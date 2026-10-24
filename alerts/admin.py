from django.contrib import admin
from .models import Alert


@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    list_display = ('id', 'camera_no', 'alert_names', 'alert_time', 'created_date')
    list_filter = ('camera_no',)
