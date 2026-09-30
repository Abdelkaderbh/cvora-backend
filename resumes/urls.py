from rest_framework.routers import DefaultRouter
from django.urls import path

from .views import (
	CVViewSet,
	EmailVerificationAPIView,
	LoginAPIView,
	RegistrationAPIView,
)


router = DefaultRouter()
router.register("cvs", CVViewSet, basename="cv")

urlpatterns = [
	path("register/", RegistrationAPIView.as_view(), name="register"),
	path("verify-email/", EmailVerificationAPIView.as_view(), name="verify-email"),
	path("login/", LoginAPIView.as_view(), name="login"),
] + router.urls
