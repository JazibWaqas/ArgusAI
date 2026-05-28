"""
Formal PDF layout for a ForensicReport.

Kept separate from analysis pipeline, detectors, and reasoning.
Callers should catch exceptions and map to HTTP errors.
"""

from __future__ import annotations

import io
import re
from typing import List, Optional, Tuple

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from ..models.evidence import EvidenceSignal
from ..models.report import ForensicReport, Verdict

_MAX_PARA_LEN = 48_000
_MAX_KEY_FINDINGS = 8
_KEY_FINDING_MAX_CHARS = 520
_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

_VERDICT_DISPLAY = {
    Verdict.LIKELY_AUTHENTIC: "Likely authentic (camera-captured)",
    Verdict.LIKELY_AI_GENERATED: "Likely AI Generated",
    Verdict.INCONCLUSIVE: "Inconclusive",
}


def _safe_snippet(text: Optional[str], limit: int = 2000) -> str:
    if not text:
        return ""
    s = str(text).strip()
    s = _CONTROL_CHAR_RE.sub(" ", s)
    if len(s) > limit:
        s = s[: limit - 1] + "…"
    return s


def _truncate_at_word(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    cut = text[: max(1, limit - 1)]
    sp = cut.rfind(" ")
    if sp > limit // 2:
        cut = cut[:sp].rstrip()
    return cut + "…"


def _para_xml(text: str) -> str:
    s = _safe_snippet(text, _MAX_PARA_LEN)
    s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return s.replace("\n", "<br/>")


def _format_verdict(v: Verdict) -> str:
    if v in _VERDICT_DISPLAY:
        return _VERDICT_DISPLAY[v]
    t = v.value.replace("_", " ").title()
    return re.sub(r"\bAi\b", "AI", t)


def _support_label_table(supports: str) -> str:
    m = {
        "authentic": "Authentic-leaning",
        "ai_generated": "AI / synthetic-leaning",
        "inconclusive": "Inconclusive",
        "unknown": "Unknown",
    }
    return m.get((supports or "unknown").lower(), supports or "Unknown")


def _supports_str(sig: EvidenceSignal) -> str:
    s = sig.supports
    return s.value if hasattr(s, "value") else str(s)


def _status_str(sig: EvidenceSignal) -> str:
    st = sig.status
    return st.value if hasattr(st, "value") else str(st)


def _key_findings(signals: List[EvidenceSignal]) -> List[str]:
    def sort_key(sig: EvidenceSignal) -> Tuple[int, float]:
        inf = sig.verdict_influence_percent
        return (-(inf if inf is not None else -1), -sig.reliability)

    ranked = sorted(signals, key=sort_key)
    out: List[str] = []
    for sig in ranked[:_MAX_KEY_FINDINGS]:
        raw = (sig.summary or "").strip() or (sig.what_found or "").strip() or "No summary."
        line = _truncate_at_word(_CONTROL_CHAR_RE.sub(" ", raw), _KEY_FINDING_MAX_CHARS)
        name = _safe_snippet(sig.name, 120) or sig.id
        out.append(f"{name}: {line}")
    return out


def _evidence_table_paragraph_rows(
    signals: List[EvidenceSignal],
    hdr_style: ParagraphStyle,
    cell_style: ParagraphStyle,
) -> List[List[Paragraph]]:
    rows: List[List[Paragraph]] = [
        [
            Paragraph(_para_xml("Signal"), hdr_style),
            Paragraph(_para_xml("Indicated support"), hdr_style),
            Paragraph(_para_xml("Weight %"), hdr_style),
            Paragraph(_para_xml("Status"), hdr_style),
        ]
    ]
    for sig in sorted(
        signals,
        key=lambda s: (-(s.verdict_influence_percent or -1), s.name),
    ):
        w = "" if sig.verdict_influence_percent is None else str(sig.verdict_influence_percent)
        rows.append(
            [
                Paragraph(_para_xml(_safe_snippet(sig.name, 500) or sig.id), cell_style),
                Paragraph(_para_xml(_support_label_table(_supports_str(sig))), cell_style),
                Paragraph(_para_xml(w), cell_style),
                Paragraph(_para_xml(_status_str(sig)), cell_style),
            ]
        )
    return rows


def build_official_forensic_pdf(
    report: ForensicReport,
    *,
    reference_id: Optional[str] = None,
) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
        title="Forensic Assessment Report",
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Heading1"],
        fontName="Times-Bold",
        fontSize=16,
        leading=20,
        alignment=TA_CENTER,
        spaceAfter=6,
    )
    sub_style = ParagraphStyle(
        "DocSub",
        parent=styles["Normal"],
        fontName="Times-Roman",
        fontSize=10,
        leading=14,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#333333"),
        spaceAfter=16,
    )
    h_style = ParagraphStyle(
        "Section",
        parent=styles["Heading2"],
        fontName="Times-Bold",
        fontSize=12,
        leading=15,
        spaceBefore=14,
        spaceAfter=8,
    )
    body = ParagraphStyle(
        "Body",
        parent=styles["Normal"],
        fontName="Times-Roman",
        fontSize=10,
        leading=14,
        alignment=TA_JUSTIFY,
    )
    bullet = ParagraphStyle(
        "Bullet",
        parent=body,
        leftIndent=18,
        bulletIndent=8,
        spaceAfter=6,
    )
    meta = ParagraphStyle(
        "Meta",
        parent=styles["Normal"],
        fontName="Times-Roman",
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#444444"),
    )
    table_hdr = ParagraphStyle(
        "TblHdr",
        parent=styles["Normal"],
        fontName="Times-Bold",
        fontSize=8,
        leading=11,
    )
    table_cell = ParagraphStyle(
        "TblCell",
        parent=styles["Normal"],
        fontName="Times-Roman",
        fontSize=8,
        leading=11,
    )

    story: list = []

    story.append(Paragraph("Forensic Image Authenticity Assessment", title_style))
    story.append(Paragraph("ArgusAI — Automated forensic screening", sub_style))

    gen = report.generated_at
    if gen.tzinfo is not None:
        ts = gen.strftime("%Y-%m-%d %H:%M UTC")
    else:
        ts = gen.strftime("%Y-%m-%d %H:%M") + " (local)"

    story.append(Paragraph(_para_xml(f"Report generated: {ts}"), meta))
    if reference_id:
        story.append(Paragraph(_para_xml(f"Reference: {reference_id}"), meta))
    story.append(Spacer(1, 0.15 * inch))

    img = report.evidence.image
    story.append(Paragraph("1. Subject record", h_style))
    story.append(
        Paragraph(
            _para_xml(
                f"Image dimensions: {img.width} × {img.height} pixels. "
                f"Mode: {img.mode}. "
                f"Format: {img.format or 'unknown'}. "
                f"SHA-256: {img.sha256}."
            ),
            body,
        )
    )

    story.append(Paragraph("2. Conclusion (authenticity)", h_style))
    verdict_line = (
        f"Finding: {_format_verdict(report.verdict)}. "
        f"Overall certainty: {round(report.certainty * 100)}%. "
        f"Confidence band: {_safe_snippet(report.confidence_label, 200)}."
    )
    story.append(Paragraph(_para_xml(verdict_line), body))
    if report.verdict == Verdict.INCONCLUSIVE and report.leaning:
        story.append(
            Paragraph(
                _para_xml(
                    f"Where evidence is mixed, the stronger lean is: {_format_verdict(report.leaning)}."
                ),
                body,
            )
        )
    story.append(Spacer(1, 0.08 * inch))

    story.append(Paragraph("3. Executive summary", h_style))
    story.append(Paragraph(_para_xml(report.short_summary), body))

    story.append(Paragraph("4. Key findings", h_style))
    findings = _key_findings(report.evidence.signals)
    if not findings:
        story.append(Paragraph(_para_xml("No structured signal summaries were available."), body))
    else:
        for ftext in findings:
            story.append(Paragraph(_para_xml(ftext), bullet, bulletText="•"))

    story.append(Paragraph("5. Evidence overview", h_style))
    tbl = Table(
        _evidence_table_paragraph_rows(report.evidence.signals, table_hdr, table_cell),
        colWidths=[1.85 * inch, 2.45 * inch, 0.65 * inch, 0.85 * inch],
    )
    tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8e8e8")),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.append(tbl)

    story.append(Paragraph("6. Assessment narrative", h_style))
    expl = report.explanation.strip()
    parts = [p.strip() for p in expl.split("\n\n") if p.strip()]
    if not parts:
        parts = [expl] if expl else ["No narrative was attached to this report."]
    for part in parts[:40]:
        story.append(Paragraph(_para_xml(part), body))
        story.append(Spacer(1, 0.06 * inch))

    if report.evidence.warnings:
        story.append(Paragraph("Pipeline notices", h_style))
        for w in report.evidence.warnings[:20]:
            story.append(Paragraph(_para_xml(f"• {_safe_snippet(w, 500)}"), body))

    story.append(Paragraph("7. Limitations", h_style))
    limitations = (
        "This assessment is produced by automated forensic detectors and heuristics. "
        "It is not legal or scientific certification of origin. "
        "Results depend on image quality, compression, and which detectors succeeded. "
        "Adversarial editing or uncommon generators may not be represented in training data. "
        "Use this report as one input to human judgment, not as a sole determinant."
    )
    story.append(Paragraph(_para_xml(limitations), body))

    doc.build(story)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes
