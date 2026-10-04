import json
import urllib.error
import urllib.request

from django.conf import settings


class ResendEmailError(Exception):
	"""Raised when Resend cannot accept an email request."""


def send_verification_email(recipient, verification_code):
	payload = json.dumps(
		{
			"from": settings.RESEND_FROM_EMAIL,
			"to": [recipient],
			"subject": "Verify your CVora account",
			"text": (
				f"Your CVora verification code is {verification_code}. "
				"It expires in 10 minutes."
			),
		}
	).encode("utf-8")
	request = urllib.request.Request(
		"https://api.resend.com/emails",
		data=payload,
		headers={
			"Authorization": f"Bearer {settings.RESEND_API_KEY}",
			"Content-Type": "application/json",
		},
		method="POST",
	)

	try:
		with urllib.request.urlopen(
			request,
			timeout=settings.RESEND_TIMEOUT,
		) as response:
			if response.status >= 300:
				raise ResendEmailError(
					f"Resend returned unexpected status {response.status}."
				)
	except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
		raise ResendEmailError("Resend email request failed.") from exc
