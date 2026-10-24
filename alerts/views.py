from rest_framework import generics, permissions, status
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.response import Response

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
