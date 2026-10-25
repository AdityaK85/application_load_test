import json
import redis
from django.conf import settings

r = redis.Redis.from_url(settings.ALERT_QUEUE_URL, decode_responses=True,
                         socket_timeout=5, socket_connect_timeout=2)

STREAM = "alerts_stream"
GROUP = "alerts_workers"
DEAD = "alerts_dead"          # messages that keep failing


def enqueue(op, data):
    """op: create | update | delete"""
    r.xadd(STREAM, {"op": op, "data": json.dumps(data, default=str)})