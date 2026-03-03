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
        "label": "Gemini 3 Flash Preview",
        "key_name": "GEMINI_API_KEY",
        "type": "gemini",
        "free": True,
        "signup_url": "https://aistudio.google.com/app/apikey",
    },
    {
        "id": "gemini15",
        "label": "Gemini 2.5 Flash Lite",
        "key_name": "GEMINI_API_KEY",          # same key, separate rate limit pool
        "type": "oai",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "model": "gemini-2.5-flash-lite",
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
        "label": "GPT-OSS 120B · Cerebras",
        "key_name": "CEREBRAS_API_KEY",
        "type": "oai",
        "base_url": "https://api.cerebras.ai/v1",
        "model": "gpt-oss-120b",
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
        "extra_headers": {"HTTP-Referer": "https://github.com/AlexanderLago/job_bot", "X-Title": "Job Bot"},
    },
    {
        "id": "zhipu",
        "label": "GLM-4.5-Flash · Zhipu AI (z.ai)",
        "key_name": "ZHIPU_API_KEY",
        "type": "oai",
        "base_url": "https://open.bigmodel.cn/api/paas/v4/",
        "model": "glm-4.5-flash",
        "free": True,
        "signup_url": "https://z.ai/",
    },
    # ── Extra OpenRouter slots — same key, different model = separate rate limit pool ──
    {
        "id": "openrouter2",
        "label": "Gemma 3 27B · OpenRouter",
        "key_name": "OPENROUTER_API_KEY",
        "type": "oai",
        "base_url": "https://openrouter.ai/api/v1",
        "model": "google/gemma-3-27b-it:free",
        "free": True,
        "signup_url": "https://openrouter.ai/keys",
        "extra_headers": {"HTTP-Referer": "https://github.com/AlexanderLago/job_bot", "X-Title": "Job Bot"},
    },
    {
        "id": "openrouter3",
        "label": "Mistral 7B · OpenRouter",
        "key_name": "OPENROUTER_API_KEY",
        "type": "oai",
        "base_url": "https://openrouter.ai/api/v1",
        "model": "mistralai/mistral-7b-instruct:free",
        "free": True,
        "signup_url": "https://openrouter.ai/keys",
        "extra_headers": {"HTTP-Referer": "https://github.com/AlexanderLago/job_bot", "X-Title": "Job Bot"},
    },
    # ── Additional free-tier providers ────────────────────────────────────────
    {
        "id": "together",
        "label": "Llama 3.3 70B · Together AI",
        "key_name": "TOGETHER_API_KEY",
        "type": "oai",
        "base_url": "https://api.together.xyz/v1",
        "model": "meta-llama/Llama-3.3-70B-Instruct-Turbo-Free",
        "free": True,
        "signup_url": "https://api.together.xyz/",
    },
    {
        "id": "mistral",
        "label": "Mistral Nemo · Mistral AI",
        "key_name": "MISTRAL_API_KEY",
        "type": "oai",
        "base_url": "https://api.mistral.ai/v1",
        "model": "open-mistral-nemo",
        "free": True,
        "signup_url": "https://console.mistral.ai/",
    },
    {
        "id": "fireworks",
        "label": "Llama 3.1 70B · Fireworks AI",
        "key_name": "FIREWORKS_API_KEY",
        "type": "oai",
        "base_url": "https://api.fireworks.ai/inference/v1",
        "model": "accounts/fireworks/models/llama-v3p1-70b-instruct",
        "free": True,
        "signup_url": "https://fireworks.ai/",
    },
    {
        "id": "deepinfra",
        "label": "Llama 3.1 70B · DeepInfra",
        "key_name": "DEEPINFRA_API_KEY",
        "type": "oai",
        "base_url": "https://api.deepinfra.com/v1/openai",
        "model": "meta-llama/Meta-Llama-3.1-70B-Instruct",
        "free": True,
        "signup_url": "https://deepinfra.com/",
    },
    {
        "id": "hyperbolic",
        "label": "Llama 3.1 70B · Hyperbolic",
        "key_name": "HYPERBOLIC_API_KEY",
        "type": "oai",
        "base_url": "https://api.hyperbolic.xyz/v1",
        "model": "meta-llama/Meta-Llama-3.1-70B-Instruct",
        "free": True,
        "signup_url": "https://app.hyperbolic.xyz/",
    },
    {
        "id": "nvidia",
        "label": "Llama 3.3 70B · NVIDIA NIM",
        "key_name": "NVIDIA_API_KEY",
        "type": "oai",
        "base_url": "https://integrate.api.nvidia.com/v1",
        "model": "meta/llama-3.3-70b-instruct",
        "free": True,
        "signup_url": "https://build.nvidia.com/",
    },
    {
        "id": "github",
        "label": "Llama 3.3 70B · GitHub Models",
        "key_name": "GITHUB_TOKEN",
        "type": "oai",
        "base_url": "https://models.inference.ai.azure.com",
        "model": "Llama-3.3-70B-Instruct",
        "free": True,
        "signup_url": "https://github.com/settings/tokens",
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


def _tailor_user_msg(resume_text: str, jd: str, temperature: float, preserve_structure: bool = False) -> str:
    tone = (
        "be conservative, stay close to original language" if temperature < 0.4
        else "be creative with rewording and verb choices" if temperature > 0.6
        else "balanced rewording"
    )
    ps_block = (
        "\n\nSTRUCTURE PRESERVATION MODE IS ACTIVE — this overrides restructuring guidance:\n"
        "- Do NOT change the order of sections, jobs, or bullet points\n"
        "- Do NOT add or remove bullet points — only rephrase existing ones in place\n"
        "- Keep the summary the same length and general structure as the original\n"
        "- You MAY add implied skills and new entries to the Skills section\n"
        "- Weave keywords into existing bullets only where natural, without changing bullet count or order\n"
        "- Preserve the candidate's voice and phrasing as much as possible\n"
    ) if preserve_structure else ""
    return (
        f"Here is the candidate's current resume:\n\n<resume>\n{resume_text}\n</resume>\n\n"
        f"Here is the job description to tailor the resume for:\n\n"
        f"<job_description>\n{jd}\n</job_description>\n\n"
        f"Temperature setting: {temperature:.2f} ({tone})"
        f"{ps_block}\n\n"
        "Please tailor this resume following all rules in your instructions. "
        "Return ONLY the JSON object, nothing else."
    )


def _score_user_msg(resume_text: str, jd: str) -> str:
    return (
        f"Here is the candidate's resume:\n\n<resume>\n{resume_text}\n</resume>\n\n"
        f"Here is the job description:\n\n<job_description>\n{jd}\n</job_description>\n\n"
        "Score the resume against the job description. Return ONLY the JSON object."
    )


def _should_skip(exc: Exception) -> bool:
    """Return True for any error that means we should skip to the next provider."""
    msg = str(exc).lower()
    return any(x in msg for x in (
        "429", "rate_limit", "rate limit", "resource_exhausted", "quota",   # rate limits
        "503", "unavailable", "high demand", "service unavailable",         # overload / Gemini 503
        "404", "not found", "not_found", "no such model", "does not exist", # bad model/endpoint
        "401", "403", "unauthorized", "invalid api key", "invalid_api_key", # auth failures
        "authentication", "forbidden", "permission denied",
        "timeout", "timed out", "connecttimeout", "connection error",       # network failures
    ))


def _call_oai(base_url: str, api_key: str, model: str, system: str, user: str,
               temperature: float, max_tokens: int, extra_headers: dict = None) -> str:
    """Make an OpenAI-compatible chat completion request."""
    from openai import (OpenAI, RateLimitError as OAIRateLimitError,
                        NotFoundError as OAINotFoundError,
                        APITimeoutError as OAITimeoutError,
                        APIConnectionError as OAIConnError)
    client = OpenAI(api_key=api_key, base_url=base_url,
                    default_headers=extra_headers or {})
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
    except (OAIRateLimitError, OAINotFoundError, OAITimeoutError, OAIConnError) as e:
        raise ProviderRateLimitError(str(e))
    except Exception as e:
        if _should_skip(e):
            raise ProviderRateLimitError(str(e))
        raise


# ── Public API ─────────────────────────────────────────────────────────────────

def call_tailor(provider: dict, api_key: str, resume_text: str, jd: str, temperature: float,
                preserve_structure: bool = False) -> dict:
    """Tailor the resume using the given provider. Raises ProviderRateLimitError on 429."""
    t = provider["type"]

    if t == "anthropic":
        from utils.ai_tailor import tailor_resume
        try:
            return tailor_resume(resume_text, jd, api_key, temperature, preserve_structure)
        except Exception as e:
            if _should_skip(e):
                raise ProviderRateLimitError(str(e))
            raise

    if t == "gemini":
        from utils.gemini_tailor import tailor_resume_gemini
        try:
            return tailor_resume_gemini(resume_text, jd, api_key, temperature, preserve_structure)
        except Exception as e:
            if _should_skip(e):
                raise ProviderRateLimitError(str(e))
            raise

    if t == "oai":
        from utils.ai_tailor import SYSTEM_PROMPT
        raw = _call_oai(
            base_url=provider["base_url"],
            api_key=api_key,
            model=provider["model"],
            system=SYSTEM_PROMPT,
            user=_tailor_user_msg(resume_text, jd, temperature, preserve_structure),
            temperature=temperature,
            max_tokens=4096,
            extra_headers=provider.get("extra_headers"),
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
            if _should_skip(e):
                raise ProviderRateLimitError(str(e))
            raise

    if t == "gemini":
        from utils.gemini_scorer import score_resume_gemini
        try:
            return score_resume_gemini(resume_text, jd, api_key)
        except Exception as e:
            if _should_skip(e):
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
            extra_headers=provider.get("extra_headers"),
        )
        return _parse_json(raw)

    raise ValueError(f"Unknown provider type: {t}")
