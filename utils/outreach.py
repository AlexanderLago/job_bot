# utils/outreach.py — LinkedIn outreach message generator (career-ops style)
#
# Generates a concise 3-component LinkedIn connection message:
#   Hook    — company-specific challenge (not generic flattery)
#   Proof   — one quantifiable candidate achievement
#   Proposal — low-pressure conversation request
# Target: ≤ 300 characters total.

import json
import re

_OUTREACH_PROMPT = """You are an expert LinkedIn outreach writer for tech professionals.

Write a LinkedIn connection request message with exactly three components:
1. HOOK: A company-specific observation (a challenge they face, a product angle, a recent move).
   Do NOT start with "I saw your job posting" or generic compliments.
2. PROOF: One quantified achievement from the candidate's resume that's directly relevant.
3. PROPOSAL: A low-pressure ask — offer to share thoughts, ask a specific question, or suggest a quick chat.

Rules:
- Total message ≤ 300 characters (LinkedIn limit).
- Conversational, not salesy. First-person. No buzzwords.
- The hook must be specific to the company/role, not generic.

Return ONLY valid JSON — no markdown, no prose:
{
  "hook": "<1 sentence>",
  "proof": "<1 sentence with a number>",
  "proposal": "<1 sentence>",
  "full_message": "<hook + proof + proposal combined, ≤ 300 chars>",
  "char_count": <integer>
}"""


def generate_linkedin_message(
    resume_text: str,
    job_description: str,
    provider_cfg: dict,
    api_key: str,
    target_name: str = "",
    company_name: str = "",
) -> dict:
    """
    Generate a LinkedIn outreach message.

    Returns dict with keys: hook, proof, proposal, full_message, char_count.
    """
    target_hint = f"Target person: {target_name}\n" if target_name else ""
    company_hint = f"Company: {company_name}\n" if company_name else ""

    user_message = (
        f"{target_hint}{company_hint}"
        f"\nJOB DESCRIPTION\n{job_description[:3000]}\n\n"
        f"CANDIDATE RESUME\n{resume_text[:3000]}\n\n"
        "Write the LinkedIn outreach message JSON."
    )

    raw = _call_provider(provider_cfg, api_key, user_message, max_tokens=500)
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    raw = re.sub(r"\s*```$", "", raw)
    result = json.loads(raw)

    # Ensure char_count is accurate
    full = result.get("full_message", "")
    result["char_count"] = len(full)
    return result


def _call_provider(
    cfg: dict,
    api_key: str,
    user_message: str,
    max_tokens: int = 500,
) -> str:
    provider_id = cfg.get("id", "")

    if provider_id == "claude":
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model=cfg.get("model", "claude-sonnet-4-6"),
            max_tokens=max_tokens,
            temperature=0.2,
            system=_OUTREACH_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )
        return resp.content[0].text

    if provider_id in ("gemini15", "gemini20", "gemini25"):
        from google import genai
        from google.genai import types as gtypes
        client = genai.Client(api_key=api_key)
        resp = client.models.generate_content(
            model=cfg.get("model", "gemini-2.0-flash"),
            contents=f"{_OUTREACH_PROMPT}\n\n{user_message}",
            config=gtypes.GenerateContentConfig(
                temperature=0.2,
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
        temperature=0.2,
        messages=[
            {"role": "system", "content": _OUTREACH_PROMPT},
            {"role": "user",   "content": user_message},
        ],
    )
    return resp.choices[0].message.content
