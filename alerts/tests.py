# alerts/tests.py
import io
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIRequestFactory

from alerts.models import Alert
from alerts.serializers import AlertSerializer
from alerts.views import AlertListCreateView


def make_image(name="test.png"):
    buf = io.BytesIO()
    Image.new("RGB", (10, 10), color="red").save(buf, format="PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


class AlertCreateNoDBTest(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.view = AlertListCreateView.as_view()

    def post(self, **overrides):
        data = {
            "image": make_image(),
            "alert_names": ["person", "car"],
            "camera_no": 1,
            "alert_time": timezone.now().isoformat(),
        }
        data.update(overrides)
        data = {k: v for k, v in data.items() if v is not None}
        request = self.factory.post("/api/alerts/", data, format="multipart")
        return self.view(request)

    def test_valid_request_returns_201(self):
        fake = Alert(id=1, image="alerts/x.png", alert_names=["person", "car"],
                     camera_no=1, alert_time=timezone.now())
        with patch.object(AlertSerializer, "create", return_value=fake):
            response = self.post()

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["message"], "Alert saved")

    def test_missing_image_returns_400(self):
        self.assertEqual(self.post(image=None).status_code, 400)

    def test_invalid_image_returns_400(self):
        fake = SimpleUploadedFile("f.png", b"not an image", content_type="image/png")
        self.assertEqual(self.post(image=fake).status_code, 400)

    def test_missing_camera_no_returns_400(self):
        self.assertIn("camera_no", self.post(camera_no=None).data)

    def test_invalid_alert_time_returns_400(self):
        self.assertIn("alert_time", self.post(alert_time="not-a-date").data)

    def test_missing_alert_names_returns_400(self):
        self.assertIn("alert_names", self.post(alert_names=None).data)