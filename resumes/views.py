import logging
import os
import re
import secrets
from datetime import timedelta

from django.core.mail import send_mail
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, permissions, serializers, status, viewsets
from rest_framework.authtoken.models import Token
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.parsers import FormParser, MultiPartParser

from .models import Analysis, CV, User
from .ai import analyze_with_gemini, analyze_with_ollama
from .serializers import (
	AnalysisRequestSerializer,
	AnalysisSerializer,
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
		name = f"{user.first_name} {user.last_name}".strip() or user.email
		return Response({"token": token.key, "user_id": user.id, "name": name})


class CVUploadAPIView(APIView):
	permission_classes = [permissions.IsAuthenticated]
	parser_classes = [MultiPartParser, FormParser]

	def post(self, request):
		serializer = CVSerializer(data=request.data)
		serializer.is_valid(raise_exception=True)
		cv = serializer.save(user=request.user)
		logger.info("CV uploaded: cv_id=%s user_id=%s", cv.id, request.user.id)
		return Response(CVSerializer(cv).data, status=status.HTTP_201_CREATED)


def _extract_cv_text(cv):
	if cv.file.name.lower().endswith((".txt", ".md")):
		cv.file.open("rb")
		try:
			return cv.file.read().decode("utf-8", errors="ignore")
		finally:
			cv.file.close()

	try:
		from pypdf import PdfReader
	except ImportError:
		raise serializers.ValidationError(
			"PDF analysis requires the pypdf package to be installed."
		)

	try:
		cv.file.open("rb")
		reader = PdfReader(cv.file)
		return "\n".join(page.extract_text() or "" for page in reader.pages)
	finally:
		cv.file.close()


def _normalize_keyword(word):
	word = word.lower()
	if word == "apis":
		return "api"
	if word.endswith("ies") and len(word) > 4:
		return f"{word[:-3]}y"
	if word.endswith("s") and not word.endswith("ss") and len(word) > 3:
		return word[:-1]
	return word


def _keywords(text):
	stop_words = {
		"a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
		"in", "is", "of", "on", "or", "that", "the", "this", "to", "with",
		"we", "our", "you", "your", "looking", "seeking", "experienced",
		"experience", "strong", "ability", "work", "working", "join", "team",
		"candidate", "role", "position", "responsible", "responsibilities",
		"including", "build", "develop", "development", "using",
	}
	keywords = set()
	for word in re.findall(
		r"[a-zA-Z][a-zA-Z0-9+#]*(?:[.-][a-zA-Z0-9+#]+)*", text
	):
		normalized_word = _normalize_keyword(word)
		if normalized_word not in stop_words:
			keywords.add(normalized_word)
	return keywords


class CVAnalysisAPIView(APIView):
	permission_classes = [permissions.IsAuthenticated]
	parser_classes = [MultiPartParser, FormParser]

	def post(self, request):
		request_serializer = AnalysisRequestSerializer(data=request.data)
		request_serializer.is_valid(raise_exception=True)
		data = request_serializer.validated_data
		if data.get("file"):
			cv = CV.objects.create(
				user=request.user,
				title=data.get("title") or data["file"].name,
				file=data["file"],
			)
		else:
			cv = get_object_or_404(CV, id=data["cv_id"], user=request.user)

		cv_text = _extract_cv_text(cv)
		provider = os.getenv("AI_PROVIDER", "keywords").lower()
		if provider == "gemini":
			ai_result = analyze_with_gemini(
				cv_text,
				data["job_title"],
				data["job_description"],
			)
			score = ai_result.pop("score")
			result = ai_result
		elif provider == "ollama":
			ai_result = analyze_with_ollama(
				cv_text,
				data["job_title"],
				data["job_description"],
			)
			score = ai_result.pop("score")
			result = ai_result
		else:
			job_keywords = _keywords(
				f'{data["job_title"]} {data["job_description"]}'
			)
			cv_keywords = _keywords(cv_text)
			matched_keywords = sorted(job_keywords & cv_keywords)
			missing_keywords = sorted(job_keywords - cv_keywords)
			score = round((len(matched_keywords) / len(job_keywords)) * 100, 2) if job_keywords else 0
			result = {
				"matched_keywords": matched_keywords,
				"missing_keywords": missing_keywords,
			}
		result["job_description"] = data["job_description"]

		analysis = Analysis.objects.create(
			user=request.user,
			cv=cv,
			job_title=data["job_title"],
			score=score,
			result=result,
		)
		logger.info("CV analyzed: analysis_id=%s user_id=%s", analysis.id, request.user.id)
		return Response(AnalysisSerializer(analysis).data, status=status.HTTP_201_CREATED)


class AnalysisListAPIView(generics.ListAPIView):
	permission_classes = [permissions.IsAuthenticated]
	serializer_class = AnalysisSerializer

	def get_queryset(self):
		return Analysis.objects.filter(user=self.request.user).order_by("-created_at")


class CVDeleteAPIView(APIView):
	permission_classes = [permissions.IsAuthenticated]

	def delete(self, request, pk):
		cv = get_object_or_404(CV, id=pk, user=request.user)
		cv.delete()
		return Response(status=status.HTTP_204_NO_CONTENT)


class CVViewSet(viewsets.ModelViewSet):
	serializer_class = CVSerializer
	permission_classes = [permissions.IsAuthenticated]
	parser_classes = [MultiPartParser, FormParser]

	def get_queryset(self):
		return CV.objects.filter(user=self.request.user).order_by("-uploaded_at")

	def perform_create(self, serializer):
		cv = serializer.save(user=self.request.user)
		logger.info("CV uploaded: cv_id=%s user_id=%s", cv.id, self.request.user.id)
