# utils/company_research.py — Company research engine (career-ops style)
#
# Produces a structured 6-dimension company deep-dive to inform interview
# preparation and application strategy.

import json
import re

_RESEARCH_PROMPT = """You are a senior talent intelligence researcher.

Given a company name, job description, and candidate resume, produce a structured company analysis.
Return ONLY valid JSON with these exact keys — no markdown, no prose:

{
  "company_name": "<extracted or inferred company name>",
  "ai_strategy": {
    "summary": "<2-3 sentences on their AI products, stack, published research, LLM usage>",
    "notable_signals": ["<signal 1>", "<signal 2>"]
  },
  "recent_movements": {
    "summary": "<funding rounds, key hires, product launches, acquisitions in last 12-18 months>",
    "notable_signals": ["<signal 1>", "<signal 2>"]
  },
  "engineering_culture": {
    "summary": "<deployment cadence, open-source presence, tech blog, engineering org signals>",
    "notable_signals": ["<signal 1>", "<signal 2>"]
  },
  "probable_challenges": {
    "summary": "<scaling pains, tech debt signals, market pressures, org complexity>",
    "notable_signals": ["<challenge 1>", "<challenge 2>"]
  },
  "competitive_positioning": {
    "summary": "<main competitors, differentiation, market position>",
    "notable_signals": ["<signal 1>", "<signal 2>"]
  },
  "candidate_alignment": {
    "summary": "<how the candidate's background specifically maps to this company's needs and context>",
    "talking_points": [
      "<specific thing to mention in interviews based on company context>",
      "<question to ask that demonstrates research depth>"
    ]
  }
}

Base your analysis on signals in the job description and your knowledge of the company.
Be specific — no generic filler. If you don't have reliable data for a section, say so briefly."""


def research_company(
    job_description: str,
    resume_text: str,
    provider_cfg: dict,
    api_key: str,
    company_name: str = "",
) -> dict:
    """
    Generate a 6-dimension company research report.

    Parameters
    ----------
    job_description : Full JD text.
    resume_text     : Candidate resume for alignment section.
    provider_cfg    : Provider config dict.
    api_key         : Provider API key.
    company_name    : Optional — extracted from JD if blank.
    """
    company_hint = f"Company: {company_name}\n\n" if company_name else ""

    user_message = (
        f"{company_hint}"
        f"JOB DESCRIPTION\n{job_description[:5000]}\n\n"
        f"CANDIDATE RESUME (for alignment section only)\n{resume_text[:3000]}\n\n"
        "Produce the company research JSON."
    )

    raw = _call_provider(provider_cfg, api_key, user_message, max_tokens=2500)
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)


def _call_provider(
    cfg: dict,
    api_key: str,
    user_message: str,
    max_tokens: int = 2500,
) -> str:
    provider_id = cfg.get("id", "")

    if provider_id == "claude":
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model=cfg.get("model", "claude-sonnet-4-6"),
            max_tokens=max_tokens,
            temperature=0.1,
            system=_RESEARCH_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
        return resp.content[0].text

    if provider_id in ("gemini15", "gemini20", "gemini25"):
        from google import genai
        from google.genai import types as gtypes
        client = genai.Client(api_key=api_key)
        resp = client.models.generate_content(
            model=cfg.get("model", "gemini-2.0-flash"),
            contents=f"{_RESEARCH_PROMPT}\n\n{user_message}",
            config=gtypes.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=max_tokens,
            ),
        )
        return resp.text

    import openai
    client = openai.OpenAI(
        api_key=api_key,
        base_url=cfg.get("base_url", "https://api.openai.com/v1"),
    )
    resp = client.chat.completions.create(
        model=cfg.get("model", "gpt-4o-mini"),
        max_tokens=max_tokens,
        temperature=0.1,
        messages=[
            {"role": "system", "content": _RESEARCH_PROMPT},
            {"role": "user",   "content": user_message},
        ],
    )
    return resp.choices[0].message.content
