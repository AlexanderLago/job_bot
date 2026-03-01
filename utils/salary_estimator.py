# utils/salary_estimator.py — Salary extraction, web search, and AI estimator

import re

import requests
from bs4 import BeautifulSoup

from utils.job_scraper import scrape_job_url
from utils.interview_prep import _ai_call, _parse_obj

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

_SALARY_PATTERNS = [
    r"\$[\d,]+\s*[-–]\s*\$[\d,]+",
    r"\$[\d,]+[kK]?\s*(?:to|–|-)\s*\$?[\d,]+[kK]?",
    r"(?:salary|compensation|pay)[^\n]*\$[\d,]+",
    r"\$[\d,]+(?:\.\d+)?[kK]?\s*(?:per\s+(?:year|annum|yr))?",
]

_ESTIMATE_SYSTEM = (
    "You are an expert compensation analyst and career coach. "
    "Your job is to give a candidate a specific dollar figure they should ask for "
    "in salary negotiations — not a range, but a single recommended number.\n\n"
    "Given the candidate's resume, job description, market salary data, role, and location, "
    "produce a structured salary estimate. Account for the candidate's years of experience, "
    "skills match to the job description, location cost-of-living, and seniority implied by "
    "the resume versus the JD.\n\n"
    "Return ONLY a JSON object with these exact keys:\n"
    '{"market_low": <int>, "market_mid": <int>, "market_high": <int>, '
    '"recommended_ask": <int>, "reasoning": "<3-4 sentences>", '
    '"negotiation_tips": ["<tip 1>", "<tip 2>", ...], '
    '"data_sources": ["<source 1>", ...]}'
)


def extract_salary_from_jd(jd_text: str) -> dict | None:
    """
    Try to find a salary figure in the job description using regex.
    Returns {"min": int, "max": int, "raw": str} if found, else None.
    """
    for pattern in _SALARY_PATTERNS:
        match = re.search(pattern, jd_text, re.IGNORECASE)
        if match:
            raw = match.group(0).strip()
            numbers = re.findall(r"\d[\d,]*", raw)
            parsed = []
            for n in numbers:
                val = int(n.replace(",", ""))
                if val < 1000:  # treat as thousands (e.g. "$80k")
                    val *= 1000
                parsed.append(val)
            if len(parsed) >= 2:
                return {"min": min(parsed), "max": max(parsed), "raw": raw}
            if len(parsed) == 1:
                return {"min": parsed[0], "max": parsed[0], "raw": raw}
    return None


def search_salary_data(job_title: str, location: str) -> str:
    """
    DuckDuckGo search for salary data → scrape top 3 pages → return up to 4000 chars.
    Returns empty string on any failure.
    """
    from datetime import datetime
    year = datetime.now().year
    query = f"{job_title} salary {location} {year}"
    try:
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


def estimate_salary(
    resume_text: str,
    jd_text: str,
    job_title: str,
    location: str,
    market_data: str,
    jd_salary: dict | None,
    provider: dict,
    api_key: str,
) -> dict:
    """
    Use AI to estimate salary target based on resume, JD, and market data.
    Returns dict with market_low, market_mid, market_high, recommended_ask,
    reasoning, negotiation_tips, data_sources.
    """
    sources = []
    if jd_salary:
        sources.append("salary range found in job description")
    if market_data:
        sources.append("web salary research")

    jd_salary_note = (
        f"\n\nSalary found in job description: {jd_salary['raw']} "
        f"(${jd_salary['min']:,} – ${jd_salary['max']:,})"
        if jd_salary
        else ""
    )

    market_note = (
        f"\n\nMarket salary data from web research:\n{market_data[:2000]}"
        if market_data
        else ""
    )

    user_msg = (
        f"Job Title: {job_title}\n"
        f"Location: {location or 'Not specified'}\n"
        f"{jd_salary_note}"
        f"{market_note}\n\n"
        f"Candidate Resume:\n{resume_text[:2000]}\n\n"
        f"Job Description:\n{jd_text[:1500]}\n\n"
        "Analyze the above and produce the salary estimate JSON."
    )

    raw = _ai_call(
        provider, api_key, _ESTIMATE_SYSTEM, user_msg,
        temperature=0.2, max_tokens=1024,
    )
    result = _parse_obj(raw)

    # Ensure required fields with sensible defaults
    def _int(key: str) -> int:
        try:
            return int(result.get(key, 0))
        except (TypeError, ValueError):
            return 0

    final_sources = list(result.get("data_sources", sources)) or sources or ["AI analysis"]
    return {
        "market_low": _int("market_low"),
        "market_mid": _int("market_mid"),
        "market_high": _int("market_high"),
        "recommended_ask": _int("recommended_ask"),
        "reasoning": str(result.get("reasoning", "")),
        "negotiation_tips": [str(t) for t in result.get("negotiation_tips", [])],
        "data_sources": final_sources,
    }
