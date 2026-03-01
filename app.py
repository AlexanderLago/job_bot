import base64
import hashlib
import json as _json
import re
import time
import traceback
from datetime import datetime
from pathlib import Path

import streamlit as st

from utils.resume_parser import parse_resume
from utils.ai_providers import PROVIDERS, call_tailor, call_score, ProviderRateLimitError
from utils.docx_builder import build_docx
from utils.pdf_builder import build_pdf
from utils.job_scraper import scrape_job_url
from utils.log_builder import build_log_docx, build_log_csv
from utils.interview_prep import search_interview_content, generate_questions, rate_answer

# ── Disk persistence helpers ──────────────────────────────────────────────────
_SAVE_DIR  = Path.home() / ".job_bot"
_SAVE_FILE = _SAVE_DIR / "saved_state.json"

def _load_saved() -> dict:
    """Read persisted state from disk. Returns {} if nothing saved yet."""
    try:
        if _SAVE_FILE.exists():
            return _json.loads(_SAVE_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}

def _write_saved(data: dict) -> None:
    """Overwrite the saved state file atomically."""
    try:
        _SAVE_DIR.mkdir(parents=True, exist_ok=True)
        _SAVE_FILE.write_text(_json.dumps(data), encoding="utf-8")
    except Exception:
        pass

def _patch_saved(**kwargs) -> None:
    """Merge kwargs into the saved state (read-modify-write)."""
    d = _load_saved()
    d.update(kwargs)
    _write_saved(d)

def _clear_saved() -> None:
    try:
        _SAVE_FILE.unlink(missing_ok=True)
    except Exception:
        pass

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Job Bot",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&family=Share+Tech+Mono&display=swap');

/* ═══════════════════════════════════════════════════
   JOB BOT — ULTRON ROBOTIC THEME
   ═══════════════════════════════════════════════════ */

/* ── Background: dark + circuit grid ── */
.stApp {
    background-color: #060606;
    background-image:
        linear-gradient(rgba(160,160,160,0.03) 1px, transparent 1px),
        linear-gradient(90deg, rgba(160,160,160,0.03) 1px, transparent 1px);
    background-size: 28px 28px;
}

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0c0c0c 0%, #080808 100%);
    border-right: 1px solid #1e1e1e;
}
[data-testid="stSidebar"] .stMarkdown p,
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] .stCaption { color: #888 !important; }
[data-testid="stSidebar"] strong { color: #bbb !important; font-family: 'Orbitron', monospace !important; letter-spacing: 0.05em !important; font-size: 0.75rem !important; }

/* ── Tabs ── */
.stTabs [data-baseweb="tab-list"] { background: #0a0a0a; border-bottom: 1px solid #1e1e1e; gap: 4px; }
.stTabs [data-baseweb="tab"] { background: #0e0e0e; border: 1px solid #1e1e1e; border-bottom: none; color: #555 !important; font-family: 'Share Tech Mono', monospace; letter-spacing: 0.12em; border-radius: 2px 2px 0 0; }
.stTabs [aria-selected="true"] { background: #0a0a0a !important; color: #CC0000 !important; border-color: #CC0000 !important; box-shadow: 0 0 12px rgba(204,0,0,0.2); }

/* ── Buttons ── */
.stButton > button { background: linear-gradient(135deg, #181818 0%, #0f0f0f 100%) !important; border: 1px solid #2e2e2e !important; color: #999 !important; font-family: 'Share Tech Mono', monospace !important; letter-spacing: 0.08em !important; text-transform: uppercase !important; border-radius: 2px !important; transition: all 0.15s ease !important; }
.stButton > button:hover { border-color: #CC0000 !important; color: #CC0000 !important; box-shadow: 0 0 14px rgba(204,0,0,0.25) !important; background: linear-gradient(135deg, #160a0a 0%, #0f0707 100%) !important; }
.stButton > button[kind="primary"] { background: linear-gradient(135deg, #7a0000 0%, #CC0000 100%) !important; border: 1px solid #FF2020 !important; color: #fff !important; box-shadow: 0 0 22px rgba(204,0,0,0.45) !important; }
.stButton > button[kind="primary"]:hover { box-shadow: 0 0 32px rgba(204,0,0,0.65) !important; }

/* ── Download buttons ── */
div[data-testid="stDownloadButton"] button { width: 100%; background: linear-gradient(135deg, #181818, #0f0f0f) !important; border: 1px solid #2e2e2e !important; color: #999 !important; font-family: 'Share Tech Mono', monospace !important; text-transform: uppercase !important; letter-spacing: 0.06em !important; border-radius: 2px !important; }
div[data-testid="stDownloadButton"] button:hover { border-color: #CC0000 !important; color: #CC0000 !important; box-shadow: 0 0 10px rgba(204,0,0,0.2) !important; }

/* ── Inputs ── */
.stTextArea textarea, .stTextInput > div > div > input { background: #0a0a0a !important; border: 1px solid #222 !important; color: #bbb !important; font-family: 'Share Tech Mono', monospace !important; border-radius: 2px !important; }
.stTextArea textarea:focus, .stTextInput > div > div > input:focus { border-color: #CC0000 !important; box-shadow: 0 0 8px rgba(204,0,0,0.15) !important; }

/* ── File uploader ── */
[data-testid="stFileUploader"] { border: 1px dashed #2a2a2a !important; background: #0a0a0a !important; border-radius: 2px !important; }

/* ── Sliders ── */
[data-testid="stSlider"] [role="slider"] { background: #CC0000 !important; box-shadow: 0 0 8px rgba(204,0,0,0.5) !important; }

/* ── Dividers ── */
hr { border-color: #1a1a1a !important; }

/* ── Alerts ── */
[data-testid="stSuccess"] { background: #060f06 !important; border: 1px solid #1a3a1a !important; border-radius: 2px !important; }
[data-testid="stWarning"] { background: #0f0a00 !important; border: 1px solid #3a2800 !important; border-radius: 2px !important; }
[data-testid="stError"]   { background: #0f0000 !important; border: 1px solid #3a0000 !important; border-radius: 2px !important; }
[data-testid="stInfo"]    { background: #00050f !important; border: 1px solid #001a3a !important; border-radius: 2px !important; }

/* ── Expanders ── */
[data-testid="stExpander"] { background: #0a0a0a !important; border: 1px solid #1e1e1e !important; border-radius: 2px !important; }
[data-testid="stExpander"]:hover { border-color: #CC0000 !important; }

/* ── Scrollbar ── */
::-webkit-scrollbar { width: 6px; } ::-webkit-scrollbar-track { background: #080808; } ::-webkit-scrollbar-thumb { background: #2a2a2a; border-radius: 0; } ::-webkit-scrollbar-thumb:hover { background: #CC0000; }

/* ── Custom classes ── */
.main-title {
    font-family: 'Orbitron', monospace;
    font-size: 5rem;
    font-weight: 900;
    background: linear-gradient(135deg, #666 0%, #bbb 25%, #fff 50%, #bbb 75%, #555 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    letter-spacing: 0.3em;
    text-align: center;
    margin: 0.4rem 0 0 0;
    filter: drop-shadow(0 0 30px rgba(255,255,255,0.08));
}
.subtitle {
    font-family: 'Share Tech Mono', monospace;
    color: #CC0000 !important;
    font-size: 0.72rem;
    letter-spacing: 0.35em;
    text-align: center;
    text-transform: uppercase;
    margin: 0.2rem 0 2rem 0;
}
.section-label {
    font-family: 'Share Tech Mono', monospace;
    font-size: 0.68rem;
    text-transform: uppercase;
    letter-spacing: 0.2em;
    color: #CC0000;
    margin-bottom: 6px;
    border-left: 2px solid #CC0000;
    padding-left: 8px;
}
.score-card {
    background: linear-gradient(135deg, #0e0e0e, #080808);
    border: 1px solid #CC0000;
    border-radius: 2px;
    padding: 1rem 1.25rem;
    margin-bottom: 1rem;
    box-shadow: 0 0 24px rgba(204,0,0,0.12);
}
.score-number {
    font-family: 'Orbitron', monospace;
    font-size: 3rem;
    font-weight: 800;
    line-height: 1;
}
.history-card {
    background: linear-gradient(135deg, #0e0e0e, #0a0a0a);
    border: 1px solid #1e1e1e;
    border-radius: 2px;
    padding: 1rem;
    margin-bottom: 0.75rem;
}
.keyword-pill {
    display: inline-block;
    background: #0d0d0d;
    border: 1px solid #CC0000;
    color: #CC0000;
    border-radius: 1px;
    padding: 2px 10px;
    font-size: 0.78rem;
    font-family: 'Share Tech Mono', monospace;
    margin: 3px 3px 3px 0;
}
</style>
""", unsafe_allow_html=True)

# ── Session state initialisation ──────────────────────────────────────────────
if "master_resume_text" not in st.session_state:
    st.session_state.master_resume_text = ""
    st.session_state.master_resume_name = ""
    st.session_state.master_resume_bytes = b""
if "history" not in st.session_state:
    st.session_state.history = []
if "app_log" not in st.session_state:
    st.session_state.app_log = []
# Store job_text fetched from URL so it survives reruns
if "fetched_job_text" not in st.session_state:
    st.session_state.fetched_job_text = ""
if "last_score" not in st.session_state:
    st.session_state.last_score = None
if "tailor_result" not in st.session_state:
    st.session_state.tailor_result = None
if "rate_limited_providers" not in st.session_state:
    st.session_state.rate_limited_providers = set()
if "rl_until" not in st.session_state:
    st.session_state.rl_until = {}          # {provider_id: epoch float when cooldown expires}
if "result_cache" not in st.session_state:
    st.session_state.result_cache = {}      # {cache_key: result dict}
if "prep_questions" not in st.session_state:
    st.session_state.prep_questions = []
if "prep_chat" not in st.session_state:
    st.session_state.prep_chat = []
if "prep_job" not in st.session_state:
    st.session_state.prep_job = {"company": "", "role": ""}
if "prep_active_q" not in st.session_state:
    st.session_state.prep_active_q = None
if "mark_applied_open" not in st.session_state:
    st.session_state.mark_applied_open = False

# ── Load persisted state from disk (runs once per session) ───────────────────
if "fs_loaded" not in st.session_state:
    _saved = _load_saved()
    if _saved.get("master_name") and not st.session_state.master_resume_name:
        st.session_state.master_resume_name  = _saved["master_name"]
        st.session_state.master_resume_text  = _saved.get("master_text", "")
        _b64 = _saved.get("master_bytes", "")
        st.session_state.master_resume_bytes = base64.b64decode(_b64) if _b64 else b""
    if not st.session_state.app_log:
        st.session_state.app_log = _saved.get("app_log", [])
    if not st.session_state.history:
        st.session_state.history = _saved.get("history_meta", [])
    st.session_state.fs_loaded = True
    # Seed user-key widget states from disk so inputs show saved values on load
    _saved_ukeys = _saved.get("user_keys", {})
    for _p in PROVIDERS:
        _wk = f"ukey_{_p['key_name']}"
        if _wk not in st.session_state:
            st.session_state[_wk] = _saved_ukeys.get(_p["key_name"], "")
    # Migrate existing log entries that lack a status field
    for _entry in st.session_state.app_log:
        if "status" not in _entry:
            _entry["status"] = "Applied"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _company_slug(company: str) -> str:
    return re.sub(r"[^a-z0-9]", "", company.lower()) or "company"


_JD_NOISE = {
    "about the job", "job description", "about this role", "about the role",
    "position overview", "job summary", "about us", "job posting",
    "about this position", "overview", "basic qualifications",
    "preferred qualifications", "minimum qualifications",
    "key responsibilities", "responsibilities", "requirements",
    "what you'll do", "what you will do", "what we're looking for",
    "what we are looking for", "nice to have", "required skills",
    "preferred skills", "equal opportunity", "about the team",
    "who you are", "who we are", "the role", "the team",
}
_JD_SKIP = {
    "about", "job", "description", "requirements", "responsibilities",
    "overview", "summary", "position", "role", "opportunity", "posting",
    "remote", "hybrid", "the", "a", "an", "this", "we", "our", "your",
    "what", "who", "how", "why", "when", "where", "which",
    "basic", "preferred", "minimum", "key", "required", "nice",
    "qualifications", "skills", "benefits", "compensation", "salary",
    "equal", "diversity", "inclusion", "apply", "note", "please",
    "must", "strong", "excellent", "experience", "ability", "knowledge",
    # job-title words that are never company names
    "senior", "junior", "staff", "principal", "lead", "associate",
    "engineer", "manager", "developer", "analyst", "designer", "director",
    "specialist", "coordinator", "consultant", "scientist", "architect",
    "recruiter", "product", "software", "data", "sales", "marketing",
    "operations", "finance", "full", "part", "time", "contract",
}
_ABOUT_FILLER = {
    "the", "us", "this", "our", "you", "a", "an",
    "role", "team", "job", "position", "company", "opportunity", "department",
}


def _extract_company_name(jd_lines: list) -> str:
    """
    Best-effort extraction of the human-readable company name from JD lines.
    Returns a display name string (may contain spaces/caps).
    """
    clean = [l for l in jd_lines[:40] if l.strip() and l.lower().strip() not in _JD_NOISE]

    # 0) "About CompanyName" section header — most reliable signal
    for line in clean:
        m = re.match(r'^About\s+([A-Z][A-Za-z0-9&\- .,]{1,40}?)\s*$', line.strip())
        if m:
            name = m.group(1).strip()
            if name.split()[0].lower() not in _ABOUT_FILLER:
                return name

    # 1) "Role at Company" in first 5 lines
    for line in clean[:5]:
        m = re.search(
            r'\bat\s+([A-Z][A-Za-z0-9& .,\-]{1,35}?)(?=\s*[,|–\-]|\s+(?:is|are|was|has|have)\b|$)',
            line,
        )
        if m:
            name = m.group(1).strip()
            if len(name) >= 2 and name.split()[0].lower() not in _JD_SKIP:
                return name

    # 2) Explicit label — "Company: Acme Corp" or "Employer: …"
    for line in clean[:25]:
        m = re.match(r'^(?:Company|Employer|Organization):\s*(.+)$', line.strip(), re.IGNORECASE)
        if m:
            return m.group(1).strip()

    # 3) "CompanyName is/are/was/has/have …" at line start
    for line in clean[:15]:
        m = re.match(r'^([A-Z][A-Za-z0-9& .,\-]{1,35}?)\s+(?:is|are|was|has|have)\b', line)
        if m:
            cand = m.group(1).strip()
            words = cand.split()
            if 1 <= len(words) <= 4 and words[0].lower() not in _JD_SKIP:
                return cand

    # 4) Short capitalised line (1–3 words) that doesn't look like a title or location
    for line in clean[:10]:
        words = line.split()
        if 1 <= len(words) <= 3 and words[0][0].isupper():
            if words[0].lower() not in _JD_SKIP:
                # Reject "City, ST" patterns
                if not re.search(r',\s*[A-Z]{2}\b', line):
                    return line

    return ""   # caller falls back


def _slug_from_jd(jd_lines: list) -> str:
    """Return a file-safe slug derived from the company name in the JD."""
    name = _extract_company_name(jd_lines)
    return _company_slug(name) if name else "tailored"


def _condense_resume(data: dict) -> dict:
    """Trim resume content lightly so it fits on one page."""
    import copy
    d = copy.deepcopy(data)
    # Trim summary to first 2 sentences
    summary = d.get("summary", "")
    if summary:
        sentences = re.split(r'(?<=[.!?])\s+', summary.strip())
        if len(sentences) > 2:
            d["summary"] = " ".join(sentences[:2])
    # Cap most-recent job at 5 bullets
    exp = d.get("experience", [])
    if exp and len(exp[0].get("bullets", [])) > 5:
        exp[0]["bullets"] = exp[0]["bullets"][:5]
    return d


# Per-provider cooldown in seconds before it re-enters rotation after a rate limit.
_RL_COOLDOWN = {
    "anthropic": 300, "gemini": 60, "gemini15": 60, "groq": 60,
    "cerebras": 60, "sambanova": 60, "openrouter": 60, "openrouter2": 60,
    "openrouter3": 60, "zhipu": 60, "together": 60, "mistral": 60,
    "fireworks": 60, "deepinfra": 60, "hyperbolic": 60,
}


def _call_with_fallback(fn, available, all_keys, preferred_cfg, *args):
    """Try preferred provider, then cycle through available on rate limit.
    Tricks: auto-expire cooldowns, retry once before cycling, full fallback chain.
    Returns (result, used_provider_cfg). Raises RuntimeError if all exhausted."""
    now = time.time()
    # Auto-clear providers whose cooldown has expired
    expired = [k for k, until in st.session_state.rl_until.items() if until <= now]
    for k in expired:
        del st.session_state.rl_until[k]
    st.session_state.rate_limited_providers = set(st.session_state.rl_until.keys())

    order = [preferred_cfg] + [p for p in available if p["id"] != preferred_cfg["id"]]
    for p in order:
        key = all_keys.get(p["id"], "")
        if not key:
            continue
        if p["id"] in st.session_state.rl_until:
            continue  # still cooling down — skip
        try:
            return fn(p, key, *args), p
        except ProviderRateLimitError as _e:
            # Retry once after a brief pause (catches momentary blips)
            time.sleep(3)
            try:
                return fn(p, key, *args), p
            except ProviderRateLimitError:
                cooldown = _RL_COOLDOWN.get(p["id"], 90)
                st.session_state.rl_until[p["id"]] = time.time() + cooldown
                st.session_state.rate_limited_providers.add(p["id"])
                _msg = "model unavailable" if any(x in str(_e).lower() for x in ("404", "not found")) else f"rate limited (reset in {cooldown}s)"
                st.toast(f"⚠️ {p['label']} {_msg} — trying next provider...")
    raise RuntimeError("All configured providers are rate limited. Wait a moment and try again.")


def _score_color(score: int) -> str:
    if score >= 85:
        return "#22C55E"   # green
    if score >= 70:
        return "#84CC16"   # lime
    if score >= 55:
        return "#EAB308"   # yellow
    if score >= 40:
        return "#F97316"   # orange
    return "#EF4444"       # red


def _score_label(score: int) -> str:
    if score >= 85:
        return "Excellent match"
    if score >= 70:
        return "Strong match"
    if score >= 55:
        return "Moderate match"
    if score >= 40:
        return "Weak match"
    return "Poor match"


# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚙️ Settings")
    st.divider()

    # Master resume
    st.markdown("**📄 Master Resume**")
    st.caption("Upload once — reuse across all tailoring sessions.")
    master_file = st.file_uploader(
        label="Upload master resume",
        type=["pdf", "docx", "txt"],
        label_visibility="collapsed",
        key="master_uploader",
    )
    if master_file:
        raw = master_file.read()
        try:
            parsed = parse_resume(raw, master_file.name)
            st.session_state.master_resume_bytes = raw
            st.session_state.master_resume_name = master_file.name
            st.session_state.master_resume_text = parsed
            _patch_saved(
                master_name  = st.session_state.master_resume_name,
                master_text  = st.session_state.master_resume_text,
                master_bytes = base64.b64encode(raw).decode(),
            )
            st.success(f"✅ {master_file.name}")
        except Exception as e:
            st.error(f"Could not read master resume: {e}")
    elif st.session_state.master_resume_name:
        st.success(f"✅ {st.session_state.master_resume_name}")

    st.divider()

    # ── AI Model selector ──────────────────────────────────────────────────────
    # Reads all provider keys from Streamlit secrets. Shows only configured ones
    # as selectable options; lists unconfigured ones with signup links.
    _all_keys = {}
    for _p in PROVIDERS:
        _secret_key = ""
        try:
            _secret_key = st.secrets.get(_p["key_name"], "") or ""
        except Exception:
            pass
        _user_key = st.session_state.get(f"ukey_{_p['key_name']}", "").strip()
        _all_keys[_p["id"]] = _user_key or _secret_key

    _available = [_p for _p in PROVIDERS if _all_keys.get(_p["id"])]
    _rl = st.session_state.rate_limited_providers

    st.markdown("**🤖 AI Model**")

    if not _available:
        st.warning("No API keys configured. Add at least one key to `.streamlit/secrets.toml`.")
        _selected_cfg = None
        provider = ""
        api_key = ""
    else:
        _radio_ids = ["auto"] + [_p["id"] for _p in _available]
        _radio_labels = {"auto": "🔄 Auto (cycle on rate limit)"}
        _now = time.time()
        for _p in _available:
            if _p["id"] in st.session_state.rl_until:
                _secs = max(0, int(st.session_state.rl_until[_p["id"]] - _now))
                _badge = f" ⚠️ resetting in {_secs}s"
            else:
                _badge = " ✅"
            _radio_labels[_p["id"]] = _p["label"] + _badge

        _selected_id = st.radio(
            "model_select",
            _radio_ids,
            format_func=lambda x: _radio_labels[x],
            index=0,
            label_visibility="collapsed",
        )

        if _selected_id == "auto":
            # Pick first non-rate-limited available provider
            _selected_cfg = next(
                (_p for _p in _available if _p["id"] not in _rl),
                _available[0],
            )
        else:
            _selected_cfg = next(_p for _p in PROVIDERS if _p["id"] == _selected_id)

        provider = _selected_cfg["id"]
        api_key = _all_keys.get(provider, "")

    # ── User API key inputs ────────────────────────────────────────────────────
    with st.expander("🔑 Your API Keys"):
        st.caption("Enter your own keys — they override the app's built-in keys and use your personal rate limit pool.")
        _seen_kn: set = set()
        for _p in PROVIDERS:
            _kn = _p["key_name"]
            if _kn in _seen_kn:
                continue
            _seen_kn.add(_kn)
            # Collect all provider labels sharing this key_name
            _sharing = [_q["label"] for _q in PROVIDERS if _q["key_name"] == _kn]
            _input_label = _sharing[0] if len(_sharing) == 1 else _sharing[0].split("·")[-1].strip()
            st.text_input(
                _input_label,
                type="password",
                key=f"ukey_{_kn}",
                help=f"Used by: {', '.join(_sharing)}",
                placeholder="Paste API key…",
            )
        if st.button("💾 Save My Keys", use_container_width=True):
            _to_save = {}
            for _p in PROVIDERS:
                _kn = _p["key_name"]
                _to_save[_kn] = st.session_state.get(f"ukey_{_kn}", "")
            _patch_saved(user_keys=_to_save)
            st.success("Keys saved!")
            st.rerun()

    # Unconfigured providers — show signup links
    _missing = [_p for _p in PROVIDERS if not _all_keys.get(_p["id"])]
    if _missing:
        # Deduplicate by signup_url to avoid showing the same provider 3x (openrouter)
        _seen_urls: set = set()
        _missing_deduped = []
        for _p in _missing:
            if _p["signup_url"] not in _seen_urls:
                _seen_urls.add(_p["signup_url"])
                _missing_deduped.append(_p)
        with st.expander(f"➕ Get free API keys ({len(_missing_deduped)} providers)"):
            for _p in _missing_deduped:
                st.markdown(f"**{_p['label']}** (free)  \n[Get key]({_p['signup_url']})")

    st.divider()

    st.markdown("**Temperature**")
    temperature = st.slider(
        label="temperature",
        min_value=0.0,
        max_value=1.0,
        value=0.3,
        step=0.05,
        label_visibility="collapsed",
    )
    col_lo, col_hi = st.columns(2)
    col_lo.caption("Conservative")
    col_hi.caption("Creative")
    st.caption(
        "**Low** — stays close to your original wording.  \n"
        "**High** — bolder rewording, stronger action verbs.  \n"
        "*Either way: nothing is fabricated.*"
    )

    st.divider()

    output_format = st.radio(
        "Output format",
        ["DOCX + PDF", "DOCX only", "PDF only"],
        index=0,
    )

    st.divider()
    st.markdown("**🗑️ Saved Data**")
    if st.button("Clear all saved data", type="secondary"):
        _clear_saved()
        st.session_state.master_resume_name  = ""
        st.session_state.master_resume_text  = ""
        st.session_state.master_resume_bytes = b""
        st.session_state.app_log  = []
        st.session_state.history  = []
        st.success("All saved data cleared.")

    st.divider()
    st.caption("⚙ UNIT POWERED BY CLAUDE SONNET · [ANTHROPIC](https://anthropic.com)")

# ── Main header ───────────────────────────────────────────────────────────────
st.markdown("""
<div style="text-align:center; padding: 1.2rem 0 0 0;">
  <svg xmlns="http://www.w3.org/2000/svg" width="120" height="132" viewBox="0 0 120 132">
    <defs>
      <filter id="rglow" x="-60%" y="-60%" width="220%" height="220%">
        <feGaussianBlur stdDeviation="3.5" result="blur"/>
        <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
      </filter>
      <linearGradient id="metal" x1="0%" y1="0%" x2="100%" y2="100%">
        <stop offset="0%" style="stop-color:#383838"/>
        <stop offset="45%" style="stop-color:#1a1a1a"/>
        <stop offset="100%" style="stop-color:#2d2d2d"/>
      </linearGradient>
    </defs>
    <!-- Head -->
    <polygon points="18,2 102,2 118,20 118,88 102,106 18,106 2,88 2,20" fill="url(#metal)" stroke="#3a3a3a" stroke-width="1.5"/>
    <!-- Forehead panel -->
    <rect x="22" y="7" width="76" height="16" rx="1" fill="#111" stroke="#272727" stroke-width="1"/>
    <!-- Forehead centre light -->
    <rect x="55" y="11" width="10" height="6" rx="1" fill="#CC0000" filter="url(#rglow)" opacity="0.95"/>
    <!-- Panel seam lines -->
    <line x1="2" y1="55" x2="22" y2="55" stroke="#2a2a2a" stroke-width="1"/>
    <line x1="98" y1="55" x2="118" y2="55" stroke="#2a2a2a" stroke-width="1"/>
    <line x1="2" y1="65" x2="22" y2="65" stroke="#222" stroke-width="0.8"/>
    <line x1="98" y1="65" x2="118" y2="65" stroke="#222" stroke-width="0.8"/>
    <!-- Eye sockets (dark recesses) -->
    <polygon points="6,43 54,37 54,57 6,57" fill="#040404" stroke="#161616" stroke-width="0.5"/>
    <polygon points="66,37 114,43 114,57 66,57" fill="#040404" stroke="#161616" stroke-width="0.5"/>
    <!-- Eyes: glowing red visor -->
    <polygon points="8,44 52,38 52,56 8,56" fill="#CC0000" filter="url(#rglow)"/>
    <polygon points="68,38 112,44 112,56 68,56" fill="#CC0000" filter="url(#rglow)"/>
    <!-- Nose sensor -->
    <rect x="52" y="60" width="16" height="11" rx="1" fill="#111" stroke="#CC0000" stroke-width="0.7" opacity="0.65"/>
    <!-- Mouth area (Ultron angular) -->
    <polygon points="20,74 34,68 86,68 100,74 90,88 30,88" fill="#070707" stroke="#252525" stroke-width="1"/>
    <line x1="36" y1="68" x2="36" y2="88" stroke="#1c1c1c" stroke-width="1"/>
    <line x1="48" y1="68" x2="48" y2="88" stroke="#1c1c1c" stroke-width="1"/>
    <line x1="60" y1="68" x2="60" y2="88" stroke="#242424" stroke-width="1.5"/>
    <line x1="72" y1="68" x2="72" y2="88" stroke="#1c1c1c" stroke-width="1"/>
    <line x1="84" y1="68" x2="84" y2="88" stroke="#1c1c1c" stroke-width="1"/>
    <!-- Chin -->
    <polygon points="30,88 90,88 96,106 24,106" fill="url(#metal)" stroke="#333" stroke-width="1"/>
    <!-- Neck blocks -->
    <rect x="32" y="106" width="22" height="14" rx="1" fill="#111" stroke="#252525"/>
    <rect x="66" y="106" width="22" height="14" rx="1" fill="#111" stroke="#252525"/>
    <!-- Ear panels -->
    <rect x="0" y="46" width="5" height="22" rx="1" fill="#141414" stroke="#252525"/>
    <rect x="115" y="46" width="5" height="22" rx="1" fill="#141414" stroke="#252525"/>
  </svg>
</div>
<p class="main-title">JOB BOT</p>
<p class="subtitle">▸ RESUME OPTIMIZATION SYSTEM ONLINE ◂</p>
""", unsafe_allow_html=True)

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_tailor, tab_history, tab_log, tab_prep = st.tabs(["✨ Tailor", "📁 History", "📋 Application Log", "🎤 Interview Prep"])


# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — TAILOR
# ══════════════════════════════════════════════════════════════════════════════
with tab_tailor:

    col_left, col_right = st.columns(2, gap="large")

    # ── Left: resume source ──────────────────────────────────────────────────
    with col_left:
        st.markdown('<p class="section-label">Your Resume</p>', unsafe_allow_html=True)

        use_master = False
        if st.session_state.master_resume_text:
            use_master = st.checkbox(
                f"Use master resume ({st.session_state.master_resume_name})",
                value=True,
            )

        resume_text = ""
        uploaded_file = None

        if use_master:
            resume_text = st.session_state.master_resume_text
            st.info(f"Using master resume: **{st.session_state.master_resume_name}**")
        else:
            uploaded_file = st.file_uploader(
                label="Upload resume",
                type=["pdf", "docx", "txt"],
                label_visibility="collapsed",
                help="Accepts PDF, DOCX, or plain text.",
            )
            if uploaded_file:
                st.success(f"Loaded: **{uploaded_file.name}**")

    # ── Right: job description ───────────────────────────────────────────────
    with col_right:
        st.markdown('<p class="section-label">Job Description</p>', unsafe_allow_html=True)

        input_method = st.radio(
            "Input method",
            ["Paste text", "Job URL"],
            horizontal=True,
            label_visibility="collapsed",
        )

        job_description = ""

        if input_method == "Job URL":
            url_col, btn_col = st.columns([4, 1])
            with url_col:
                job_url = st.text_input(
                    "Job URL",
                    placeholder="https://careers.example.com/job/12345",
                    label_visibility="collapsed",
                )
            with btn_col:
                st.markdown("<br>", unsafe_allow_html=True)
                fetch_btn = st.button("Fetch", use_container_width=True)

            if fetch_btn and job_url.strip():
                with st.spinner("⚙️ ScAnNiNg NeTwOrK... BeEp BoOp..."):
                    text, err = scrape_job_url(job_url.strip())
                if err:
                    st.warning(f"⚠️ {err}")
                    st.session_state.fetched_job_text = ""
                else:
                    st.session_state.fetched_job_text = text
                    st.success("Job posting fetched — review and edit below if needed.")

            job_description = st.text_area(
                label="Fetched job description (editable)",
                value=st.session_state.fetched_job_text,
                placeholder="Click 'Fetch' above, or paste text here as a fallback...",
                height=240,
                label_visibility="collapsed",
            )
        else:
            # Clear any stale fetched text when switching to paste mode
            if st.session_state.fetched_job_text:
                st.session_state.fetched_job_text = ""
            job_description = st.text_area(
                label="Job description",
                placeholder="Paste the full job posting here — title, responsibilities, requirements, company info...",
                height=280,
                label_visibility="collapsed",
            )

        words = len(job_description.split()) if job_description else 0
        st.caption(f"{words} words")

    # ── Action buttons ────────────────────────────────────────────────────────
    st.markdown("")
    btn_col1, btn_col2, _ = st.columns([1, 1, 2])

    with btn_col1:
        score_btn = st.button("🎯 Score My Fit", use_container_width=True)
    with btn_col2:
        run_btn = st.button("✨ Tailor My Resume", type="primary", use_container_width=True)

    # ── Score ─────────────────────────────────────────────────────────────────
    if score_btn:
        errors = []
        if not api_key:
            errors.append("No API key — enter it in the sidebar.")
        active_resume = resume_text if use_master else (
            parse_resume(uploaded_file.read(), uploaded_file.name) if uploaded_file else ""
        )
        if not active_resume:
            errors.append("No resume provided.")
        if not job_description.strip():
            errors.append("No job description provided.")

        if errors:
            for e in errors:
                st.error(e)
        else:
            _score_ck = hashlib.md5(f"score||{active_resume}||{job_description}".encode()).hexdigest()
            if _score_ck in st.session_state.result_cache:
                st.session_state.last_score = st.session_state.result_cache[_score_ck]
                st.toast("⚡ Score loaded from cache — no API call needed.")
            else:
                with st.spinner("⚙️ AnAlYzInG tArGeT jOb DaTa... BEEP BOOP BOP..."):
                    try:
                        result, used = _call_with_fallback(
                            call_score, _available, _all_keys, _selected_cfg,
                            active_resume, job_description,
                        )
                        if used["id"] != provider:
                            st.info(f"Switched to {used['label']} (primary was rate limited)")
                        st.session_state.last_score = result
                        st.session_state.result_cache[_score_ck] = result
                    except RuntimeError as e:
                        st.error(str(e))
                        st.session_state.last_score = None
                    except Exception as e:
                        st.error(f"Scoring error: {str(e)[:600]}")
                        st.session_state.last_score = None

    # Show score card if we have a result
    if st.session_state.last_score:
        sc = st.session_state.last_score
        score_val = sc.get("score", 0)
        color = _score_color(score_val)
        label = _score_label(score_val)

        st.markdown("---")
        s_col1, s_col2 = st.columns([1, 3])
        with s_col1:
            st.markdown(
                f'<div class="score-card" style="text-align:center">'
                f'<div class="score-number" style="color:{color}">{score_val}</div>'
                f'<div style="color:#94A3B8;font-size:0.85rem">/ 100</div>'
                f'<div style="color:{color};font-weight:600;margin-top:4px">{label}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
        with s_col2:
            if sc.get("strengths"):
                st.markdown("**✅ Strengths**")
                for s in sc["strengths"]:
                    st.markdown(f"- {s}")
            if sc.get("gaps"):
                st.markdown("**⚠️ Gaps**")
                for g in sc["gaps"]:
                    st.markdown(f"- {g}")
            if sc.get("keywords_missing"):
                st.markdown("**🔍 Missing Keywords**")
                pills = "".join(
                    f'<span class="keyword-pill">{k}</span>'
                    for k in sc["keywords_missing"]
                )
                st.markdown(pills, unsafe_allow_html=True)
        st.markdown("---")

    # ── Tailor ────────────────────────────────────────────────────────────────
    if run_btn:
        st.session_state.tailor_result = None  # clear previous result on new attempt
        errors = []
        if not api_key:
            errors.append("No API key — enter it in the sidebar.")
        if not use_master and not uploaded_file:
            errors.append("No resume uploaded.")
        if not job_description.strip():
            errors.append("No job description provided.")

        if errors:
            for e in errors:
                st.error(e)
            st.stop()

        # Parse resume if not using master
        if not use_master:
            with st.spinner("⚙️ InItIaLiZiNg ReSuMe ScAnNeR..."):
                try:
                    resume_text = parse_resume(uploaded_file.read(), uploaded_file.name)
                except Exception as e:
                    st.error(f"Could not read resume: {e}")
                    st.stop()

        if not resume_text.strip():
            st.error("Could not extract any text from your resume. Try a .docx or .txt file.")
            st.stop()

        # Call AI provider (with automatic fallback on rate limit + caching)
        _tailor_ck = hashlib.md5(f"tailor||{resume_text}||{job_description}||{temperature:.2f}".encode()).hexdigest()
        if _tailor_ck in st.session_state.result_cache:
            resume_data = st.session_state.result_cache[_tailor_ck]
            used = _selected_cfg
            st.toast("⚡ Result loaded from cache — no API call needed.")
        else:
            _provider_label = _selected_cfg["label"] if _selected_cfg else "AI"
            with st.spinner(f"⚙️ [{_provider_label}] CaLcUlAtInG rEsUmE mAtRiX... BEEP BOOP BOP..."):
                try:
                    resume_data, used = _call_with_fallback(
                        call_tailor, _available, _all_keys, _selected_cfg,
                        resume_text, job_description, temperature,
                    )
                    if used["id"] != provider:
                        st.info(f"Switched to {used['label']} (primary was rate limited)")
                    st.session_state.result_cache[_tailor_ck] = resume_data
                except RuntimeError as e:
                    st.error(str(e))
                    st.stop()
                except Exception as e:
                    st.error(f"AI error: {e}")
                    with st.expander("Debug info"):
                        st.code(traceback.format_exc())
                    st.stop()

        resume_data = _condense_resume(resume_data)

        jd_lines = [ln.strip() for ln in job_description.splitlines() if ln.strip()]
        company_name = _extract_company_name(jd_lines) or (jd_lines[0][:40] if jd_lines else "")
        slug = _company_slug(company_name) or "tailored"

        # Build files
        docx_bytes, pdf_bytes = None, None
        if output_format in ("DOCX + PDF", "DOCX only"):
            with st.spinner("⚙️ AsSeBlInG dOcUmEnT mAtRiX..."):
                try:
                    docx_bytes = build_docx(resume_data)
                except Exception as e:
                    st.error(f"DOCX build error: {e}")

        if output_format in ("DOCX + PDF", "PDF only"):
            with st.spinner("⚙️ ReNdErInG pDf CoNsTrUcT..."):
                try:
                    pdf_bytes = build_pdf(resume_data)
                except Exception as e:
                    st.error(f"PDF build error: {e}")

        # Save to session history
        history_entry = {
            "company": company_name,
            "slug": slug,
            "job_title": jd_lines[0] if jd_lines else "",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "score": st.session_state.last_score.get("score") if st.session_state.last_score else None,
            "data": resume_data,
            "docx_bytes": docx_bytes,
            "pdf_bytes": pdf_bytes,
        }
        existing_idx = next((i for i, e in enumerate(st.session_state.history) if e["slug"] == slug), None)
        if existing_idx is not None:
            st.session_state.history[existing_idx] = history_entry
        else:
            st.session_state.history.insert(0, history_entry)
        _hist_meta = [
            {k: v for k, v in e.items() if k not in ("docx_bytes", "pdf_bytes")}
            for e in st.session_state.history
        ]
        _patch_saved(history_meta=_hist_meta)
        st.session_state.tailor_result = {
            "resume_data":  resume_data,
            "docx_bytes":   docx_bytes,
            "pdf_bytes":    pdf_bytes,
            "slug":         slug,
            "company_name": company_name,
            "job_title":    jd_lines[0] if jd_lines else "",
            "score":        st.session_state.last_score.get("score") if st.session_state.last_score else None,
        }

    # ── Results (persists across reruns) ──────────────────────────────────────
    if st.session_state.get("tailor_result"):
        tr           = st.session_state.tailor_result
        resume_data  = tr["resume_data"]
        docx_bytes   = tr["docx_bytes"]
        pdf_bytes    = tr["pdf_bytes"]
        slug         = tr["slug"]
        company_name = tr["company_name"]

        st.divider()
        st.success("Your tailored resume is ready!")

        dl_col1, dl_col2, dl_col3 = st.columns([1, 1, 2])
        docx_filename = f"resume_{slug}.docx"
        pdf_filename  = f"resume_{slug}.pdf"

        if docx_bytes:
            with dl_col1:
                st.download_button(
                    label="⬇️ Download DOCX",
                    data=docx_bytes,
                    file_name=docx_filename,
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
        if pdf_bytes:
            with dl_col2:
                st.download_button(
                    label="⬇️ Download PDF",
                    data=pdf_bytes,
                    file_name=pdf_filename,
                    mime="application/pdf",
                )

        # ── Mark as Applied ───────────────────────────────────────────────────
        if not st.session_state.mark_applied_open:
            if st.button("✓ Mark as Applied", type="primary", key="mark_applied_btn"):
                st.session_state.mark_applied_open = True
                st.rerun()
        else:
            st.markdown("**Save to Application Log**")
            apply_c1, apply_c2 = st.columns(2)
            with apply_c1:
                apply_location = st.text_input(
                    "Location", placeholder="New York, NY", key="apply_location"
                )
            with apply_c2:
                apply_work_type = st.selectbox(
                    "Work Type", ["Hybrid", "Remote", "On-site"], key="apply_work_type"
                )
            btn_confirm_col, btn_cancel_col, _ = st.columns([1, 1, 2])
            with btn_confirm_col:
                if st.button("Confirm & Save", type="primary", key="apply_confirm_btn"):
                    new_entry = {
                        "date": datetime.today().strftime("%Y-%m-%d"),
                        "job_title": tr["job_title"],
                        "company": tr["company_name"] or tr["slug"],
                        "location": apply_location,
                        "work_type": apply_work_type,
                        "fit_pct": tr["score"] or 0,
                        "status": "Applied",
                    }
                    st.session_state.app_log.append(new_entry)
                    _patch_saved(app_log=st.session_state.app_log)
                    st.session_state.mark_applied_open = False
                    st.success("Added to your Application Log ✓ — view it in the 📋 Application Log tab.")
                    st.rerun()
            with btn_cancel_col:
                if st.button("Cancel", key="apply_cancel_btn"):
                    st.session_state.mark_applied_open = False
                    st.rerun()

        # ── Preview ───────────────────────────────────────────────────────────
        st.markdown("### Preview")
        st.markdown(f"## {resume_data.get('name', '')}")
        contact_parts = [
            resume_data.get("phone", ""),
            resume_data.get("email", ""),
            resume_data.get("location", ""),
            resume_data.get("linkedin", ""),
        ]
        st.markdown("  |  ".join(p for p in contact_parts if p))
        st.divider()

        if resume_data.get("summary"):
            st.markdown("**PROFESSIONAL SUMMARY**")
            st.write(resume_data["summary"])
            st.divider()

        if resume_data.get("experience"):
            st.markdown("**EXPERIENCE**")
            for job in resume_data["experience"]:
                col_t, col_d = st.columns([3, 1])
                with col_t:
                    st.markdown(f"**{job.get('title', '')}** — {job.get('company', '')} · {job.get('location', '')}")
                with col_d:
                    st.markdown(
                        f"<div style='text-align:right;color:#94A3B8'>{job.get('dates', '')}</div>",
                        unsafe_allow_html=True,
                    )
                for b in job.get("bullets", []):
                    st.markdown(f"- {b}")
            st.divider()

        if resume_data.get("education"):
            st.markdown("**EDUCATION**")
            for edu in resume_data["education"]:
                st.markdown(f"**{edu.get('degree', '')}** — {edu.get('school', '')}  ·  {edu.get('dates', '')}")
                if edu.get("details"):
                    st.caption(edu["details"])
            st.divider()

        if resume_data.get("skills"):
            st.markdown("**SKILLS**")
            st.markdown(", ".join(resume_data["skills"]))
            st.divider()

        keywords = resume_data.get("keywords_added", [])
        if keywords:
            st.markdown("**ATS Keywords Added**")
            pills = "".join(f'<span class="keyword-pill">{k}</span>' for k in keywords)
            st.markdown(pills, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — HISTORY
# ══════════════════════════════════════════════════════════════════════════════
with tab_history:
    st.markdown("### Session History")
    st.caption("Tailoring history is saved in your browser. File downloads must be re-generated each session.")

    if not st.session_state.history:
        st.info("No tailored resumes yet. Head to the **✨ Tailor** tab to get started.")
    else:
        for i, entry in enumerate(st.session_state.history):
            score = entry.get("score")
            score_badge = (
                f'<span style="color:{_score_color(score)};font-weight:600">{score}% match</span>'
                if score is not None
                else '<span style="color:#64748B">not scored</span>'
            )
            st.markdown(
                f'<div class="history-card">'
                f'<div style="font-size:1.1rem;font-weight:700">{entry["company"] or "Untitled"}</div>'
                f'<div style="color:#94A3B8;font-size:0.85rem">{entry["timestamp"]} &nbsp;·&nbsp; {score_badge}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
            h_col1, h_col2, _ = st.columns([1, 1, 2])
            if entry.get("docx_bytes"):
                with h_col1:
                    st.download_button(
                        label="⬇️ DOCX",
                        data=entry["docx_bytes"],
                        file_name=f"resume_{entry['slug']}.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        key=f"hist_docx_{i}",
                        use_container_width=True,
                    )
            if entry.get("pdf_bytes"):
                with h_col2:
                    st.download_button(
                        label="⬇️ PDF",
                        data=entry["pdf_bytes"],
                        file_name=f"resume_{entry['slug']}.pdf",
                        mime="application/pdf",
                        key=f"hist_pdf_{i}",
                        use_container_width=True,
                    )
            if not entry.get("docx_bytes") and not entry.get("pdf_bytes"):
                st.caption("Re-run tailoring to regenerate download.")


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — APPLICATION LOG
# ══════════════════════════════════════════════════════════════════════════════
with tab_log:
    st.markdown("### Application Log")
    st.caption("Track every job you apply to. Export as DOCX or CSV to save your records.")

    _STATUS_OPTIONS = [
        "Applied", "Phone Screen", "1st Interview",
        "2nd Interview", "Final Round", "Verbal Offer",
        "Offer Received", "Rejected", "No Response",
    ]

    # ── Add entry manually ────────────────────────────────────────────────────
    with st.expander("➕ Add Entry Manually", expanded=False):
        m_c1, m_c2 = st.columns(2)
        with m_c1:
            m_title = st.text_input("Job Title", key="manual_title")
            m_company = st.text_input("Company", key="manual_company")
            m_location = st.text_input("Location", key="manual_location")
        with m_c2:
            m_work_type = st.selectbox("Work Type", ["Hybrid", "Remote", "On-site"], key="manual_work_type")
            m_status = st.selectbox("Status", _STATUS_OPTIONS, key="manual_status")
            m_fit = st.number_input("Fit %", min_value=0, max_value=100, value=0, key="manual_fit")
            m_date = st.date_input("Date Applied", value=datetime.today(), key="manual_date")
        if st.button("Add Entry", key="manual_add_btn"):
            if m_title.strip() or m_company.strip():
                st.session_state.app_log.append({
                    "date": str(m_date),
                    "job_title": m_title,
                    "company": m_company,
                    "location": m_location,
                    "work_type": m_work_type,
                    "fit_pct": m_fit,
                    "status": m_status,
                })
                _patch_saved(app_log=st.session_state.app_log)
                st.success("Entry added!")
                st.rerun()
            else:
                st.warning("Please enter at least a Job Title or Company.")

    st.divider()

    if not st.session_state.app_log:
        st.info("No applications logged yet. Add an entry above, or mark a tailored resume as applied.")
    else:
        # Migrate any entries missing status
        for _e in st.session_state.app_log:
            if "status" not in _e:
                _e["status"] = "Applied"

        # Display editable table
        import pandas as pd
        df = pd.DataFrame(st.session_state.app_log)
        if "status" not in df.columns:
            df["status"] = "Applied"
        _col_order = [c for c in ["date", "company", "job_title", "status", "location", "work_type", "fit_pct"] if c in df.columns]
        df = df[_col_order]
        edited_df = st.data_editor(
            df,
            column_config={
                "date":      st.column_config.TextColumn("Date"),
                "company":   st.column_config.TextColumn("Company"),
                "job_title": st.column_config.TextColumn("Job Title"),
                "status":    st.column_config.SelectboxColumn("Status", options=_STATUS_OPTIONS, required=True),
                "location":  st.column_config.TextColumn("Location"),
                "work_type": st.column_config.TextColumn("Work Type"),
                "fit_pct":   st.column_config.NumberColumn("Fit %", min_value=0, max_value=100),
            },
            hide_index=True,
            use_container_width=True,
            key="log_editor",
        )
        if edited_df.to_dict("records") != st.session_state.app_log:
            st.session_state.app_log = edited_df.to_dict("records")
            _patch_saved(app_log=st.session_state.app_log)

        st.markdown("")
        exp_col1, exp_col2, _ = st.columns([1, 1, 2])

        with exp_col1:
            try:
                docx_log = build_log_docx(st.session_state.app_log)
                st.download_button(
                    label="⬇️ Export DOCX",
                    data=docx_log,
                    file_name="application_log.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    use_container_width=True,
                )
            except Exception as e:
                st.error(f"DOCX export error: {e}")

        with exp_col2:
            try:
                csv_log = build_log_csv(st.session_state.app_log)
                st.download_button(
                    label="⬇️ Export CSV",
                    data=csv_log,
                    file_name="application_log.csv",
                    mime="text/csv",
                    use_container_width=True,
                )
            except Exception as e:
                st.error(f"CSV export error: {e}")

        st.markdown("")
        if st.button("🗑️ Clear Log", type="secondary"):
            st.session_state.app_log = []
            _patch_saved(app_log=[])
            st.rerun()


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — INTERVIEW PREP
# ══════════════════════════════════════════════════════════════════════════════
with tab_prep:
    st.markdown("### Interview Prep")
    st.caption("Generate realistic practice questions for any role and get scored AI feedback on your answers.")

    if not api_key:
        st.warning("Configure an AI provider in the sidebar to use Interview Prep.")
    else:
        # ── A) Job selector ───────────────────────────────────────────────────
        st.markdown("#### Select a Job")
        use_log_job = st.toggle("Pick from Application Log", value=bool(st.session_state.app_log), key="prep_use_log")

        prep_company = ""
        prep_role = ""

        if use_log_job:
            if st.session_state.app_log:
                _job_labels = [
                    f"{e.get('company', '?')} — {e.get('job_title', '?')}"
                    for e in st.session_state.app_log
                ]
                _selected_label = st.selectbox("Select job", _job_labels, key="prep_job_select")
                _selected_entry = st.session_state.app_log[_job_labels.index(_selected_label)]
                prep_company = _selected_entry.get("company", "")
                prep_role = _selected_entry.get("job_title", "")
            else:
                st.info("No jobs in your Application Log yet. Toggle off to enter manually.")

        if not use_log_job or not st.session_state.app_log:
            _pc1, _pc2 = st.columns(2)
            with _pc1:
                prep_company = st.text_input("Company", key="prep_company_manual")
            with _pc2:
                prep_role = st.text_input("Role / Job Title", key="prep_role_manual")

        load_btn = st.button("Load Questions", type="primary", key="prep_load_btn")

        if load_btn:
            if not prep_company and not prep_role:
                st.warning("Enter a company and/or role to generate questions.")
            else:
                with st.spinner("⚙️ SeArChInG iNtErViEw CoNtEnT... BeEp BoOp..."):
                    web_ctx = search_interview_content(prep_company, prep_role)
                with st.spinner("⚙️ GeNeRaTiNg QuEsTiOnS..."):
                    try:
                        qs = generate_questions(
                            company=prep_company,
                            role=prep_role,
                            count=3,
                            web_context=web_ctx,
                            provider=_selected_cfg,
                            api_key=api_key,
                        )
                        st.session_state.prep_questions = qs
                        st.session_state.prep_job = {"company": prep_company, "role": prep_role}
                        st.session_state.prep_chat = []
                        st.session_state.prep_active_q = None
                    except Exception as _e:
                        st.error(f"Could not generate questions: {_e}")

        # ── B/C) Question list ─────────────────────────────────────────────────
        if st.session_state.prep_questions:
            st.markdown("---")
            _pj = st.session_state.prep_job
            st.markdown(f"#### Questions — {_pj['role']} at {_pj['company']}")

            for _qi, _q in enumerate(st.session_state.prep_questions):
                _qc1, _qc2 = st.columns([5, 1])
                with _qc1:
                    st.markdown(
                        f'<div class="history-card" style="margin-bottom:0.4rem">'
                        f'<span style="color:#CC0000;font-family:\'Share Tech Mono\',monospace">Q{_qi + 1}.</span> {_q}'
                        f"</div>",
                        unsafe_allow_html=True,
                    )
                with _qc2:
                    if st.button("Practice →", key=f"prep_q_{_qi}", use_container_width=True):
                        st.session_state.prep_active_q = _q
                        st.session_state.prep_chat = []
                        st.rerun()

            if st.button("Ask 3 More", key="prep_more_btn"):
                with st.spinner("⚙️ GeNeRaTiNg MoRe QuEsTiOnS..."):
                    try:
                        _more = generate_questions(
                            company=st.session_state.prep_job["company"],
                            role=st.session_state.prep_job["role"],
                            count=3,
                            web_context="",
                            provider=_selected_cfg,
                            api_key=api_key,
                        )
                        st.session_state.prep_questions.extend(_more)
                        st.rerun()
                    except Exception as _e:
                        st.error(f"Could not generate more questions: {_e}")

        # ── D) Chat interface ──────────────────────────────────────────────────
        if st.session_state.prep_active_q:
            st.markdown("---")
            st.markdown("#### Practice Session")

            with st.chat_message("assistant"):
                st.markdown(f"**{st.session_state.prep_active_q}**")

            for _msg in st.session_state.prep_chat:
                with st.chat_message(_msg["role"]):
                    st.markdown(_msg["content"])
                    if _msg.get("score") is not None:
                        _sv = _msg["score"]
                        _sc = _score_color(_sv)
                        st.markdown(
                            f'<span style="color:{_sc};font-size:1.05rem;font-weight:700">'
                            f"Score: {_sv}/100</span>",
                            unsafe_allow_html=True,
                        )

            _user_answer = st.chat_input("Type your answer...", key="prep_chat_input")
            if _user_answer:
                st.session_state.prep_chat.append({"role": "user", "content": _user_answer})
                with st.spinner("⚙️ AnAlYzInG yOuR aNsWeR..."):
                    try:
                        _rating = rate_answer(
                            company=st.session_state.prep_job["company"],
                            role=st.session_state.prep_job["role"],
                            question=st.session_state.prep_active_q,
                            answer=_user_answer,
                            provider=_selected_cfg,
                            api_key=api_key,
                        )
                        _sv = _rating["score"]
                        _sc = _score_color(_sv)
                        _fb_md = (
                            f"**Score: {_sv}/100**\n\n"
                            f"{_rating['feedback']}"
                        )
                        if _rating["strengths"]:
                            _fb_md += "\n\n**✅ Strengths:**\n" + "\n".join(
                                f"- {s}" for s in _rating["strengths"]
                            )
                        if _rating["improvements"]:
                            _fb_md += "\n\n**💡 Improvements:**\n" + "\n".join(
                                f"- {s}" for s in _rating["improvements"]
                            )
                        st.session_state.prep_chat.append({
                            "role": "assistant",
                            "content": _fb_md,
                            "score": _sv,
                        })
                        st.rerun()
                    except Exception as _e:
                        st.error(f"Could not rate answer: {_e}")
