import json
import os
import uuid
import redis as redis_lib
from django.conf import settings
from django.utils.dateparse import parse_datetime
from rest_framework import generics, permissions, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.decorators import api_view, parser_classes
from django.core.cache import cache
from .redis_client import enqueue
from .models import Alert
from .serializers import AlertSerializer, RegisterSerializer


class RegisterView(generics.CreateAPIView):
    """POST /api/auth/register/  (optional helper to create users)"""
    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]


class AlertListCreateView(generics.ListCreateAPIView):
    """
    POST /api/alerts/  -> camera sends image + alert_names + camera_no + alert_time
    GET  /api/alerts/  -> list saved alerts (filters: ?camera_no=1&alert_name=person)
    """
    serializer_class = AlertSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    def get_queryset(self):
        qs = Alert.objects.all()
        camera_no = self.request.query_params.get('camera_no')
        alert_name = self.request.query_params.get('alert_name')
        if camera_no:
            qs = qs.filter(camera_no=camera_no)
        if alert_name:
            qs = qs.filter(alert_names__contains=[alert_name.lower()])
        return qs

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {'message': 'Alert saved', 'data': serializer.data},
            status=status.HTTP_201_CREATED,
        )


MAX_IMAGE_BYTES = 5 * 1024 * 1024
UPLOAD_DIR = "alerts"
ITEM_TTL = 300


def _key(ref):
    return f"alert:{ref}"


def _parse_names(request):
    names = [n.strip().lower() for n in request.data.getlist("alert_names") if n.strip()]
    if len(names) == 1 and "," in names[0]:
        names = [n.strip().lower() for n in names[0].split(",") if n.strip()]
    return names


# ---------- CREATE ----------
@api_view(["POST"])
@parser_classes([MultiPartParser, FormParser])
def alert_create(request):
    f = request.FILES.get("image")
    if not f:
        return Response({"image": "This field is required."}, status=400)
    if f.size > MAX_IMAGE_BYTES:
        return Response({"image": "File too large (max 5 MB)."}, status=400)
    if not (f.content_type or "").startswith("image/"):
        return Response({"image": "Only image files are allowed."}, status=400)

    camera_no = request.data.get("camera_no")
    if not camera_no:
        return Response({"camera_no": "This field is required."}, status=400)
    alert_time = parse_datetime(request.data.get("alert_time") or "")
    if alert_time is None:
        return Response({"alert_time": "Invalid ISO datetime."}, status=400)
    names = _parse_names(request)
    if not names:
        return Response({"alert_names": "This field is required."}, status=400)

    ref = uuid.uuid4().hex
    rel_name = f"{UPLOAD_DIR}/{ref}.jpg"
    full = os.path.join(settings.MEDIA_ROOT, rel_name)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "wb") as out:
        for chunk in f.chunks():
            out.write(chunk)

    data = {"ref": ref, "image": rel_name, "alert_names": names,
            "camera_no": camera_no, "alert_time": alert_time.isoformat()}
    try:
        enqueue("create", data)
    except redis_lib.RedisError:
        os.remove(full)
        return Response({"detail": "Queue unavailable, retry."}, status=503)

    cache.set(_key(ref), {**data, "pending": True}, ITEM_TTL)   # readable immediately
    return Response({"message": "Alert queued", "ref": ref}, status=202)


# ---------- READ ONE: Redis -> DB -> store ----------
@api_view(["GET"])
def alert_get(request, ref):
    hit = cache.get(_key(ref))
    if hit is not None:
        if hit.get("deleted"):
            return Response({"detail": "Not found."}, status=404)
        return Response(hit)

    try:
        obj = Alert.objects.get(ref=ref)
    except Alert.DoesNotExist:
        return Response({"detail": "Not found."}, status=404)

    data = dict(AlertSerializer(obj, context={"request": request}).data)
    data["ref"] = obj.ref.hex
    cache.set(_key(ref), data, ITEM_TTL)
    return Response(data)


# ---------- UPDATE ----------
@api_view(["PATCH"])
@parser_classes([JSONParser, FormParser, MultiPartParser])
def alert_update(request, ref):
    changes = {}
    if "camera_no" in request.data:
        changes["camera_no"] = request.data["camera_no"]
    if "alert_time" in request.data:
        t = parse_datetime(request.data["alert_time"])
        if t is None:
            return Response({"alert_time": "Invalid ISO datetime."}, status=400)
        changes["alert_time"] = t.isoformat()
    if "alert_names" in request.data:
        names = _parse_names(request) if hasattr(request.data, "getlist") \
            else [str(n).lower() for n in request.data["alert_names"]]
        if not names:
            return Response({"alert_names": "Cannot be empty."}, status=400)
        changes["alert_names"] = names
    if not changes:
        return Response({"detail": "Nothing to update."}, status=400)

    try:
        enqueue("update", {"ref": ref, "changes": changes})
    except redis_lib.RedisError:
        return Response({"detail": "Queue unavailable, retry."}, status=503)

    hit = cache.get(_key(ref))
    if hit:
        hit.update(changes)
        cache.set(_key(ref), hit, ITEM_TTL)
    else:
        cache.delete(_key(ref))
    return Response({"message": "Update queued"}, status=202)


# ---------- DELETE ----------
@api_view(["DELETE"])
def alert_delete(request, ref):
    try:
        enqueue("delete", {"ref": ref})
    except redis_lib.RedisError:
        return Response({"detail": "Queue unavailable, retry."}, status=503)
    cache.set(_key(ref), {"deleted": True}, 120)      # tombstone: GET returns 404 now
    return Response({"message": "Delete queued"}, status=202)