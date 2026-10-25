from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .views import *

urlpatterns = [
    # Auth
    path('auth/register/', RegisterView.as_view(), name='register'),
    path('auth/login/', TokenObtainPairView.as_view(), name='login'),        # access (1h) + refresh
    path('auth/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # Alerts
    path("alerts/", alert_create),                          # POST
    path("alerts/<str:ref>/", alert_get),                   # GET
    path("alerts/<str:ref>/update/", alert_update),         # PATCH
    path("alerts/<str:ref>/delete/", alert_delete),
]
