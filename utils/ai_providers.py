# utils/ai_providers.py — unified multi-provider AI caller with auto-fallback

import json
import re

# ── Provider registry ──────────────────────────────────────────────────────────
# Order = priority for auto-cycling (best quality first).
# All entries with type="oai" use the OpenAI-compatible chat completions API.
PROVIDERS = [
    {
        "id": "anthropic",
        "label": "Claude 3.5 Sonnet",
        "key_name": "ANTHROPIC_API_KEY",
        "type": "anthropic",
        "free": False,
        "signup_url": "https://console.anthropic.com/",
    },
    {
        "id": "gemini",
        "label": "Gemini 2.0 Flash",
        "key_name": "GEMINI_API_KEY",
        "type": "gemini",
        "free": True,
        "signup_url": "https://aistudio.google.com/app/apikey",
    },
    {
        "id": "gemini15",
        "label": "Gemini 1.5 Flash",
        "key_name": "GEMINI_API_KEY",          # same key, separate rate limit pool
        "type": "oai",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "model": "gemini-1.5-flash",
        "free": True,
        "signup_url": "https://aistudio.google.com/app/apikey",
    },
    {
        "id": "groq",
        "label": "Llama 3.3 70B · Groq",
        "key_name": "GROQ_API_KEY",
        "type": "oai",
        "base_url": "https://api.groq.com/openai/v1",
        "model": "llama-3.3-70b-versatile",
        "free": True,
        "signup_url": "https://console.groq.com/keys",
    },
    {
        "id": "cerebras",
        "label": "Llama 3.1 70B · Cerebras",
        "key_name": "CEREBRAS_API_KEY",
        "type": "oai",
        "base_url": "https://api.cerebras.ai/v1",
        "model": "llama3.1-70b",
        "free": True,
        "signup_url": "https://inference.cerebras.ai/",
    },
    {
        "id": "sambanova",
        "label": "Llama 3.3 70B · SambaNova",
        "key_name": "SAMBANOVA_API_KEY",
        "type": "oai",
        "base_url": "https://api.sambanova.ai/v1",
        "model": "Meta-Llama-3.3-70B-Instruct",
        "free": True,
        "signup_url": "https://cloud.sambanova.ai/",
    },
    {
        "id": "openrouter",
        "label": "Llama 3.3 70B · OpenRouter",
        "key_name": "OPENROUTER_API_KEY",
        "type": "oai",
        "base_url": "https://openrouter.ai/api/v1",
        "model": "meta-llama/llama-3.3-70b-instruct:free",
        "free": True,
        "signup_url": "https://openrouter.ai/keys",
    },
    {
        "id": "zhipu",
        "label": "GLM-4-Flash · Zhipu AI (z.ai)",
        "key_name": "ZHIPU_API_KEY",
        "type": "oai",
        "base_url": "https://open.bigmodel.cn/api/paas/v4/",
        "model": "glm-4-flash",
        "free": True,
        "signup_url": "https://z.ai/",
    },
]


class ProviderRateLimitError(Exception):
    """Raised when a provider returns HTTP 429 / quota exhausted."""
    pass


# ── Internal helpers ───────────────────────────────────────────────────────────

def _parse_json(raw: str) -> dict:
    raw = raw.strip()
    # Strip markdown fences
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    # Strip <think>...</think> blocks (DeepSeek R1 / reasoning models)
    raw = re.sub(r"<think>[\s\S]*?</think>\s*", "", raw).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"AI returned invalid JSON: {e}\n\nRaw output:\n{raw[:500]}")


def _tailor_user_msg(resume_text: str, jd: str, temperature: float) -> str:
    tone = (
        "be conservative, stay close to original language" if temperature < 0.4
        else "be creative with rewording and verb choices" if temperature > 0.6
        else "balanced rewording"
    )
    return (
        f"Here is the candidate's current resume:\n\n<resume>\n{resume_text}\n</resume>\n\n"
        f"Here is the job description to tailor the resume for:\n\n"
        f"<job_description>\n{jd}\n</job_description>\n\n"
        f"Temperature setting: {temperature:.2f} ({tone})\n\n"
        "Please tailor this resume following all rules in your instructions. "
        "Return ONLY the JSON object, nothing else."
    )


def _score_user_msg(resume_text: str, jd: str) -> str:
    return (
        f"Here is the candidate's resume:\n\n<resume>\n{resume_text}\n</resume>\n\n"
        f"Here is the job description:\n\n<job_description>\n{jd}\n</job_description>\n\n"
        "Score the resume against the job description. Return ONLY the JSON object."
    )


def _is_rate_limit(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(x in msg for x in ("429", "rate_limit", "rate limit", "resource_exhausted", "quota"))


def _call_oai(base_url: str, api_key: str, model: str, system: str, user: str,
               temperature: float, max_tokens: int) -> str:
    """Make an OpenAI-compatible chat completion request."""
    from openai import OpenAI, RateLimitError as OAIRateLimitError
    client = OpenAI(api_key=api_key, base_url=base_url)
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content or ""
    except OAIRateLimitError as e:
        raise ProviderRateLimitError(str(e))
    except Exception as e:
        if _is_rate_limit(e):
            raise ProviderRateLimitError(str(e))
        raise


# ── Public API ─────────────────────────────────────────────────────────────────

def call_tailor(provider: dict, api_key: str, resume_text: str, jd: str, temperature: float) -> dict:
    """Tailor the resume using the given provider. Raises ProviderRateLimitError on 429."""
    t = provider["type"]

    if t == "anthropic":
        from utils.ai_tailor import tailor_resume
        try:
            return tailor_resume(resume_text, jd, api_key, temperature)
        except Exception as e:
            if _is_rate_limit(e):
                raise ProviderRateLimitError(str(e))
            raise

    if t == "gemini":
        from utils.gemini_tailor import tailor_resume_gemini
        try:
            return tailor_resume_gemini(resume_text, jd, api_key, temperature)
        except Exception as e:
            if _is_rate_limit(e):
                raise ProviderRateLimitError(str(e))
            raise

    if t == "oai":
        from utils.ai_tailor import SYSTEM_PROMPT
        raw = _call_oai(
            base_url=provider["base_url"],
            api_key=api_key,
            model=provider["model"],
            system=SYSTEM_PROMPT,
            user=_tailor_user_msg(resume_text, jd, temperature),
            temperature=temperature,
            max_tokens=4096,
        )
        return _parse_json(raw)

    raise ValueError(f"Unknown provider type: {t}")


def call_score(provider: dict, api_key: str, resume_text: str, jd: str) -> dict:
    """Score the resume using the given provider. Raises ProviderRateLimitError on 429."""
    t = provider["type"]

    if t == "anthropic":
        from utils.scorer import score_resume
        try:
            return score_resume(resume_text, jd, api_key)
        except Exception as e:
            if _is_rate_limit(e):
                raise ProviderRateLimitError(str(e))
            raise

    if t == "gemini":
        from utils.gemini_scorer import score_resume_gemini
        try:
            return score_resume_gemini(resume_text, jd, api_key)
        except Exception as e:
            if _is_rate_limit(e):
                raise ProviderRateLimitError(str(e))
            raise

    if t == "oai":
        from utils.scorer import _SYSTEM_PROMPT
        raw = _call_oai(
            base_url=provider["base_url"],
            api_key=api_key,
            model=provider["model"],
            system=_SYSTEM_PROMPT,
            user=_score_user_msg(resume_text, jd),
            temperature=0.1,
            max_tokens=1024,
        )
        return _parse_json(raw)

    raise ValueError(f"Unknown provider type: {t}")
