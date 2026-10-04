from rest_framework.routers import DefaultRouter
from django.urls import path

from .views import (
	CVUploadAPIView,
	CVViewSet,
	CVAnalysisAPIView,
	AnalysisListAPIView,
	AnalysisStatisticsAPIView,
	CVDeleteAPIView,
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
	path("cvs/upload/", CVUploadAPIView.as_view(), name="cv-upload"),
	path("cvs/analyze/", CVAnalysisAPIView.as_view(), name="cv-analyze"),
	path("cvs/analyses/", AnalysisListAPIView.as_view(), name="analysis-list"),
	path("cvs/statistics/", AnalysisStatisticsAPIView.as_view(), name="analysis-statistics"),
	path("cvs/<int:pk>/delete/", CVDeleteAPIView.as_view(), name="cv-delete"),
] + router.urls
