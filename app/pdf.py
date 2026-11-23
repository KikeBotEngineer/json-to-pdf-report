from datetime import UTC, datetime
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.charts import ChartImage
from app.metrics import Metrics
from app.models import ReportRequest

INK = colors.HexColor("#1e293b")
MUTED = colors.HexColor("#64748b")
HEADER_BG = colors.HexColor("#334155")
STRIPE = colors.HexColor("#f1f5f9")
RULE = colors.HexColor("#cbd5e1")

CONTENT_WIDTH = A4[0] - 4 * cm
CHART_ASPECT = 3.6 / 7  # matches the figure size in charts.py

_base = getSampleStyleSheet()
COVER_TITLE = ParagraphStyle("CoverTitle", _base["Title"], fontSize=28, leading=34, textColor=INK)
COVER_LINE = ParagraphStyle(
    "CoverLine", _base["Normal"], fontSize=12, leading=18, textColor=MUTED, alignment=TA_CENTER
)
H2 = ParagraphStyle("H2", _base["Heading2"], textColor=INK, spaceBefore=12, spaceAfter=8)
BODY = ParagraphStyle("Body", _base["Normal"], textColor=INK)


def _hours(x: float | None) -> str:
    return "—" if x is None else f"{x:,.1f} h"


def _table(rows: list[list[str]], col_widths: list[float]) -> Table:
    t = Table(rows, colWidths=col_widths, hAlign="LEFT")
    t.setStyle(
        TableStyle(
            [
                ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 10),
                ("FONT", (0, 1), (-1, -1), "Helvetica", 10),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG),
                ("TEXTCOLOR", (0, 1), (-1, -1), INK),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, STRIPE]),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                ("LINEBELOW", (0, -1), (-1, -1), 0.5, RULE),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return t


def _cover(req: ReportRequest, m: Metrics) -> list:
    generated = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    return [
        Spacer(1, 7 * cm),
        Paragraph(escape(req.title), COVER_TITLE),
        Spacer(1, 1 * cm),
        Paragraph(f"Periodo: {req.period.start} a {req.period.end}", COVER_LINE),
        Paragraph(f"Generado: {generated}", COVER_LINE),
        Paragraph(f"Total de tickets: {m.total:,}", COVER_LINE),
        PageBreak(),
    ]


def _summary(m: Metrics) -> list:
    rows = [
        ["Indicador", "Valor"],
        ["Total de tickets", f"{m.total:,}"],
        ["Abiertos", f"{m.open:,}"],
        ["Resueltos", f"{m.resolved:,}"],
        ["% resueltos", f"{m.pct_resolved:.1f} %"],
        ["Tiempo medio de resolución", _hours(m.mean_hours)],
        ["Tiempo mediano de resolución", _hours(m.median_hours)],
        ["P90 de resolución", _hours(m.p90_hours)],
    ]
    return [Paragraph("Resumen", H2), _table(rows, [10 * cm, 5 * cm])]


def _chart(c: ChartImage) -> KeepTogether:
    img = Image(c.png, width=CONTENT_WIDTH, height=CONTENT_WIDTH * CHART_ASPECT)
    return KeepTogether([Paragraph(c.title, H2), img])


def _priority(m: Metrics) -> list:
    rows = [["Prioridad", "Tickets", "Tiempo medio de resolución"]]
    rows += [[r.priority, f"{r.count:,}", _hours(r.mean_hours)] for r in m.by_priority]
    return [Paragraph("Detalle por prioridad", H2), _table(rows, [5 * cm, 4 * cm, 6 * cm])]


def _footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(MUTED)
    canvas.drawRightString(A4[0] - 2 * cm, 1.2 * cm, f"Página {doc.page}")
    canvas.restoreState()


def build(req: ReportRequest, m: Metrics, charts: list[ChartImage]) -> bytes:
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title=req.title,
    )
    story = _cover(req, m) + _summary(m)
    story += [_chart(c) for c in charts]
    story += _priority(m)
    doc.build(story, onLaterPages=_footer)
    return buf.getvalue()
