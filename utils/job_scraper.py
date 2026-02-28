# utils/job_scraper.py — Fetch a job posting URL and extract readable text

import requests
from bs4 import BeautifulSoup


_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# Tags that contain no useful job-description text
_STRIP_TAGS = ["script", "style", "nav", "header", "footer", "aside", "noscript"]


def scrape_job_url(url: str) -> tuple[str, str]:
    """
    Fetch a job posting URL and extract the visible text.

    Returns:
        (text, None)  on success  — text is the extracted job description
        (None, error) on failure  — error is a human-readable message
    """
    try:
        resp = requests.get(url, headers=_HEADERS, timeout=15, allow_redirects=True)
        resp.raise_for_status()
    except requests.exceptions.Timeout:
        return None, "The page took too long to respond (>15 s). Try pasting the job description instead."
    except requests.exceptions.TooManyRedirects:
        return None, "Too many redirects — this URL may require a login. Try pasting the job description instead."
    except requests.exceptions.HTTPError as e:
        code = e.response.status_code if e.response is not None else "?"
        if code in (403, 401):
            return None, f"Access denied (HTTP {code}). This site blocks automated access. Please paste the job description instead."
        return None, f"HTTP {code} error fetching the page. Try pasting the job description instead."
    except requests.exceptions.RequestException as e:
        return None, f"Could not fetch URL: {e}. Try pasting the job description instead."

    try:
        soup = BeautifulSoup(resp.text, "lxml")
    except Exception:
        soup = BeautifulSoup(resp.text, "html.parser")

    # Remove non-content tags
    for tag in soup(_STRIP_TAGS):
        tag.decompose()

    text = soup.get_text(separator="\n", strip=True)

    # Collapse excessive blank lines
    lines = [ln.strip() for ln in text.splitlines()]
    cleaned_lines = []
    prev_blank = False
    for ln in lines:
        if ln == "":
            if not prev_blank:
                cleaned_lines.append("")
            prev_blank = True
        else:
            cleaned_lines.append(ln)
            prev_blank = False

    text = "\n".join(cleaned_lines).strip()

    if not text:
        return None, "Could not extract any text from this page. Try pasting the job description instead."

    # Cap at 8 000 chars so we don't blow up the Claude context
    if len(text) > 8000:
        text = text[:8000] + "\n\n[...page truncated for length...]"

    return text, None
