import logging
import secrets
from datetime import timedelta

from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone
from rest_framework import permissions, serializers, status, viewsets
from rest_framework.authtoken.models import Token
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import FormParser, MultiPartParser

from .models import CV, User
from .serializers import (
	CVSerializer,
	EmailVerificationSerializer,
	LoginSerializer,
	RegistrationSerializer,
)


logger = logging.getLogger("resumes")


class RegistrationAPIView(APIView):
	permission_classes = [permissions.AllowAny]

	@transaction.atomic
	def post(self, request):
		serializer = RegistrationSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		user = serializer.save()
		verification_code = f"{secrets.randbelow(1_000_000):06d}"
		user.verification_code = verification_code
		user.verification_code_created_at = timezone.now()
		user.save(update_fields=["verification_code", "verification_code_created_at"])

		send_mail(
			subject="Verify your CVora account",
		message=(
			f"Your CVora verification code is {verification_code}. "
			"It expires in 10 minutes."
		),
		from_email=None,
		recipient_list=[user.email],
		fail_silently=False,
		)
		logger.info("User registered: user_id=%s", user.id)
		return Response(
			{
				"message": "A verification code has been sent to your email.",
			},
			status=status.HTTP_201_CREATED,
		)


class EmailVerificationAPIView(APIView):
	permission_classes = [permissions.AllowAny]

	def post(self, request):
		serializer = EmailVerificationSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)

		try:
			user = User.objects.get(email=serializer.validated_data["email"])
		except User.DoesNotExist:
			raise serializers.ValidationError("Invalid email or verification code.")

		code_is_valid = user.verification_code == serializer.validated_data["code"]
		code_created_at = user.verification_code_created_at
		code_is_recent = code_created_at and code_created_at >= (
			timezone.now() - timedelta(minutes=10)
		)
		if not code_is_valid or not code_is_recent:
			raise serializers.ValidationError("Invalid or expired verification code.")

		user.is_active = True
		user.verification_code = None
		user.verification_code_created_at = None
		user.save(
			update_fields=[
				"is_active",
				"verification_code",
				"verification_code_created_at",
			]
		)
		token, _ = Token.objects.get_or_create(user=user)
		logger.info("User email verified: user_id=%s", user.id)
		return Response({"message": "Email verified.", "token": token.key})


class LoginAPIView(APIView):
	permission_classes = [permissions.AllowAny]

	def post(self, request):
		serializer = LoginSerializer(
			data=request.data,
			context={"request": request},
		)
		serializer.is_valid(raise_exception=True)
		user = serializer.validated_data["user"]
		token, _ = Token.objects.get_or_create(user=user)
		logger.info("User logged in: user_id=%s", user.id)
		return Response({"token": token.key, "user_id": user.id})


class CVViewSet(viewsets.ModelViewSet):
	serializer_class = CVSerializer
	permission_classes = [permissions.IsAuthenticated]
	parser_classes = [MultiPartParser, FormParser]

	def get_queryset(self):
		return CV.objects.filter(user=self.request.user).order_by("-uploaded_at")

	def perform_create(self, serializer):
		cv = serializer.save(user=self.request.user)
		logger.info("CV uploaded: cv_id=%s user_id=%s", cv.id, self.request.user.id)
