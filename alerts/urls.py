from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .views import AlertListCreateView, RegisterView

urlpatterns = [
    # Auth
    path('auth/register/', RegisterView.as_view(), name='register'),
    path('auth/login/', TokenObtainPairView.as_view(), name='login'),        # access (1h) + refresh
    path('auth/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # Alerts
    path('alerts/', AlertListCreateView.as_view(), name='alerts'),
]
