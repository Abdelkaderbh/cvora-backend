import json
import os
import urllib.error
import urllib.request

from rest_framework import serializers


OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite").strip()
if not GEMINI_MODEL:
    GEMINI_MODEL = "gemini-3.5-flash-lite"
GEMINI_FALLBACK_MODEL = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-3.5-flash").strip()


def _comparison_prompt(cv_text, job_title, job_description):
    return f"""
You are a professional recruitment assistant. Compare the CV with the job post.
Return only valid JSON. Do not include Markdown or additional text.

Required JSON shape:
{{
  "score": 0,
  "matched_keywords": [],
  "missing_keywords": [],
  "strengths": [],
  "gaps": [],
  "recommendations": [],
  "summary": ""
}}

Rules:
- score is an integer from 0 to 100.
- Match equivalent terms and synonyms, including singular/plural forms.
- Do not treat polite recruitment wording such as "we are looking", "join our team", or "experienced" as skills.
- Compare technical skills, responsibilities, seniority, domain knowledge, and relevant achievements.
- Keep each list concise and based only on the provided text.

JOB TITLE:
{job_title}

JOB DESCRIPTION:
{job_description}

CV TEXT:
{cv_text[:30000]}
""".strip()


def _parse_comparison_result(result_text):
    try:
        result = json.loads(result_text)
        score = max(0, min(100, int(result["score"])))
        return {
            "score": score,
            "matched_keywords": result.get("matched_keywords", []),
            "missing_keywords": result.get("missing_keywords", []),
            "strengths": result.get("strengths", []),
            "gaps": result.get("gaps", []),
            "recommendations": result.get("recommendations", []),
            "summary": result.get("summary", ""),
        }
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise serializers.ValidationError(
            "The AI model returned an invalid comparison result."
        ) from exc


def analyze_with_ollama(cv_text, job_title, job_description):
    prompt = _comparison_prompt(cv_text, job_title, job_description)
    payload = json.dumps(
        {
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.1},
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{OLLAMA_URL.rstrip('/')}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=int(os.getenv("OLLAMA_TIMEOUT", "120")),
        ) as response:
            response_data = json.load(response)
    except (urllib.error.URLError, TimeoutError) as exc:
        raise serializers.ValidationError(
            "The local AI model is unavailable. Start Ollama and try again."
        ) from exc

    try:
        return _parse_comparison_result(response_data["response"])
    except (KeyError, TypeError) as exc:
        raise serializers.ValidationError(
            "The AI model returned an invalid comparison result."
        ) from exc


def analyze_with_gemini(cv_text, job_title, job_description):
    if not GEMINI_API_KEY:
        raise serializers.ValidationError(
            "GEMINI_API_KEY is not configured. Add your Google AI Studio key to .env."
        )

    payload = json.dumps(
        {
            "contents": [{"parts": [{"text": _comparison_prompt(cv_text, job_title, job_description)}]}],
            "generationConfig": {
                "temperature": 0.1,
                "responseMimeType": "application/json",
            },
        }
    ).encode("utf-8")
    models = [GEMINI_MODEL]
    if GEMINI_FALLBACK_MODEL and GEMINI_FALLBACK_MODEL != GEMINI_MODEL:
        models.append(GEMINI_FALLBACK_MODEL)

    for model_index, model in enumerate(models):
        request = urllib.request.Request(
            f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(
                request,
                timeout=int(os.getenv("GEMINI_TIMEOUT", "120")),
            ) as response:
                response_data = json.load(response)
            result_text = response_data["candidates"][0]["content"]["parts"][0]["text"]
            return _parse_comparison_result(result_text)
        except urllib.error.HTTPError as exc:
            if exc.code == 503 and model_index < len(models) - 1:
                continue
            try:
                error_body = json.loads(exc.read().decode("utf-8"))
                error_message = error_body.get("error", {}).get("message", "")
            except (json.JSONDecodeError, UnicodeDecodeError):
                error_message = ""
            detail = f" ({error_message})" if error_message else ""
            raise serializers.ValidationError(
                f"Gemini request failed with HTTP {exc.code}{detail}."
            ) from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise serializers.ValidationError(
                "Gemini could not be reached. Check your internet connection and GEMINI_API_KEY."
            ) from exc
        except (KeyError, IndexError, TypeError) as exc:
            raise serializers.ValidationError(
                "Gemini returned an empty comparison result."
            ) from exc

