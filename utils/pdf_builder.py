# utils/pdf_builder.py — Build an ATS-friendly PDF resume using ReportLab

import io
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, HRFlowable, ListFlowable, ListItem
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT

BRAND_COLOR = colors.HexColor("#4F46E5")
DARK_GRAY = colors.HexColor("#444444")
BLACK = colors.black


def _styles():
    base = getSampleStyleSheet()
    custom = {}

    custom["name"] = ParagraphStyle(
        "name", parent=base["Normal"],
        fontSize=20, fontName="Helvetica-Bold",
        textColor=BLACK, alignment=TA_CENTER,
        spaceAfter=2,
    )
    custom["contact"] = ParagraphStyle(
        "contact", parent=base["Normal"],
        fontSize=9, fontName="Helvetica",
        textColor=DARK_GRAY, alignment=TA_CENTER,
        spaceAfter=8,
    )
    custom["section"] = ParagraphStyle(
        "section", parent=base["Normal"],
        fontSize=11, fontName="Helvetica-Bold",
        textColor=BRAND_COLOR, alignment=TA_LEFT,
        spaceBefore=10, spaceAfter=2,
    )
    custom["job_title"] = ParagraphStyle(
        "job_title", parent=base["Normal"],
        fontSize=11, fontName="Helvetica-Bold",
        textColor=BLACK, spaceBefore=6, spaceAfter=1,
    )
    custom["meta"] = ParagraphStyle(
        "meta", parent=base["Normal"],
        fontSize=10, fontName="Helvetica-Oblique",
        textColor=DARK_GRAY, spaceAfter=2,
    )
    custom["body"] = ParagraphStyle(
        "body", parent=base["Normal"],
        fontSize=10, fontName="Helvetica",
        textColor=BLACK, spaceAfter=4, leading=14,
    )
    custom["bullet"] = ParagraphStyle(
        "bullet", parent=base["Normal"],
        fontSize=10, fontName="Helvetica",
        textColor=BLACK, spaceAfter=1, leading=14,
        leftIndent=12, bulletIndent=0,
    )
    return custom


def build_pdf(data: dict) -> bytes:
    """Build an ATS-friendly PDF from structured resume data. Returns bytes."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )

    S = _styles()
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
        story.append(Paragraph("PROFESSIONAL SUMMARY", S["section"]))
        story.append(HRFlowable(width="100%", thickness=1, color=BRAND_COLOR, spaceAfter=4))
        story.append(Paragraph(summary, S["body"]))

    # ── Experience ────────────────────────────────────────────────────────────
    experience = data.get("experience", [])
    if experience:
        story.append(Paragraph("EXPERIENCE", S["section"]))
        story.append(HRFlowable(width="100%", thickness=1, color=BRAND_COLOR, spaceAfter=4))
        for job in experience:
            story.append(Paragraph(job.get("title", ""), S["job_title"]))
            company = job.get("company", "")
            location = job.get("location", "")
            dates = job.get("dates", "")
            meta = company + (f"  —  {location}" if location else "") + (f"   {dates}" if dates else "")
            story.append(Paragraph(meta, S["meta"]))
            for bullet in job.get("bullets", []):
                story.append(Paragraph(f"• {bullet}", S["bullet"]))

    # ── Education ─────────────────────────────────────────────────────────────
    education = data.get("education", [])
    if education:
        story.append(Paragraph("EDUCATION", S["section"]))
        story.append(HRFlowable(width="100%", thickness=1, color=BRAND_COLOR, spaceAfter=4))
        for edu in education:
            story.append(Paragraph(edu.get("degree", ""), S["job_title"]))
            school = edu.get("school", "")
            loc = edu.get("location", "")
            dates = edu.get("dates", "")
            meta = school + (f"  —  {loc}" if loc else "") + (f"   {dates}" if dates else "")
            story.append(Paragraph(meta, S["meta"]))
            if edu.get("details"):
                story.append(Paragraph(edu["details"], S["body"]))

    # ── Skills ────────────────────────────────────────────────────────────────
    skills = data.get("skills", [])
    if skills:
        story.append(Paragraph("SKILLS", S["section"]))
        story.append(HRFlowable(width="100%", thickness=1, color=BRAND_COLOR, spaceAfter=4))
        chunk_size = 4
        rows = [skills[i:i+chunk_size] for i in range(0, len(skills), chunk_size)]
        for row in rows:
            story.append(Paragraph("  •  ".join(row), S["body"]))

    # ── Certifications ────────────────────────────────────────────────────────
    certs = data.get("certifications", [])
    if certs:
        story.append(Paragraph("CERTIFICATIONS", S["section"]))
        story.append(HRFlowable(width="100%", thickness=1, color=BRAND_COLOR, spaceAfter=4))
        for cert in certs:
            story.append(Paragraph(f"• {cert}", S["bullet"]))

    doc.build(story)
    buf.seek(0)
    return buf.read()
