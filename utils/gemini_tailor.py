# utils/gemini_tailor.py — Gemini resume tailoring via direct REST API (no SDK)

import json
import re
import requests

_MODEL = "gemini-2.0-flash"
_API_URL = f"https://generativelanguage.googleapis.com/v1/models/{_MODEL}:generateContent"

_SYSTEM_PROMPT = """You are an expert ATS resume writer and career coach. Your job is to tailor a \
candidate's resume to a specific job description to maximize their chances of passing Applicant \
Tracking Systems (ATS) and impressing human reviewers.

ABSOLUTE RULES — NEVER BREAK THESE:
1. NEVER fabricate, invent, or embellish any experience, skill, credential, date, company, title, \
or accomplishment that does not already exist in the candidate's original resume.
2. ONLY rephrase and restructure content that is already there. You may reword bullets using the \
job description's language — but only where the meaning is accurate.
3. If the job requires a qualification the candidate clearly does not have, do NOT add it.
4. Preserve all dates, company names, school names, and degrees exactly as they appear.
5. Do not invent numbers or metrics that weren't in the original.

ATS OPTIMIZATION RULES:
- Use standard section headers: Summary, Experience, Education, Skills, Certifications
- Mirror keywords and phrases from the job description wherever they truthfully apply
- Use strong, specific action verbs (Led, Designed, Implemented, Managed, etc.)
- Keep bullets concise: 1-2 lines, starting with a verb, ending with impact where possible
- Prioritize the most relevant experience for this specific job
- Skills section should list exact terms from the job description that the candidate actually has

TEMPERATURE GUIDANCE:
- At low temperature you were asked to be conservative: minimal rewording, stay close to original language
- At high temperature you were asked to be more creative: bolder rewording, stronger verbs, more dynamic framing
- In either case: NEVER fabricate

OUTPUT FORMAT — return ONLY valid JSON, no markdown, no explanation, just the JSON object:
{
  "name": "Full Name",
  "email": "email@example.com",
  "phone": "phone number",
  "location": "City, State (or City, State, ZIP)",
  "linkedin": "LinkedIn URL or empty string",
  "website": "personal website or empty string",
  "summary": "3-4 sentence professional summary tailored to this specific job and company",
  "experience": [
    {
      "title": "Job Title",
      "company": "Company Name",
      "location": "City, State",
      "dates": "Month Year - Month Year (or Present)",
      "bullets": [
        "Bullet point 1 starting with action verb",
        "Bullet point 2"
      ]
    }
  ],
  "education": [
    {
      "degree": "Degree and Major",
      "school": "School Name",
      "location": "City, State",
      "dates": "Year or Year - Year",
      "details": "GPA / honors / relevant coursework if present, else empty string"
    }
  ],
  "skills": ["Skill 1", "Skill 2", "Skill 3"],
  "certifications": ["Certification 1"],
  "keywords_added": ["keyword1", "keyword2"]
}"""


def tailor_resume_gemini(
    resume_text: str,
    job_description: str,
    api_key: str,
    temperature: float = 0.3,
) -> dict:
    """
    Call Gemini REST API to tailor the resume to the job description.
    Returns a dict with the structured resume data.
    """
    user_message = f"""Here is the candidate's current resume:

<resume>
{resume_text}
</resume>

Here is the job description to tailor the resume for:

<job_description>
{job_description}
</job_description>

Temperature setting: {temperature:.2f} ({"be conservative, stay close to original language" if temperature < 0.4 else "be creative with rewording and verb choices" if temperature > 0.6 else "balanced rewording"})

Please tailor this resume to the job description following all the rules in your instructions. \
Return ONLY the JSON object, nothing else."""

    payload = {
        "system_instruction": {"parts": [{"text": _SYSTEM_PROMPT}]},
        "contents": [{"parts": [{"text": user_message}]}],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": 4096,
        },
    }

    resp = requests.post(
        _API_URL,
        params={"key": api_key},
        json=payload,
        timeout=60,
    )

    if not resp.ok:
        _raise_friendly(resp)

    raw = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()

    # Strip markdown code fences if Gemini wrapped it
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"AI returned invalid JSON: {e}\n\nRaw output:\n{raw[:500]}")


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
