# utils/pdf_builder.py — Build an ATS-friendly PDF resume using ReportLab

import copy
import io
from xml.sax.saxutils import escape
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, HRFlowable, ListFlowable, ListItem,
    Table, TableStyle,
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT


class _SectionGap(Spacer):
    """Elastic spacer placed between resume sections.
    After the full story is built, _stretch_gaps() redistributes remaining
    page space evenly across all gap instances so the resume fills the page
    without overflowing.
    """
    BASE = 5    # minimum gap height (points)
    MAX_ADD = 18  # max extra points added per gap

BRAND_COLOR = colors.HexColor("#4F46E5")
DARK_GRAY = colors.HexColor("#444444")
BLACK = colors.black


def _styles(tight: bool = False):
    base = getSampleStyleSheet()
    custom = {}

    # Tight mode: smaller fonts and tighter spacing to recover vertical space
    fs = 9 if tight else 10
    lead = 11 if tight else 12

    custom["name"] = ParagraphStyle(
        "name", parent=base["Normal"],
        fontSize=18, fontName="Helvetica-Bold",
        leading=24,
        textColor=BLACK, alignment=TA_CENTER,
        spaceAfter=2,
    )
    custom["contact"] = ParagraphStyle(
        "contact", parent=base["Normal"],
        fontSize=9, fontName="Helvetica",
        textColor=DARK_GRAY, alignment=TA_CENTER,
        spaceAfter=4 if tight else 6,
    )
    custom["section"] = ParagraphStyle(
        "section", parent=base["Normal"],
        fontSize=11, fontName="Helvetica-Bold",
        textColor=BRAND_COLOR, alignment=TA_LEFT,
        spaceBefore=1 if tight else 2, spaceAfter=1,
    )
    custom["job_title"] = ParagraphStyle(
        "job_title", parent=base["Normal"],
        fontSize=11, fontName="Helvetica-Bold",
        textColor=BLACK, spaceBefore=1 if tight else 3, spaceAfter=0,
    )
    custom["meta"] = ParagraphStyle(
        "meta", parent=base["Normal"],
        fontSize=fs, fontName="Helvetica-Oblique",
        textColor=DARK_GRAY, spaceAfter=0,
    )
    custom["meta_right"] = ParagraphStyle(
        "meta_right", parent=base["Normal"],
        fontSize=fs, fontName="Helvetica-Oblique",
        textColor=DARK_GRAY, spaceAfter=0,
        alignment=TA_CENTER,
    )
    custom["body"] = ParagraphStyle(
        "body", parent=base["Normal"],
        fontSize=fs, fontName="Helvetica",
        textColor=BLACK, spaceAfter=1 if tight else 2, leading=lead,
    )
    custom["bullet"] = ParagraphStyle(
        "bullet", parent=base["Normal"],
        fontSize=fs, fontName="Helvetica",
        textColor=BLACK, spaceAfter=0, leading=lead,
        leftIndent=12, bulletIndent=0,
    )
    custom["skill_cat"] = ParagraphStyle(
        "skill_cat", parent=base["Normal"],
        fontSize=fs, fontName="Helvetica",
        textColor=BLACK, spaceAfter=0 if tight else 1, leading=lead,
    )
    return custom


_LEFT_MARGIN = 0.75 * inch
_RIGHT_MARGIN = 0.75 * inch
_TOP_MARGIN = 0.5 * inch
_BOTTOM_MARGIN = 0.5 * inch
_USABLE_WIDTH = letter[0] - _LEFT_MARGIN - _RIGHT_MARGIN
_USABLE_HEIGHT = letter[1] - _TOP_MARGIN - _BOTTOM_MARGIN


def _flowable_height(f) -> float:
    """Return total rendered height of a flowable including its style spacing."""
    try:
        _, h = f.wrap(_USABLE_WIDTH, _USABLE_HEIGHT)
    except Exception:
        h = 0
    style = getattr(f, "style", None)
    if style:
        h += getattr(style, "spaceBefore", 0) + getattr(style, "spaceAfter", 0)
    else:
        h += getattr(f, "spaceBefore", 0) + getattr(f, "spaceAfter", 0)
    return float(h)


def _stretch_gaps(story: list) -> None:
    """Measure total story height and grow _SectionGap spacers to fill the page.

    Extra space is distributed evenly across all gaps, capped at MAX_ADD per gap
    so the spacing stays tasteful.  If content is already near-full, gaps stay at BASE.
    """
    gap_indices = [i for i, f in enumerate(story) if isinstance(f, _SectionGap)]
    if not gap_indices:
        return

    total_h = sum(_flowable_height(f) for f in story)
    remaining = _USABLE_HEIGHT - total_h

    if remaining > 2:
        extra = min(remaining / len(gap_indices), _SectionGap.MAX_ADD)
        for idx in gap_indices:
            # Use actual current height so math is correct regardless of gap_base
            current_h = story[idx].height
            story[idx] = _SectionGap(1, current_h + extra)


def _meta_row(left_text: str, dates: str, styles: dict):
    """One-row table that pins company/location left and dates right, no wrapping."""
    if not dates:
        return Paragraph(left_text, styles["meta"])
    left_col = _USABLE_WIDTH * 0.65
    right_col = _USABLE_WIDTH * 0.35
    tbl = Table(
        [[Paragraph(left_text, styles["meta"]), Paragraph(dates, styles["meta_right"])]],
        colWidths=[left_col, right_col],
    )
    tbl.setStyle(TableStyle([
        ("VALIGN",         (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING",    (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",   (0, 0), (-1, -1), 0),
        ("TOPPADDING",     (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING",  (0, 0), (-1, -1), 2),
    ]))
    return tbl


def _build_story(data: dict, S: dict, gap_base: float = _SectionGap.BASE) -> list:
    """Construct the full list of flowables for the resume."""
    story = []

    # ── Name ──────────────────────────────────────────────────────────────────
    story.append(Paragraph(data.get("name", ""), S["name"]))

    # ── Contact ───────────────────────────────────────────────────────────────
    contact_parts = [
        data.get("phone", ""),
        data.get("email", ""),
        data.get("location", ""),
        data.get("linkedin", ""),
        data.get("website", ""),
    ]
    contact_line = "  |  ".join(p for p in contact_parts if p)
    if contact_line:
        story.append(Paragraph(contact_line, S["contact"]))

    # ── Summary ───────────────────────────────────────────────────────────────
    summary = data.get("summary", "")
    if summary:
        story.append(_SectionGap(1, gap_base))
        story.append(Paragraph("PROFESSIONAL SUMMARY", S["section"]))
        story.append(HRFlowable(width="100%", thickness=1, color=BRAND_COLOR, spaceAfter=2))
        story.append(Paragraph(summary, S["body"]))

    # ── Skills ────────────────────────────────────────────────────────────────
    skills = data.get("skills", {})
    if skills:
        story.append(_SectionGap(1, gap_base))
        story.append(Paragraph("SKILLS", S["section"]))
        story.append(HRFlowable(width="100%", thickness=1, color=BRAND_COLOR, spaceAfter=2))
        if isinstance(skills, dict):
            for cat, items in skills.items():
                line = f"<b>{escape(cat)}:</b>  {escape(', '.join(str(s) for s in items))}"
                story.append(Paragraph(line, S["skill_cat"]))
        else:
            story.append(Paragraph(", ".join(str(s) for s in skills), S["body"]))

    # ── Experience ────────────────────────────────────────────────────────────
    experience = data.get("experience", [])
    if experience:
        story.append(_SectionGap(1, gap_base))
        story.append(Paragraph("EXPERIENCE", S["section"]))
        story.append(HRFlowable(width="100%", thickness=1, color=BRAND_COLOR, spaceAfter=2))
        for job in experience:
            story.append(Paragraph(job.get("title", ""), S["job_title"]))
            company = job.get("company", "")
            location = job.get("location", "")
            dates = job.get("dates", "")
            left = company + (f"  —  {location}" if location else "")
            story.append(_meta_row(left, dates, S))
            for bullet in job.get("bullets", []):
                story.append(Paragraph(f"• {bullet}", S["bullet"]))

    # ── Education ─────────────────────────────────────────────────────────────
    education = data.get("education", [])
    if education:
        story.append(_SectionGap(1, gap_base))
        story.append(Paragraph("EDUCATION", S["section"]))
        story.append(HRFlowable(width="100%", thickness=1, color=BRAND_COLOR, spaceAfter=2))
        for edu in education:
            story.append(Paragraph(edu.get("degree", ""), S["job_title"]))
            school = edu.get("school", "")
            loc = edu.get("location", "")
            dates = edu.get("dates", "")
            left = school + (f"  —  {loc}" if loc else "")
            story.append(_meta_row(left, dates, S))
            if edu.get("details"):
                story.append(Paragraph(edu["details"], S["body"]))

    # ── Certifications ────────────────────────────────────────────────────────
    certs = data.get("certifications", [])
    if certs:
        story.append(_SectionGap(1, gap_base))
        story.append(Paragraph("CERTIFICATIONS", S["section"]))
        story.append(HRFlowable(width="100%", thickness=1, color=BRAND_COLOR, spaceAfter=2))
        for cert in certs:
            story.append(Paragraph(f"• {cert}", S["bullet"]))

    return story


def _story_height(story: list) -> float:
    return sum(_flowable_height(f) for f in story)


def _trim_bullets(data: dict) -> dict:
    """Return a deep copy of data with one bullet removed from the oldest eligible role.

    Trims from the last (oldest) role first, working toward the first (most recent).
    Minimum 2 bullets per role in the first pass; drops to 1 if still overflowing.
    """
    data = copy.deepcopy(data)
    experience = data.get("experience", [])

    for min_bullets in (2, 1):
        for job in reversed(experience):
            bullets = job.get("bullets", [])
            if len(bullets) > min_bullets:
                job["bullets"] = bullets[:-1]
                return data

    return data  # nothing left to trim


def build_pdf(data: dict) -> bytes:
    """Build an ATS-friendly PDF from structured resume data. Returns bytes."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        leftMargin=_LEFT_MARGIN,
        rightMargin=_RIGHT_MARGIN,
        topMargin=_TOP_MARGIN,
        bottomMargin=_BOTTOM_MARGIN,
    )

    # ── Pass 1: Normal styles ─────────────────────────────────────────────────
    S = _styles(tight=False)
    story = _build_story(data, S, gap_base=_SectionGap.BASE)

    if _story_height(story) > _USABLE_HEIGHT:
        # ── Pass 2: Tight styles, zero section gaps ───────────────────────────
        S = _styles(tight=True)
        story = _build_story(data, S, gap_base=0)

        # ── Pass 3+: Iteratively trim bullets until content fits ──────────────
        for _ in range(24):
            if _story_height(story) <= _USABLE_HEIGHT:
                break
            data = _trim_bullets(data)
            story = _build_story(data, S, gap_base=0)

    # Distribute remaining page space evenly across section gaps
    _stretch_gaps(story)

    doc.build(story)
    buf.seek(0)
    return buf.read()
