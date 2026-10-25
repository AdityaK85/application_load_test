import json
import os
import socket
import sys
import tempfile
import time
import uuid
from itertools import groupby

import redis as redis_lib
from django import db
from django.conf import settings
from django.core.cache import cache
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.dateparse import parse_datetime

from alerts.models import Alert
from alerts.redis_client import DEAD, GROUP, STREAM, r

try:
    import fcntl            # Linux
except ImportError:
    fcntl = None            # Windows

try:
    import msvcrt           # Windows
except ImportError:
    msvcrt = None

BATCH = 500
LOCK_FILE = os.path.join(tempfile.gettempdir(), "process_alerts.lock")


def acquire_lock(fh):
    """Return True if the lock was taken, False if another run holds it."""
    try:
        if fcntl:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        else:
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
        return True
    except (BlockingIOError, OSError):
        return False


def norm_ref(ref):
    """Always return the 32-char hex form of a UUID."""
    return uuid.UUID(str(ref)).hex


class Command(BaseCommand):
    help = "Cron job: apply queued alert operations from Redis to the database"

    def add_arguments(self, parser):
        parser.add_argument("--max-seconds", type=int, default=55,
                            help="Keep polling this long, then exit (0 = drain once and exit)")

    def handle(self, *args, **opts):
        # ---- prevent overlapping runs on this machine ----
        lock = open(LOCK_FILE, "w")          # keep this handle open until the run ends
        if not acquire_lock(lock):
            self.stdout.write("Previous run still active, exiting")
            return

        # Fixed consumer name: unacked messages from a crashed run are re-read next time
        consumer = f"cron-{socket.gethostname()}"
        try:
            r.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
        except redis_lib.ResponseError:
            pass                             # group already exists

        deadline = time.time() + opts["max_seconds"]
        total = 0

        # 1) recover messages delivered earlier but never acked (crash, DB error)
        while True:
            msgs = self.read(consumer, "0", block=None)
            if not msgs:
                break
            total += self.apply(msgs)

        # 2) process new messages until the queue is empty (or time is up)
        while True:
            msgs = self.read(consumer, ">", block=1000 if time.time() < deadline else None)
            if msgs:
                total += self.apply(msgs)
            if not msgs and time.time() >= deadline:
                break
            if opts["max_seconds"] == 0 and not msgs:
                break

        self.stdout.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} done, applied {total} operations")

    def read(self, consumer, start_id, block):
        try:
            resp = r.xreadgroup(GROUP, consumer, {STREAM: start_id}, count=BATCH, block=block)
        except redis_lib.RedisError as exc:
            self.stderr.write(f"Redis error: {exc}")
            sys.exit(1)                      # cron will retry in a minute
        return resp[0][1] if resp else []

    # ---- one batch ----
    def apply(self, msgs):
        db.close_old_connections()
        ids = [m[0] for m in msgs]
        items = []
        for m in msgs:
            try:
                data = json.loads(m[1]["data"])
                data["ref"] = norm_ref(data["ref"])
                items.append((m[1]["op"], data))
            except Exception as exc:         # malformed message -> dead letter
                r.xadd(DEAD, {"op": m[1].get("op", "?"), "data": m[1].get("data", ""),
                              "error": f"bad message: {exc}"[:300]})

        try:
            self.run_batch(items)
        except Exception as exc:
            self.stderr.write(f"Batch failed ({exc}); retrying one by one")
            for item in items:
                try:
                    self.run_batch([item])
                except Exception as e2:
                    r.xadd(DEAD, {"op": item[0], "data": json.dumps(item[1]),
                                  "error": str(e2)[:300]})
        r.xack(STREAM, GROUP, *ids)
        r.xdel(STREAM, *ids)
        return len(msgs)

    def run_batch(self, items):
        touched, files_to_delete = set(), []
        with transaction.atomic():
            for op, group in groupby(items, key=lambda x: x[0]):
                data = [d for _, d in group]
                if op == "create":
                    self.do_create(data)
                elif op == "update":
                    self.do_update(data)
                elif op == "delete":
                    files_to_delete += self.do_delete(data)
                touched.update(d["ref"] for d in data)

        for ref in touched:                  # after commit
            cache.delete(f"alert:{ref}")
        for path in files_to_delete:
            try:
                os.remove(os.path.join(settings.MEDIA_ROOT, path))
            except OSError:
                pass

    def do_create(self, rows):
        Alert.objects.bulk_create(
            [Alert(ref=d["ref"], image=d["image"], alert_names=d["alert_names"],
                   camera_no=d["camera_no"], alert_time=parse_datetime(d["alert_time"]))
             for d in rows],
            batch_size=BATCH, ignore_conflicts=True)

    def do_update(self, rows):
        by_ref = {}
        for d in rows:
            by_ref.setdefault(d["ref"], {}).update(d["changes"])
        objs = list(Alert.objects.filter(ref__in=by_ref))
        fields = set()
        for o in objs:
            for k, v in by_ref[o.ref.hex].items():
                setattr(o, k, parse_datetime(v) if k == "alert_time" else v)
                fields.add(k)
        if objs:
            Alert.objects.bulk_update(objs, list(fields), batch_size=BATCH)

    def do_delete(self, rows):
        refs = [d["ref"] for d in rows]
        qs = Alert.objects.filter(ref__in=refs)
        paths = [str(i) for i in qs.values_list("image", flat=True)]
        qs.delete()
        return paths