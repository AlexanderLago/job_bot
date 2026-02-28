# utils/gemini_scorer.py — Gemini resume scoring using google-genai SDK

import json
import re
from google import genai
from google.genai import types

_MODEL = "gemini-3-flash-preview"

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
    Call Gemini to score how well the resume matches the job description.
    Returns a dict with keys: score, strengths, gaps, keywords_missing.
    """
    client = genai.Client(api_key=api_key)

    user_message = f"""Here is the candidate's resume:

<resume>
{resume_text}
</resume>

Here is the job description:

<job_description>
{job_description}
</job_description>

Score the resume against the job description. Return ONLY the JSON object."""

    response = client.models.generate_content(
        model=_MODEL,
        contents=user_message,
        config=types.GenerateContentConfig(
            system_instruction=_SYSTEM_PROMPT,
            temperature=0.1,
            max_output_tokens=2048,
        ),
    )

    raw = response.text.strip()
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
