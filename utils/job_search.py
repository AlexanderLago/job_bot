# utils/job_search.py — Adzuna job search API wrapper + AI keyword extractor

import re
from datetime import datetime

import requests

from utils.interview_prep import _ai_call, _parse_list

_COUNTRY_LABELS = {
    "us": "United States",
    "gb": "United Kingdom",
    "au": "Australia",
    "ca": "Canada",
    "de": "Germany",
    "fr": "France",
    "nl": "Netherlands",
    "sg": "Singapore",
    "nz": "New Zealand",
    "za": "South Africa",
    "br": "Brazil",
    "in": "India",
    "pl": "Poland",
    "mx": "Mexico",
    "it": "Italy",
    "es": "Spain",
    "at": "Austria",
    "be": "Belgium",
    "ch": "Switzerland",
    "ru": "Russia",
}

_ADZUNA_BASE = "https://api.adzuna.com/v1/api/jobs"

_KEYWORDS_SYSTEM = (
    "You are a job search expert. Given a candidate's resume, extract 3-5 specific job title "
    "strings that best match their experience and skills. Focus on titles they are most qualified "
    "for based on their work history and skills.\n\n"
    "Return ONLY a JSON array of job title strings, no other text. "
    'Example: ["Data Analyst", "Business Intelligence Analyst", "Data Scientist"]'
)


def search_jobs(
    app_id: str,
    app_key: str,
    what: str,
    where: str = "",
    country: str = "us",
    page: int = 1,
    results_per_page: int = 10,
    full_time: bool = False,
) -> tuple:
    """
    Search Adzuna for job listings.
    Returns (results: list[dict], total_count: int, error: str|None)
    """
    params = {
        "app_id": app_id,
        "app_key": app_key,
        "results_per_page": results_per_page,
        "content-type": "application/json",
    }
    if what.strip():
        params["what"] = what.strip()
    if where.strip():
        params["where"] = where.strip()
    if full_time:
        params["full_time"] = 1

    url = f"{_ADZUNA_BASE}/{country}/search/{page}"

    try:
        resp = requests.get(url, params=params, timeout=15)
    except requests.ConnectionError:
        return [], 0, "Connection error — check your internet connection."
    except requests.Timeout:
        return [], 0, "Request timed out — Adzuna may be slow. Try again."

    if resp.status_code in (401, 403):
        return [], 0, "Invalid Adzuna credentials — check your App ID and App Key."
    if resp.status_code == 400:
        return [], 0, "Invalid search request — try different search terms."
    if not resp.ok:
        return [], 0, f"Adzuna API error ({resp.status_code}) — try again shortly."

    try:
        data = resp.json()
    except Exception:
        return [], 0, "Could not parse Adzuna response."

    total = data.get("count", 0)
    raw_results = data.get("results", [])
    results = [_normalise_job(j) for j in raw_results]
    return results, total, None


def generate_search_keywords(resume_text: str, provider: dict, api_key: str) -> list:
    """
    Use AI to extract 3-5 job title strings from a resume.
    Returns a list of strings.
    """
    user_msg = (
        f"Here is the candidate's resume:\n\n{resume_text[:3000]}\n\n"
        "Extract 3-5 specific job title strings that best match this candidate's experience. "
        "Return ONLY a JSON array of job title strings."
    )
    raw = _ai_call(provider, api_key, _KEYWORDS_SYSTEM, user_msg, temperature=0.2, max_tokens=256)
    return [str(t) for t in _parse_list(raw)]


# ── Internal helpers ───────────────────────────────────────────────────────────

def _normalise_job(job: dict) -> dict:
    """Flatten an Adzuna job object into a clean dict."""
    salary_min = job.get("salary_min")
    salary_max = job.get("salary_max")

    if salary_min and salary_max:
        salary_display = f"${salary_min:,.0f} – ${salary_max:,.0f}"
    elif salary_min:
        salary_display = f"${salary_min:,.0f}+"
    elif salary_max:
        salary_display = f"Up to ${salary_max:,.0f}"
    else:
        salary_display = "Not specified"

    desc = job.get("description", "")
    if len(desc) > 400:
        desc = desc[:397] + "…"

    posted_raw = job.get("created", "")
    try:
        posted_date = datetime.fromisoformat(posted_raw.replace("Z", "+00:00")).strftime("%b %d, %Y")
    except Exception:
        posted_date = posted_raw[:10] if posted_raw else ""

    location = job.get("location", {})
    location_str = location.get("display_name", "") if isinstance(location, dict) else str(location)

    company = job.get("company", {})
    company_str = company.get("display_name", "") if isinstance(company, dict) else str(company)

    category = job.get("category", {})
    category_str = category.get("label", "") if isinstance(category, dict) else str(category)

    return {
        "title": job.get("title", ""),
        "company": company_str,
        "location": location_str,
        "salary_min": salary_min,
        "salary_max": salary_max,
        "salary_display": salary_display,
        "description": desc,
        "url": job.get("redirect_url", ""),
        "posted_date": posted_date,
        "category": category_str,
    }
