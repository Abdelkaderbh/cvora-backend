import json
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from .models import Analysis, CV, User
from . import ai


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

	def test_user_can_delete_own_cv_and_its_analysis_results(self):
		cv = CV.objects.create(
			user=self.user,
			title="Resume to delete",
			file=SimpleUploadedFile("resume.pdf", b"resume"),
		)
		analysis = Analysis.objects.create(
			user=self.user,
			cv=cv,
			job_title="Backend Engineer",
			score=75,
			result={"summary": "To be deleted"},
		)

		response = self.client.delete(reverse("cv-delete", args=[cv.id]))

		self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
		self.assertFalse(CV.objects.filter(id=cv.id).exists())
		self.assertFalse(Analysis.objects.filter(id=analysis.id).exists())

	def test_user_can_upload_a_cv_with_login_token(self):
		token = Token.objects.create(user=self.user)
		self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
		uploaded_file = SimpleUploadedFile(
			"token-resume.pdf",
			b"fake pdf content",
			content_type="application/pdf",
		)

		response = self.client.post(
			reverse("cv-list"),
			{"title": "Token resume", "file": uploaded_file},
			format="multipart",
		)

		self.assertEqual(response.status_code, status.HTTP_201_CREATED)
		self.assertTrue(
			CV.objects.filter(user=self.user, title="Token resume").exists()
		)

	def test_user_can_upload_a_cv_with_explicit_upload_endpoint(self):
		token = Token.objects.create(user=self.user)
		self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
		uploaded_file = SimpleUploadedFile(
			"explicit-resume.pdf",
			b"fake pdf content",
			content_type="application/pdf",
		)

		response = self.client.post(
			reverse("cv-upload"),
			{"title": "Explicit resume", "file": uploaded_file},
			format="multipart",
		)

		self.assertEqual(response.status_code, status.HTTP_201_CREATED)
		self.assertEqual(response.data["title"], "Explicit resume")
		self.assertTrue(
			CV.objects.filter(user=self.user, title="Explicit resume").exists()
		)

	def test_user_can_compare_cv_with_job_post(self):
		token = Token.objects.create(user=self.user)
		self.client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
		cv = CV.objects.create(
			user=self.user,
			title="Backend resume",
			file=SimpleUploadedFile(
				"resume.txt",
				b"Python Django PostgreSQL REST API",
				content_type="text/plain",
			),
		)

		response = self.client.post(
			reverse("cv-analyze"),
			{
				"cv_id": cv.id,
				"job_title": "Backend Engineer",
				"job_description": "Build Python Django APIs with PostgreSQL.",
			},
			format="json",
		)

		self.assertEqual(response.status_code, status.HTTP_201_CREATED)
		self.assertEqual(response.data["score"], 66.67)
		self.assertIn("python", response.data["result"]["matched_keywords"])
		self.assertNotIn("looking", response.data["result"]["missing_keywords"])
		self.assertTrue(Analysis.objects.filter(id=response.data["id"]).exists())

	@patch("resumes.views.analyze_with_gemini")
	def test_user_can_upload_and_analyze_cv_in_one_request(self, mock_analyze):
		mock_analyze.return_value = {
			"score": 80,
			"matched_keywords": ["python"],
			"missing_keywords": [],
			"strengths": [],
			"gaps": [],
			"recommendations": [],
			"summary": "Good match",
		}
		response = self.client.post(
			reverse("cv-analyze"),
			{
				"title": "New resume",
				"file": SimpleUploadedFile(
					"new-resume.txt",
					b"Python Django",
					content_type="text/plain",
				),
				"job_title": "Backend Engineer",
				"job_description": "Build Python APIs.",
			},
			format="multipart",
		)

		self.assertEqual(response.status_code, status.HTTP_201_CREATED)
		self.assertEqual(response.data["score"], 80)
		self.assertEqual(response.data["cv"], CV.objects.get(title="New resume").id)

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

	def test_user_only_sees_own_analysis_results(self):
		own_cv = CV.objects.create(
			user=self.user,
			title="My resume",
			file=SimpleUploadedFile("mine.pdf", b"mine"),
		)
		other_cv = CV.objects.create(
			user=self.other_user,
			title="Other resume",
			file=SimpleUploadedFile("other.pdf", b"other"),
		)
		Analysis.objects.create(
			user=self.user,
			cv=own_cv,
			job_title="Backend Engineer",
			score=80,
			result={"summary": "Own result"},
		)
		Analysis.objects.create(
			user=self.other_user,
			cv=other_cv,
			job_title="Frontend Engineer",
			score=60,
			result={"summary": "Other result"},
		)

		response = self.client.get(reverse("analysis-list"))

		self.assertEqual(response.status_code, status.HTTP_200_OK)
		self.assertEqual(len(response.data), 1)
		self.assertEqual(response.data[0]["result"]["summary"], "Own result")


class GeminiAiTests(APITestCase):
	@patch("resumes.ai.urllib.request.urlopen")
	def test_gemini_uses_the_configured_model_and_json_response(self, mock_urlopen):
		response = mock_urlopen.return_value.__enter__.return_value
		response.read.return_value = json.dumps(
			{
				"candidates": [
					{
						"content": {
							"parts": [
								{
									"text": json.dumps(
										{
											"score": 80,
											"matched_keywords": ["python"],
											"missing_keywords": [],
											"strengths": [],
											"gaps": [],
											"recommendations": [],
											"summary": "Good match",
										}
									)
								}
							]
						}
					}
				]
			}
		).encode()

		with patch.object(ai, "GEMINI_API_KEY", "test-key"), patch.object(
			ai, "GEMINI_MODEL", "gemini-3.5-flash-lite"
		):
			result = ai.analyze_with_gemini("Python CV", "Backend Engineer", "Python")

		request = mock_urlopen.call_args.args[0]
		self.assertIn("models/gemini-3.5-flash-lite:generateContent", request.full_url)
		self.assertEqual(result["score"], 80)


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

	def test_unverified_user_gets_email_verification_message(self):
		User.objects.create_user(
			email="unverified@example.com",
			password="strong-password-123",
		)

		response = self.client.post(
			reverse("login"),
			{
				"email": "unverified@example.com",
				"password": "strong-password-123",
			},
			format="json",
		)

		self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
		self.assertIn("not verified", str(response.data).lower())
