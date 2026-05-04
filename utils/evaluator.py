# utils/evaluator.py — Multi-dimensional job evaluation engine
# Inspired by career-ops (github.com/santifer/career-ops)
#
# Evaluates a job opportunity across 10 weighted dimensions and detects the
# role archetype, returning an A-F grade with a structured report.

import json
import re

# ── Role archetypes ────────────────────────────────────────────────────────────
ARCHETYPES = {
    "Agentic AI":         "Agents, LLMs, RAG, prompt engineering, Claude/GPT/Gemini",
    "Platform / MLOps":   "Infrastructure, pipelines, model deployment, DevOps/MLOps",
    "Technical PM":       "Product, roadmap, PRD, stakeholder management, go-to-market",
    "Solutions Architect":"Customer-facing, demos, pre-sales, system integration",
    "Forward Deployed":   "Customer success, implementation, onboarding, enterprise delivery",
    "Transformation Lead":"Change management, strategy, consulting, digital transformation",
}

# ── Dimension definitions (name, weight) ──────────────────────────────────────
DIMENSIONS = [
    ("Role Alignment",    0.18),  # matches user's target roles / career goals
    ("Resume Match",      0.20),  # keyword & experience overlap
    ("Seniority Fit",     0.10),  # level matches candidate's experience
    ("Compensation",      0.12),  # salary range vs expectations
    ("Growth Potential",  0.10),  # career growth opportunity
    ("Remote / Location", 0.08),  # work arrangement matches preferences
    ("Company Quality",   0.08),  # reputation, funding, stage signals
    ("Tech Stack",        0.08),  # technology alignment
    ("Culture Signals",   0.04),  # team / culture fit indicators
    ("Role Clarity",      0.02),  # how well-defined and realistic the role is
]

_GRADE_TABLE = [
    (85, "A", "Apply immediately — strong fit across the board."),
    (70, "B", "Apply — good fit, minor gaps that can be addressed."),
    (55, "C", "Borderline — apply selectively; tailor carefully."),
    (40, "D", "Weak fit — significant gaps; consider skipping."),
    (0,  "F", "Poor fit — not recommended."),
]

_SYSTEM_PROMPT = f"""You are a senior career coach and ATS specialist evaluating job fit.

Given a candidate's resume, a job description, and the candidate's profile, produce:
1. The most likely role ARCHETYPE from this list:
   {", ".join(ARCHETYPES.keys())}

2. Numeric scores (0–10) for each of these dimensions:
   {", ".join(d[0] for d in DIMENSIONS)}

   Scoring each dimension:
   - Role Alignment: does this role fit the candidate's stated target roles/goals?
   - Resume Match: how many keywords/skills/experience items overlap?
   - Seniority Fit: is the seniority level right for the candidate?
   - Compensation: if a range is visible, how close to the candidate's expectation?
     Score 5 if unknown.
   - Growth Potential: does the role offer career growth?
   - Remote / Location: does the work arrangement match the candidate's preference?
     Score 5 if unknown.
   - Company Quality: signals of company health (funding, brand, reviews)?
   - Tech Stack: do the required tools/languages match the candidate's skills?
   - Culture Signals: positive language, team size, values statements?
   - Role Clarity: is the role well-defined with clear responsibilities?

3. Two to three STAR-story prompts tailored to this JD — each as one sentence
   starting with "Tell me about a time you..." or "Describe a situation where..."

4. Up to 8 critical ATS keywords from the JD that are NOT already prominent
   in the resume (surface, don't invent new skills).

Return ONLY valid JSON — no markdown, no prose, no explanation:
{{
  "archetype": "<one of the archetype names>",
  "dimension_scores": {{
    "Role Alignment": <0-10>,
    "Resume Match": <0-10>,
    "Seniority Fit": <0-10>,
    "Compensation": <0-10>,
    "Growth Potential": <0-10>,
    "Remote / Location": <0-10>,
    "Company Quality": <0-10>,
    "Tech Stack": <0-10>,
    "Culture Signals": <0-10>,
    "Role Clarity": <0-10>
  }},
  "star_prompts": ["...", "...", "..."],
  "keywords_to_inject": ["...", "..."],
  "brief_reasoning": "<2-3 sentence summary of why this grade>"
}}"""

_FULL_REPORT_PROMPT = """You are a senior career coach producing a structured evaluation report.

Given the candidate's resume, job description, and profile, produce a JSON report with these exact keys:

{
  "role_summary": {
    "archetype": "<archetype name>",
    "domain": "<e.g. Agentic AI, MLOps, Product>",
    "seniority": "<e.g. Senior, Staff, Lead>",
    "work_arrangement": "<Remote / Hybrid / On-site / Unknown>",
    "tldr": "<2-3 sentence plain-English summary of the role and whether the candidate should pursue it>"
  },
  "cv_match": {
    "strengths": ["<exact CV experience that maps to a requirement>", ...],
    "gaps": [{"gap": "<missing skill/exp>", "mitigation": "<how to address or frame>"}, ...],
    "match_summary": "<paragraph summarizing overall CV-to-JD fit>"
  },
  "level_strategy": {
    "positioning": "<how to position seniority — e.g. 'lean into strategic scope'>",
    "talking_points": ["<specific angle to emphasize in interviews>", ...],
    "watch_out": "<one key risk or red flag to navigate>"
  },
  "comp_market": {
    "estimated_range": "<e.g. $150-180k base + equity based on JD signals>",
    "positioning": "<advice on negotiation stance>",
    "notes": "<any comp-related signals from the JD>"
  },
  "resume_tips": {
    "summary_tweak": "<suggested 1-sentence rewrite of resume headline/summary for this role>",
    "bullets_to_add": ["<new bullet point to strengthen fit>", ...],
    "keywords_missing": ["<ATS keyword in JD not in resume>", ...]
  },
  "star_stories": [
    {
      "prompt": "<interview question this story answers>",
      "situation": "<2-3 sentences>",
      "task": "<1-2 sentences>",
      "action": "<2-3 sentences of specific actions taken>",
      "result": "<quantified outcome>",
      "reflection": "<what you learned / would do differently>"
    }
  ]
}

Include 3-4 STAR stories. Each story must use experiences from the actual resume — no fabrication.
Return ONLY valid JSON. No markdown, no prose."""


def generate_full_report(
    resume_text: str,
    job_description: str,
    provider_cfg: dict,
    api_key: str,
    user_profile: dict | None = None,
) -> dict:
    """
    Generate a deep A-F style evaluation report (career-ops style).
    Separate from evaluate_job() — call this after the user decides to dig deeper.
    """
    profile = user_profile or {}
    target_roles = ", ".join(profile.get("target_roles", [])) or "Not specified"
    min_salary   = profile.get("min_salary", 0)
    remote_pref  = profile.get("remote_pref", "Any")

    profile_block = (
        f"Target roles: {target_roles}\n"
        f"Min salary: {'${:,}/yr'.format(min_salary) if min_salary else 'Not specified'}\n"
        f"Remote preference: {remote_pref}"
    )

    user_message = f"""CANDIDATE PROFILE
{profile_block}

RESUME
{resume_text[:7000]}

JOB DESCRIPTION
{job_description[:6000]}

Generate the full evaluation report JSON."""

    raw = _call_provider(
        provider_cfg, api_key, user_message,
        system=_FULL_REPORT_PROMPT,
        max_tokens=3000,
    )
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)


def evaluate_job(
    resume_text: str,
    job_description: str,
    provider_cfg: dict,
    api_key: str,
    user_profile: dict | None = None,
) -> dict:
    """
    Evaluate job fit across 10 dimensions.

    Parameters
    ----------
    resume_text     : Plain-text resume content.
    job_description : Full job description text.
    provider_cfg    : Provider config dict (id, label, model, …).
    api_key         : API key for the selected provider.
    user_profile    : Optional dict with keys:
                        target_roles (list[str])
                        min_salary   (int, USD/yr, 0 = unknown)
                        remote_pref  ("Remote" | "Hybrid" | "On-site" | "Any")
                        location     (str)

    Returns
    -------
    dict with keys: archetype, grade, overall_score, dimension_scores,
                    recommendation, reasoning, star_prompts, keywords_to_inject
    """
    profile = user_profile or {}
    target_roles = ", ".join(profile.get("target_roles", [])) or "Not specified"
    min_salary   = profile.get("min_salary", 0)
    remote_pref  = profile.get("remote_pref", "Any")
    location     = profile.get("location", "Not specified")

    profile_block = (
        f"Target roles: {target_roles}\n"
        f"Minimum salary expectation: {'${:,}/yr'.format(min_salary) if min_salary else 'Not specified'}\n"
        f"Remote preference: {remote_pref}\n"
        f"Preferred location: {location}"
    )

    user_message = f"""CANDIDATE PROFILE
{profile_block}

RESUME
{resume_text[:6000]}

JOB DESCRIPTION
{job_description[:6000]}

Evaluate the fit and return the JSON object."""

    # ── Call provider ──────────────────────────────────────────────────────────
    raw = _call_provider(provider_cfg, api_key, user_message)

    # ── Parse + compute grade ─────────────────────────────────────────────────
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip())
    raw = re.sub(r"\s*```$", "", raw)
    data = json.loads(raw)

    dim_scores = data.get("dimension_scores", {})
    overall = _weighted_score(dim_scores)
    grade, recommendation, grade_reason = _grade(overall)

    return {
        "archetype":          data.get("archetype", "Unknown"),
        "grade":              grade,
        "overall_score":      overall,
        "dimension_scores":   dim_scores,
        "recommendation":     recommendation,
        "reasoning":          data.get("brief_reasoning", grade_reason),
        "star_prompts":       data.get("star_prompts", []),
        "keywords_to_inject": data.get("keywords_to_inject", []),
    }


# ── Helpers ────────────────────────────────────────────────────────────────────

def _weighted_score(dim_scores: dict) -> int:
    total, weight_sum = 0.0, 0.0
    for name, weight in DIMENSIONS:
        score = dim_scores.get(name, 5)
        total += score * weight
        weight_sum += weight
    if weight_sum == 0:
        return 50
    return round((total / weight_sum) * 10)  # scale 0-10 → 0-100


def _grade(score: int) -> tuple[str, str, str]:
    for threshold, letter, reason in _GRADE_TABLE:
        if score >= threshold:
            if letter in ("A", "B"):
                rec = "Apply"
            elif letter == "C":
                rec = "Borderline"
            else:
                rec = "Skip"
            return letter, rec, reason
    return "F", "Skip", _GRADE_TABLE[-1][2]


def _call_provider(
    cfg: dict,
    api_key: str,
    user_message: str,
    system: str | None = None,
    max_tokens: int = 1500,
) -> str:
    """Route to the correct provider SDK and return the raw text response."""
    provider_id = cfg.get("id", "")
    sys_prompt = system if system is not None else _SYSTEM_PROMPT

    if provider_id == "claude":
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model=cfg.get("model", "claude-sonnet-4-6"),
            max_tokens=max_tokens,
            temperature=0.1,
            system=sys_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        return resp.content[0].text

    if provider_id in ("gemini15", "gemini20", "gemini25"):
        from google import genai
        from google.genai import types as gtypes
        client = genai.Client(api_key=api_key)
        resp = client.models.generate_content(
            model=cfg.get("model", "gemini-2.0-flash"),
            contents=f"{sys_prompt}\n\n{user_message}",
            config=gtypes.GenerateContentConfig(
                temperature=0.1,
                max_output_tokens=max_tokens,
            ),
        )
        return resp.text

    # OpenAI-compatible fallback (Groq, Cerebras, SambaNova, OpenRouter, etc.)
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
            {"role": "system", "content": sys_prompt},
            {"role": "user",   "content": user_message},
        ],
    )
    return resp.choices[0].message.content
