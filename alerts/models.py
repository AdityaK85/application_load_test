from django.db import models


class Alert(models.Model):
    image = models.ImageField(upload_to='alerts/%Y/%m/%d/')
    alert_names = models.JSONField(default=list)      # e.g. ["person", "vehicle"]
    camera_no = models.CharField(max_length=50, db_index=True)
    alert_time = models.DateTimeField(db_index=True)  # time the alert happened on camera
    created_date = models.DateTimeField(auto_now_add=True)  # time saved in DB

    class Meta:
        ordering = ['-created_date']

    def __str__(self):
        return f"Cam {self.camera_no} | {', '.join(self.alert_names)} | {self.alert_time}"
