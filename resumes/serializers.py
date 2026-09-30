from rest_framework import serializers

from .models import CV, User


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
		from django.contrib.auth import authenticate

		user = authenticate(
			request=self.context.get("request"),
			email=attrs["email"],
			password=attrs["password"],
		)
		if user is None:
			raise serializers.ValidationError("Invalid email or password.")
		if not user.is_active:
			raise serializers.ValidationError("This account is inactive.")

		attrs["user"] = user
		return attrs


class CVSerializer(serializers.ModelSerializer):
	class Meta:
		model = CV
		fields = ["id", "title", "file", "uploaded_at", "user"]
		read_only_fields = ["id", "uploaded_at", "user"]
