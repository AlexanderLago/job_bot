# utils/interview_prep.py — Interview preparation helpers

import json
import re

import requests
from bs4 import BeautifulSoup

from utils.job_scraper import scrape_job_url

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

_QUESTIONS_SYSTEM = (
    "You are an expert interview coach. Generate realistic interview questions that would actually "
    "be asked for this role at this company. Mix behavioral (STAR-format), technical, situational, "
    "and company-culture questions. Be specific to the role and company — avoid generic filler questions.\n\n"
    "Return ONLY a JSON array of question strings, no other text. "
    'Example: ["Question 1?", "Question 2?"]'
)

_RATE_SYSTEM = (
    "You are an expert interview coach evaluating a candidate's answer. "
    "Score the answer on a 0-100 scale considering: relevance to the question, "
    "use of STAR method (for behavioral), specificity, conciseness, and communication clarity.\n\n"
    "Return ONLY a JSON object with these exact keys:\n"
    '{"score": <int 0-100>, "feedback": "<1-2 sentence overview>", '
    '"strengths": ["<strength 1>", ...], "improvements": ["<improvement 1>", ...]}'
)


# ── Public API ─────────────────────────────────────────────────────────────────

def search_interview_content(company: str, role: str) -> str:
    """
    Search DuckDuckGo HTML for interview content about company+role.
    Returns up to 4000 chars of scraped text, or '' on any failure.
    Silently swallows all exceptions.
    """
    try:
        query = f"{company} {role} interview questions"
        resp = requests.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
            headers=_HEADERS,
            timeout=10,
        )
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        links = []
        for a in soup.select("a.result__a"):
            href = a.get("href", "")
            if href.startswith("http"):
                links.append(href)
            if len(links) >= 3:
                break
        for url in links:
            try:
                text, err = scrape_job_url(url)
                if text and len(text) > 200:
                    return text[:4000]
            except Exception:
                continue
    except Exception:
        pass
    return ""


def generate_questions(
    company: str,
    role: str,
    count: int,
    web_context: str,
    provider: dict,
    api_key: str,
) -> list:
    """
    Generate interview questions using the given AI provider.
    Returns a list of question strings (up to `count`).
    """
    context_part = (
        f"\n\nHere is some relevant web content about interviews for this role:\n{web_context[:2000]}"
        if web_context
        else ""
    )
    user_msg = (
        f"Generate exactly {count} realistic interview questions for a {role} position at {company}."
        f"{context_part}\n\n"
        "Return ONLY a JSON array of question strings."
    )
    raw = _ai_call(provider, api_key, _QUESTIONS_SYSTEM, user_msg, temperature=0.7, max_tokens=1024)
    parsed = _parse_list(raw)
    return [str(q) for q in parsed[:count]]


def rate_answer(
    company: str,
    role: str,
    question: str,
    answer: str,
    provider: dict,
    api_key: str,
) -> dict:
    """
    Rate a candidate's interview answer.
    Returns {score: int, feedback: str, strengths: list[str], improvements: list[str]}.
    """
    user_msg = (
        f"Role: {role} at {company}\n\n"
        f"Interview question: {question}\n\n"
        f"Candidate's answer: {answer}\n\n"
        "Evaluate this answer and return ONLY the JSON object."
    )
    raw = _ai_call(provider, api_key, _RATE_SYSTEM, user_msg, temperature=0.2, max_tokens=512)
    result = _parse_obj(raw)
    return {
        "score": int(result.get("score", 0)),
        "feedback": str(result.get("feedback", "")),
        "strengths": list(result.get("strengths", [])),
        "improvements": list(result.get("improvements", [])),
    }


# ── Internal helpers ───────────────────────────────────────────────────────────

def _ai_call(
    provider: dict,
    api_key: str,
    system: str,
    user: str,
    temperature: float,
    max_tokens: int,
) -> str:
    """Route the AI call to the correct backend based on provider type."""
    t = provider["type"]

    if t == "anthropic":
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)
        msg = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            temperature=temperature,
        )
        return msg.content[0].text

    if t == "gemini":
        from google import genai
        from google.genai import types as gtypes
        client = genai.Client(api_key=api_key)
        resp = client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=user,
            config=gtypes.GenerateContentConfig(
                system_instruction=system,
                temperature=temperature,
                max_output_tokens=max_tokens,
            ),
        )
        return resp.text

    if t == "oai":
        from utils.ai_providers import _call_oai
        return _call_oai(
            base_url=provider["base_url"],
            api_key=api_key,
            model=provider["model"],
            system=system,
            user=user,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    raise ValueError(f"Unknown provider type: {t}")


def _strip_fences(raw: str) -> str:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    raw = re.sub(r"<think>[\s\S]*?</think>\s*", "", raw).strip()
    return raw


def _parse_list(raw: str) -> list:
    try:
        result = json.loads(_strip_fences(raw))
        return result if isinstance(result, list) else []
    except Exception:
        return []


def _parse_obj(raw: str) -> dict:
    try:
        result = json.loads(_strip_fences(raw))
        return result if isinstance(result, dict) else {}
    except Exception:
        return {}
