# utils/gemini_scorer.py — Gemini resume scoring via direct REST API (no SDK)

import json
import re
import requests

_MODEL = "gemini-2.0-flash"
_API_URL = f"https://generativelanguage.googleapis.com/v1/models/{_MODEL}:generateContent"

_SYSTEM_PROMPT = """You are an expert ATS analyst and career coach. \
Your job is to evaluate how well a candidate's resume matches a given job description.

Return ONLY valid JSON — no markdown, no explanation:
{
  "score": <integer 0-100>,
  "strengths": ["strength 1", "strength 2", "strength 3"],
  "gaps": ["gap 1", "gap 2", "gap 3"],
  "keywords_missing": ["keyword1", "keyword2", "keyword3"]
}

Scoring guide:
- 85-100: Excellent match — candidate meets nearly all requirements
- 70-84:  Strong match — candidate meets most key requirements
- 55-69:  Moderate match — candidate meets core requirements, some gaps
- 40-54:  Weak match — significant gaps in key requirements
- 0-39:   Poor match — major qualifications missing

Keep each list to 3-4 items maximum. Be concise and specific."""


def score_resume_gemini(
    resume_text: str,
    job_description: str,
    api_key: str,
) -> dict:
    """
    Call Gemini REST API to score resume fit against a job description.
    Returns a dict with keys: score, strengths, gaps, keywords_missing.
    """
    user_message = f"""Here is the candidate's resume:

<resume>
{resume_text}
</resume>

Here is the job description:

<job_description>
{job_description}
</job_description>

Score the resume against the job description. Return ONLY the JSON object."""

    payload = {
        "system_instruction": {"parts": [{"text": _SYSTEM_PROMPT}]},
        "contents": [{"parts": [{"text": user_message}]}],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 1024,
        },
    }

    resp = requests.post(
        _API_URL,
        params={"key": api_key},
        json=payload,
        timeout=30,
    )

    if not resp.ok:
        _raise_friendly(resp)

    raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    try:
        result = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Scorer returned invalid JSON: {e}\n\nRaw output:\n{raw[:500]}")

    result.setdefault("score", 0)
    result.setdefault("strengths", [])
    result.setdefault("gaps", [])
    result.setdefault("keywords_missing", [])

    return result


def _raise_friendly(resp: requests.Response):
    try:
        detail = resp.json()
        msg = detail.get("error", {}).get("message", resp.text)
    except Exception:
        msg = resp.text
    if resp.status_code == 429:
        raise RuntimeError(f"Gemini rate limit hit — try again in a moment. ({msg})")
    if resp.status_code == 403:
        raise RuntimeError(f"Gemini API key invalid or missing permissions. ({msg})")
    raise RuntimeError(f"Gemini API error {resp.status_code}: {msg}")
