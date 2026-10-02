import logging

from rest_framework import serializers

from .models import Analysis, CV, User


logger = logging.getLogger("resumes")


class RegistrationSerializer(serializers.ModelSerializer):
	password = serializers.CharField(write_only=True, min_length=8)

	class Meta:
		model = User
		fields = ["id", "email", "first_name", "last_name", "password"]
		read_only_fields = ["id"]

	def create(self, validated_data):
		return User.objects.create_user(is_active=False, **validated_data)


class EmailVerificationSerializer(serializers.Serializer):
	email = serializers.EmailField()
	code = serializers.RegexField(regex=r"^\d{6}$")


class LoginSerializer(serializers.Serializer):
	email = serializers.EmailField()
	password = serializers.CharField(write_only=True)

	def validate(self, attrs):
		user = User.objects.filter(email=attrs["email"]).first()
		if user is None or not user.check_password(attrs["password"]):
			logger.warning("Login failed: invalid credentials")
			raise serializers.ValidationError("Email or password is incorrect.")
		if not user.is_active:
			logger.warning("Login blocked: email not verified user_id=%s", user.id)
			raise serializers.ValidationError(
				"Your email is not verified. Please verify your email first."
			)

		attrs["user"] = user
		return attrs


class CVSerializer(serializers.ModelSerializer):
	class Meta:
		model = CV
		fields = ["id", "title", "file", "uploaded_at", "user"]
		read_only_fields = ["id", "uploaded_at", "user"]


class AnalysisRequestSerializer(serializers.Serializer):
	cv_id = serializers.IntegerField(min_value=1, required=False)
	title = serializers.CharField(max_length=255, required=False, write_only=True)
	file = serializers.FileField(required=False, write_only=True)
	job_title = serializers.CharField(max_length=255)
	job_description = serializers.CharField()

	def validate(self, attrs):
		if not attrs.get("cv_id") and not attrs.get("file"):
			raise serializers.ValidationError(
				"Provide either cv_id or a CV file to analyze."
			)
		if attrs.get("cv_id") and attrs.get("file"):
			raise serializers.ValidationError(
				"Provide cv_id or a CV file, not both."
			)
		return attrs


class AnalysisSerializer(serializers.ModelSerializer):
	class Meta:
		model = Analysis
		fields = ["id", "cv", "job_title", "score", "result", "created_at"]
		read_only_fields = fields
