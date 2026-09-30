from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .models import CV, User


class CVApiTests(APITestCase):
	def setUp(self):
		self.user = User.objects.create_user(
			email="owner@example.com",
			password="strong-password-123",
		)
		self.other_user = User.objects.create_user(
			email="other@example.com",
			password="strong-password-123",
		)
		self.client.force_authenticate(user=self.user)

	def test_user_can_upload_a_cv(self):
		uploaded_file = SimpleUploadedFile(
			"resume.pdf",
			b"fake pdf content",
			content_type="application/pdf",
		)

		response = self.client.post(
			reverse("cv-list"),
			{"title": "Backend resume", "file": uploaded_file},
			format="multipart",
		)

		self.assertEqual(response.status_code, status.HTTP_201_CREATED)
		self.assertTrue(
			CV.objects.filter(user=self.user, title="Backend resume").exists()
		)

	def test_user_only_sees_own_cvs(self):
		CV.objects.create(
			user=self.user,
			title="My resume",
			file=SimpleUploadedFile("mine.pdf", b"mine"),
		)
		CV.objects.create(
			user=self.other_user,
			title="Other resume",
			file=SimpleUploadedFile("other.pdf", b"other"),
		)

		response = self.client.get(reverse("cv-list"))

		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertEqual(len(response.data), 1)
		self.assertEqual(response.data[0]["title"], "My resume")


class AuthenticationApiTests(APITestCase):
	def test_user_can_register(self):
		response = self.client.post(
			reverse("register"),
			{
				"email": "new@example.com",
				"password": "strong-password-123",
				"first_name": "New",
			},
			format="json",
		)

		self.assertEqual(response.status_code, status.HTTP_201_CREATED)
		self.assertNotIn("token", response.data)
		user = User.objects.get(email="new@example.com")
		self.assertFalse(user.is_active)
		self.assertIsNotNone(user.verification_code)

		verification_response = self.client.post(
			reverse("verify-email"),
			{
				"email": user.email,
				"code": user.verification_code,
			},
			format="json",
		)

		self.assertEqual(
			verification_response.status_code,
			status.HTTP_200_OK,
		)
		self.assertIn("token", verification_response.data)
		user.refresh_from_db()
		self.assertTrue(user.is_active)

	def test_user_can_login(self):
		User.objects.create_user(
			email="login@example.com",
			password="strong-password-123",
			is_active=True,
		)

		response = self.client.post(
			reverse("login"),
			{
				"email": "login@example.com",
				"password": "strong-password-123",
			},
			format="json",
		)

		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertIn("token", response.data)
