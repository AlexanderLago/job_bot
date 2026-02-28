import re
import traceback
from datetime import datetime

import streamlit as st

from utils.resume_parser import parse_resume
from utils.ai_tailor import tailor_resume
from utils.gemini_tailor import tailor_resume_gemini
from utils.scorer import score_resume
from utils.gemini_scorer import score_resume_gemini
from utils.docx_builder import build_docx
from utils.pdf_builder import build_pdf
from utils.job_scraper import scrape_job_url
from utils.log_builder import build_log_docx, build_log_csv

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
    .main-title {
        font-size: 2.8rem;
        font-weight: 800;
        background: linear-gradient(135deg, #4F46E5, #7C3AED);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0;
    }
    .subtitle {
        color: #94A3B8;
        font-size: 1rem;
        margin-top: 0;
        margin-bottom: 2rem;
    }
    .keyword-pill {
        display: inline-block;
        background: #1E293B;
        border: 1px solid #4F46E5;
        color: #A5B4FC;
        border-radius: 999px;
        padding: 2px 12px;
        font-size: 0.82rem;
        margin: 3px 3px 3px 0;
    }
    .section-label {
        font-size: 0.75rem;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        color: #64748B;
        margin-bottom: 4px;
    }
    .score-card {
        background: #1E293B;
        border: 1px solid #334155;
        border-radius: 12px;
        padding: 1rem 1.25rem;
        margin-bottom: 1rem;
    }
    .score-number {
        font-size: 3rem;
        font-weight: 800;
        line-height: 1;
    }
    .history-card {
        background: #1E293B;
        border: 1px solid #334155;
        border-radius: 10px;
        padding: 1rem;
        margin-bottom: 0.75rem;
    }
    div[data-testid="stDownloadButton"] button {
        width: 100%;
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


# ── Helpers ───────────────────────────────────────────────────────────────────

def _company_slug(company: str) -> str:
    return re.sub(r"[^a-z0-9]", "", company.lower()) or "company"


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
            st.success(f"✅ {master_file.name}")
        except Exception as e:
            st.error(f"Could not read master resume: {e}")
    elif st.session_state.master_resume_name:
        st.success(f"✅ {st.session_state.master_resume_name}")

    st.divider()

    # ── Provider / API key auto-detection ─────────────────────────────────────
    _DEFAULT_GEMINI_KEY = "AIzaSyAlEuUi0f3KqtxRiNH5n09cVTJN2eQKwHg"

    _ant_key, _gem_key = "", ""
    try:
        _ant_key = st.secrets.get("ANTHROPIC_API_KEY", "") or ""
        _gem_key = st.secrets.get("GEMINI_API_KEY", "") or ""
    except Exception:
        pass

    # Fall back to hardcoded default if no secrets configured
    if not _gem_key:
        _gem_key = _DEFAULT_GEMINI_KEY

    if _ant_key:
        provider = "anthropic"
        api_key = _ant_key
        st.markdown("**🤖 AI Provider**")
        st.success("Claude (Anthropic)")
    else:
        provider = "gemini"
        api_key = _gem_key
        st.markdown("**🤖 AI Provider**")
        st.success("Gemini (Google)")

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
    st.caption("Built with Claude Sonnet · [Anthropic](https://anthropic.com)")

# ── Main header ───────────────────────────────────────────────────────────────
st.markdown('<p class="main-title">Job Bot</p>', unsafe_allow_html=True)
st.markdown(
    '<p class="subtitle">Tailors your resume to any job posting — ATS-optimized, '
    'keyword-matched, never fabricated.</p>',
    unsafe_allow_html=True,
)

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab_tailor, tab_history, tab_log = st.tabs(["✨ Tailor", "📁 History", "📋 Application Log"])


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
                with st.spinner("Fetching job posting..."):
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
            with st.spinner("Scoring your resume fit..."):
                try:
                    if provider == "anthropic":
                        result = score_resume(active_resume, job_description, api_key)
                    else:
                        result = score_resume_gemini(active_resume, job_description, api_key)
                    st.session_state.last_score = result
                except Exception as e:
                    st.error(f"Scoring error: {e}")
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
            with st.spinner("Reading your resume..."):
                try:
                    resume_text = parse_resume(uploaded_file.read(), uploaded_file.name)
                except Exception as e:
                    st.error(f"Could not read resume: {e}")
                    st.stop()

        if not resume_text.strip():
            st.error("Could not extract any text from your resume. Try a .docx or .txt file.")
            st.stop()

        # Call AI provider
        provider_label = "Claude" if provider == "anthropic" else "Gemini"
        with st.spinner(f"Tailoring your resume with {provider_label} — this takes 15–30 seconds..."):
            try:
                if provider == "anthropic":
                    resume_data = tailor_resume(
                        resume_text=resume_text,
                        job_description=job_description,
                        api_key=api_key,
                        temperature=temperature,
                    )
                else:
                    resume_data = tailor_resume_gemini(
                        resume_text=resume_text,
                        job_description=job_description,
                        api_key=api_key,
                        temperature=temperature,
                    )
            except Exception as e:
                err_str = str(e)
                if "RESOURCE_EXHAUSTED" in err_str or "429" in err_str or "quota" in err_str.lower():
                    st.error(
                        "**Gemini free tier quota exceeded.** "
                        "This usually means the model isn't available on your project's free tier. "
                        "Try again in a few minutes, or visit "
                        "[Google AI Studio](https://aistudio.google.com/app/apikey) to create a "
                        "fresh API key in a new project."
                    )
                else:
                    st.error(f"AI error: {e}")
                    with st.expander("Debug info"):
                        st.code(traceback.format_exc())
                st.stop()

        company = resume_data.get("name", "")  # We'll get company from job later
        # Try to extract company from experience or data
        company_name = ""
        # If Claude put a company in the data use it; otherwise derive from job desc first line
        if resume_data.get("experience"):
            pass  # We need the target company, not from the resume
        # Extract first meaningful word group from job description as company fallback
        jd_lines = [ln.strip() for ln in job_description.splitlines() if ln.strip()]
        if jd_lines:
            company_name = jd_lines[0][:40]  # first line of JD often has company/title
        slug = _company_slug(company_name) if company_name else "tailored"

        # Build files
        docx_bytes, pdf_bytes = None, None
        if output_format in ("DOCX + PDF", "DOCX only"):
            with st.spinner("Building DOCX..."):
                try:
                    docx_bytes = build_docx(resume_data)
                except Exception as e:
                    st.error(f"DOCX build error: {e}")

        if output_format in ("DOCX + PDF", "PDF only"):
            with st.spinner("Building PDF..."):
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
        st.session_state.history.insert(0, history_entry)

        # ── Results ───────────────────────────────────────────────────────────
        st.divider()
        st.success("Your tailored resume is ready!")

        dl_col1, dl_col2, dl_col3 = st.columns([1, 1, 2])
        candidate_name = resume_data.get("name", "Resume").replace(" ", "_")
        docx_filename = f"resume_{slug}.docx"
        pdf_filename = f"resume_{slug}.pdf"

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

        # ── Add to log expander ───────────────────────────────────────────────
        with st.expander("➕ Add to Application Log", expanded=False):
            log_c1, log_c2 = st.columns(2)
            with log_c1:
                log_title = st.text_input("Job Title", value=history_entry["job_title"], key="log_title")
                log_company = st.text_input("Company", value=company_name, key="log_company")
                log_location = st.text_input("Location", placeholder="New York, NY", key="log_location")
            with log_c2:
                log_work_type = st.selectbox("Work Type", ["Hybrid", "Remote", "On-site"], key="log_work_type")
                log_fit = st.number_input(
                    "Fit %",
                    min_value=0, max_value=100,
                    value=history_entry["score"] or 0,
                    key="log_fit",
                )
                log_date = st.date_input("Date Applied", value=datetime.today(), key="log_date")
            if st.button("Add to Log", key="add_log_btn"):
                st.session_state.app_log.append({
                    "date": str(log_date),
                    "job_title": log_title,
                    "company": log_company,
                    "location": log_location,
                    "work_type": log_work_type,
                    "fit_pct": log_fit,
                })
                st.success("Added to your Application Log!")

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
            st.markdown(" · ".join(resume_data["skills"]))
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
    st.caption("All resumes tailored this session. Data clears when you close the tab.")

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


# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — APPLICATION LOG
# ══════════════════════════════════════════════════════════════════════════════
with tab_log:
    st.markdown("### Application Log")
    st.caption("Track every job you apply to. Export as DOCX or CSV to save your records.")

    # ── Add entry manually ────────────────────────────────────────────────────
    with st.expander("➕ Add Entry Manually", expanded=False):
        m_c1, m_c2 = st.columns(2)
        with m_c1:
            m_title = st.text_input("Job Title", key="manual_title")
            m_company = st.text_input("Company", key="manual_company")
            m_location = st.text_input("Location", key="manual_location")
        with m_c2:
            m_work_type = st.selectbox("Work Type", ["Hybrid", "Remote", "On-site"], key="manual_work_type")
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
                })
                st.success("Entry added!")
                st.rerun()
            else:
                st.warning("Please enter at least a Job Title or Company.")

    st.divider()

    if not st.session_state.app_log:
        st.info("No applications logged yet. Add an entry above, or use the log expander after tailoring a resume.")
    else:
        # Display table
        import pandas as pd
        df = pd.DataFrame(st.session_state.app_log)
        df.columns = ["Date", "Job Title", "Company", "Location", "Work Type", "Fit %"]
        st.dataframe(df, use_container_width=True, hide_index=True)

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
            st.rerun()
