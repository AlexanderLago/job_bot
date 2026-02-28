# utils/scorer.py — Score resume fit against a job description using Claude

import json
import re
import anthropic

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


def score_resume(
    resume_text: str,
    job_description: str,
    api_key: str,
) -> dict:
    """
    Call Claude to score how well the resume matches the job description.

    Returns a dict with keys: score (int), strengths (list), gaps (list),
    keywords_missing (list).
    Raises ValueError if Claude returns invalid JSON.
    """
    client = anthropic.Anthropic(api_key=api_key)

    user_message = f"""Here is the candidate's resume:

<resume>
{resume_text}
</resume>

Here is the job description:

<job_description>
{job_description}
</job_description>

Score the resume against the job description. Return ONLY the JSON object."""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        temperature=0.1,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    raw = response.content[0].text.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    try:
        result = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Scorer returned invalid JSON: {e}\n\nRaw output:\n{raw[:500]}")

    # Ensure expected keys exist
    result.setdefault("score", 0)
    result.setdefault("strengths", [])
    result.setdefault("gaps", [])
    result.setdefault("keywords_missing", [])

    return result
