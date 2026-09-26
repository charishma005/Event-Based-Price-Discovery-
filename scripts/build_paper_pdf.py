from __future__ import annotations

import html
import re
from datetime import date
from pathlib import Path

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PAPER = PROJECT_ROOT / "paper" / "research_paper.md"
OUTPUT = PROJECT_ROOT / "output" / "pdf" / "how_markets_absorb_news.pdf"


def _font(name: str, fallback: str) -> str:
    candidates = {
        "serif": [
            "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
            "/System/Library/Fonts/Supplemental/Georgia.ttf",
        ],
        "sans": [
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
        ],
    }
    for candidate in candidates[name]:
        path = Path(candidate)
        if path.exists() and path.suffix.lower() == ".ttf":
            font_name = f"Paper{name.title()}"
            pdfmetrics.registerFont(TTFont(font_name, str(path)))
            return font_name
    return fallback


SERIF = _font("serif", "Times-Roman")
SANS = _font("sans", "Helvetica")


class PaperDocTemplate(BaseDocTemplate):
    def __init__(self, filename: str) -> None:
        super().__init__(
            filename,
            pagesize=letter,
            leftMargin=0.78 * inch,
            rightMargin=0.78 * inch,
            topMargin=0.75 * inch,
            bottomMargin=0.70 * inch,
            title="How Markets Absorb News",
            author="Empirical Finance Research Project",
        )
        frame = Frame(
            self.leftMargin,
            self.bottomMargin,
            self.width,
            self.height,
            id="normal",
        )
        self.addPageTemplates(PageTemplate(id="paper", frames=[frame], onPage=_page))


def _page(canvas, doc) -> None:
    canvas.saveState()
    if doc.page > 1:
        canvas.setStrokeColor(colors.HexColor("#c8c8c8"))
        canvas.line(doc.leftMargin, 0.57 * inch, letter[0] - doc.rightMargin, 0.57 * inch)
        canvas.setFont(SANS, 8)
        canvas.setFillColor(colors.HexColor("#666666"))
        canvas.drawString(doc.leftMargin, 0.38 * inch, "How Markets Absorb News")
        canvas.drawRightString(
            letter[0] - doc.rightMargin, 0.38 * inch, f"Page {doc.page}"
        )
    canvas.restoreState()


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "PaperTitle",
            parent=base["Title"],
            fontName=SANS,
            fontSize=24,
            leading=28,
            textColor=colors.HexColor("#172b4d"),
            alignment=TA_LEFT,
            spaceAfter=14,
        ),
        "subtitle": ParagraphStyle(
            "PaperSubtitle",
            parent=base["Heading2"],
            fontName=SANS,
            fontSize=13,
            leading=17,
            textColor=colors.HexColor("#42526e"),
            spaceAfter=18,
        ),
        "h1": ParagraphStyle(
            "PaperH1",
            parent=base["Heading1"],
            fontName=SANS,
            fontSize=15,
            leading=18,
            textColor=colors.HexColor("#172b4d"),
            spaceBefore=12,
            spaceAfter=8,
            keepWithNext=True,
        ),
        "h2": ParagraphStyle(
            "PaperH2",
            parent=base["Heading2"],
            fontName=SANS,
            fontSize=11.5,
            leading=14,
            textColor=colors.HexColor("#334e68"),
            spaceBefore=9,
            spaceAfter=5,
            keepWithNext=True,
        ),
        "body": ParagraphStyle(
            "PaperBody",
            parent=base["BodyText"],
            fontName=SERIF,
            fontSize=9.5,
            leading=13.2,
            alignment=TA_JUSTIFY,
            textColor=colors.HexColor("#202124"),
            spaceAfter=7,
        ),
        "abstract": ParagraphStyle(
            "PaperAbstract",
            parent=base["BodyText"],
            fontName=SERIF,
            fontSize=9.4,
            leading=13.2,
            alignment=TA_JUSTIFY,
            leftIndent=0.25 * inch,
            rightIndent=0.25 * inch,
            borderColor=colors.HexColor("#d9e2ec"),
            borderWidth=0.7,
            borderPadding=10,
            backColor=colors.HexColor("#f7f9fc"),
            spaceAfter=12,
        ),
        "caption": ParagraphStyle(
            "Caption",
            parent=base["BodyText"],
            fontName=SERIF,
            fontSize=8.2,
            leading=10.5,
            alignment=TA_LEFT,
            textColor=colors.HexColor("#465463"),
            spaceBefore=4,
            spaceAfter=9,
        ),
        "meta": ParagraphStyle(
            "Meta",
            parent=base["BodyText"],
            fontName=SANS,
            fontSize=9,
            leading=12,
            textColor=colors.HexColor("#52606d"),
            spaceAfter=6,
        ),
    }


def _inline(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(r"`([^`]+)`", r"<font name='Courier'>\1</font>", escaped)
    escaped = re.sub(r"\*([^*]+)\*", r"<i>\1</i>", escaped)
    return escaped


def _table(frame: pd.DataFrame, widths: list[float] | None = None) -> Table:
    display = frame.copy()
    for column in display.select_dtypes(include="number"):
        display[column] = display[column].map(
            lambda value: "" if pd.isna(value) else f"{value:.3f}"
        )
    data = [list(display.columns)] + display.astype(str).values.tolist()
    table = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#334e68")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), SANS),
                ("FONTNAME", (0, 1), (-1, -1), SERIF),
                ("FONTSIZE", (0, 0), (-1, -1), 7.3),
                ("LEADING", (0, 0), (-1, -1), 9),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#b8c4ce")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f7fa")]),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    return table


def _figure(
    path: Path,
    caption: str,
    number: int,
    styles,
    max_height_inches: float = 3.35,
) -> list[object]:
    image = Image(str(path))
    max_width = 6.85 * inch
    max_height = max_height_inches * inch
    scale = min(max_width / image.imageWidth, max_height / image.imageHeight)
    image.drawWidth = image.imageWidth * scale
    image.drawHeight = image.imageHeight * scale
    return [
        Spacer(1, 5),
        image,
        Paragraph(f"<b>Figure {number}.</b> {caption}", styles["caption"]),
    ]


def _build_story() -> list[object]:
    styles = _styles()
    lines = PAPER.read_text(encoding="utf-8").splitlines()
    story: list[object] = [
        Spacer(1, 0.55 * inch),
        Paragraph("How Markets Absorb News", styles["title"]),
        Paragraph(
            "Quote Revision, Signed Order Flow, and Liquidity Withdrawal Across Macro and FOMC Announcements",
            styles["subtitle"],
        ),
        Spacer(1, 0.15 * inch),
        Paragraph("Empirical Finance / Market Microstructure Research Project", styles["meta"]),
        Paragraph(f"Research draft - {date.today().isoformat()}", styles["meta"]),
        Spacer(1, 0.30 * inch),
        Paragraph(
            "This draft reports completed message-level analysis of 77 macro announcement bundles, twelve clean FOMC meetings, and selected deeper-book windows. It preserves the proposal's mechanism definition and explicitly labels hypotheses that remain unidentified without vintage consensus data.",
            styles["abstract"],
        ),
        Spacer(1, 1.35 * inch),
        Paragraph(
            "Data: Databento GLBX.MDP3 message-level MBP-1; BLS, Census, and Federal Reserve event clocks; matched official-calendar controls.",
            styles["meta"],
        ),
        Paragraph(
            "Reproducibility: all raw files are immutable and accompanied by request metadata and checksums.",
            styles["meta"],
        ),
        PageBreak(),
    ]
    paragraph: list[str] = []
    figure_number = 0
    inserted = set()

    def flush() -> None:
        if not paragraph:
            return
        value = " ".join(item.strip() for item in paragraph).strip()
        paragraph.clear()
        if value:
            style = styles["abstract"] if current_heading == "Abstract" else styles["body"]
            story.append(Paragraph(_inline(value), style))

    current_heading = ""
    for raw in lines:
        line = raw.strip()
        if not line:
            flush()
            continue
        if line.startswith("# ") or line.startswith("## Quote Revision"):
            continue
        if line.startswith("## "):
            flush()
            current_heading = line[3:]
            story.append(Paragraph(_inline(current_heading), styles["h1"]))
            continue
        if line.startswith("### "):
            flush()
            current_heading = line[4:]
            story.append(Paragraph(_inline(current_heading), styles["h2"]))
            continue
        paragraph.append(line)
        if current_heading == "4.1 Macro announcement response and the scalar-news hypothesis" and "sequence of messages and trades" in line and "macro_response" not in inserted:
            flush()
            figure_number += 1
            story.extend(
                _figure(
                    PROJECT_ROOT / "figures" / "macro_multiyear" / "macro_response_by_type.png",
                    "Absolute 60-second midpoint responses across the January 2024-August 2025 sample. Simultaneous-release bundles are assigned to their first listed class in this display.",
                    figure_number,
                    styles,
                )
            )
            inserted.add("macro_response")
        if "figures/paper/fomc_mechanism_components.png" in line and "mechanism" not in inserted:
            flush()
            figure_number += 1
            story.extend(
                _figure(
                    PROJECT_ROOT / "figures" / "paper" / "fomc_mechanism_components.png",
                    "Median absolute 60-second components across eligible observations. The black diamond is the median absolute observed return; component medians need not add because they are calculated observation by observation before aggregation.",
                    figure_number,
                    styles,
                )
            )
            inserted.add("mechanism")
        if current_heading == "4.4 Speed of price discovery" and "completed identifying model" in line and "speed" not in inserted:
            flush()
            figure_number += 1
            story.extend(
                _figure(
                    PROJECT_ROOT / "figures" / "paper" / "fomc_price_discovery_speed.png",
                    "First crossing times relative to the five-minute midpoint response. Near-zero terminal moves are excluded; boxes show cross-meeting dispersion.",
                    figure_number,
                    styles,
                )
            )
            inserted.add("speed")
        if current_heading == "4.5 Subsecond location of price discovery" and "reports all thresholds" in line and "subsecond" not in inserted:
            flush()
            figure_number += 1
            story.extend(
                _figure(
                    PROJECT_ROOT / "figures" / "paper" / "fomc_subsecond_first_move.png",
                    "First crossing of absolute 0.5, 1, and 2 basis-point thresholds within 30 seconds. Log scaling preserves the distinction between millisecond and multi-second responses; missing crossings are excluded from boxes and reported in the text.",
                    figure_number,
                    styles,
                    max_height_inches=2.15,
                )
            )
            inserted.add("subsecond")
        if current_heading == "4.6 Pre-scheduled liquidity withdrawal" and "instrument heterogeneity" in line and "depth" not in inserted:
            flush()
            figure_number += 1
            story.extend(
                _figure(
                    PROJECT_ROOT / "figures" / "paper" / "fomc_depth_withdrawal.png",
                    "Displayed touch depth in the final minute relative to the preceding four-minute mean. Open circles are matched clean controls; filled circles are FOMC statement windows.",
                    figure_number,
                    styles,
                )
            )
            inserted.add("depth")
        if current_heading == "4.6 Pre-scheduled liquidity withdrawal" and "overbroad claim" in line and "macro_depth" not in inserted:
            flush()
            figure_number += 1
            story.extend(
                _figure(
                    PROJECT_ROOT / "figures" / "paper" / "macro_depth_withdrawal.png",
                    "Monthly announcement averages versus independently screened 8:30 a.m. controls. Lines connect each month-level pair; tests use the twenty month clusters.",
                    figure_number,
                    styles,
                )
            )
            inserted.add("macro_depth")
        if "deeper-book figure reports" in line and "deeper_book" not in inserted:
            flush()
            figure_number += 1
            story.extend(
                _figure(
                    PROJECT_ROOT / "figures" / "paper" / "deeper_book_depth.png",
                    "Final-minute cumulative depth at levels 1, 5, and 10 relative to the preceding four-minute mean in three pre-specified MBP-10 windows. These selected events are descriptive, not a population test.",
                    figure_number,
                    styles,
                )
            )
            inserted.add("deeper_book")
        if current_heading == "4.7 Source-verified corporate news" and "accompanying corporate-news figure" in line and "corporate_news" not in inserted:
            flush()
            figure_number += 1
            story.extend(
                _figure(
                    PROJECT_ROOT / "figures" / "unscheduled_news" / "source_verified_event_vs_placebo.png",
                    "Exchange-time midpoint responses for six source-verified corporate announcements and their matched clocks. Scales differ across panels; the comparison emphasizes within-event timing rather than equal effect sizes.",
                    figure_number,
                    styles,
                    max_height_inches=3.10,
                )
            )
            inserted.add("corporate_news")
        if current_heading == "4.8 Proposal-wide hypothesis assessment" and "cannot be estimated" in line and "hypothesis_status" not in inserted:
            flush()
            hypothesis_table = pd.read_csv(PROJECT_ROOT / "tables" / "hypothesis_status.csv")
            story.extend(
                [
                    Spacer(1, 6),
                    Paragraph("Table 1. Proposal hypothesis status", styles["caption"]),
                    _table(
                        hypothesis_table,
                        [0.48 * inch, 0.92 * inch, 2.25 * inch, 3.10 * inch],
                    ),
                ]
            )
            inserted.add("hypothesis_status")
    flush()

    story.extend([PageBreak(), Paragraph("Appendix A. Reproducible result tables", styles["h1"])])
    returns = pd.read_csv(PROJECT_ROOT / "tables" / "fomc_60s_returns.csv")
    inference = pd.read_csv(PROJECT_ROOT / "tables" / "fomc_depth_inference.csv").rename(
        columns={
            "instrument": "instrument",
            "meeting_pairs": "N",
            "mean_event_depth_ratio": "FOMC mean",
            "mean_placebo_depth_ratio": "control mean",
            "mean_difference": "mean diff.",
            "median_difference": "median diff.",
            "event_lower_pair_count": "lower N",
            "one_sided_sign_test_p": "sign p",
            "one_sided_wilcoxon_p": "Wilcoxon p",
        }
    )
    mechanism = pd.read_csv(PROJECT_ROOT / "tables" / "fomc_mechanism_components.csv").rename(
        columns={
            "subevent": "sub-event",
            "instrument": "instrument",
            "observations": "N",
            "median_abs_total_bp": "total |bp|",
            "median_abs_quote_bp": "quote |bp|",
            "median_abs_flow_bp": "flow |bp|",
            "median_abs_residual_bp": "residual |bp|",
        }
    )
    macro_depth = pd.read_csv(PROJECT_ROOT / "tables" / "macro_depth_inference.csv").rename(
        columns={
            "event_control_pairs": "N months",
            "mean_event_depth_ratio": "event mean",
            "mean_control_depth_ratio": "control mean",
            "mean_difference": "mean diff.",
            "event_lower_pair_count": "lower N",
            "one_sided_sign_test_p": "sign p",
            "one_sided_wilcoxon_p": "Wilcoxon p",
        }
    )[["instrument", "N months", "event mean", "control mean", "mean diff.", "lower N", "sign p", "Wilcoxon p"]]
    macro_h1 = pd.read_csv(PROJECT_ROOT / "tables" / "macro_h1_quote_fraction.csv")
    macro_h1 = macro_h1.loc[macro_h1["representation_class"].eq("scalar_numeric")].rename(
        columns={
            "observations": "N",
            "zero_first_quote_count": "zero N",
            "median_absolute_quote_fraction": "median |QR/total|",
            "one_sided_wilcoxon_below_70pct_p": "below 70% p",
        }
    )[["instrument", "N", "zero N", "median |QR/total|", "below 70% p"]]
    macro_h1["below 70% p"] = macro_h1["below 70% p"].map(lambda value: f"{value:.4f}")
    corporate = pd.read_csv(PROJECT_ROOT / "tables" / "corporate_news_summary.csv").rename(
        columns={
            "event": "event",
            "instrument": "ticker",
            "scheduled_indicator": "scheduled",
            "valid_mechanically": "Q1 valid",
            "event_return_60s_bp": "news 60s bp",
            "placebo_return_60s_bp": "control 60s bp",
            "event_depth_ratio": "news depth",
            "placebo_depth_ratio": "control depth",
        }
    )
    corporate["event"] = corporate["event"].str.replace("_announcement", "", regex=False).str.replace("_", " ")
    question_status = pd.read_csv(PROJECT_ROOT / "tables" / "proposal_question_status.csv")
    for column in ("sign p", "Wilcoxon p"):
        macro_depth[column] = macro_depth[column].map(lambda value: f"{value:.4f}")
    story.extend(
        [
            Paragraph("Table A1. Sixty-second midpoint responses by meeting and sub-event", styles["caption"]),
            _table(returns, [1.05 * inch, 1.05 * inch, 1.0 * inch, 1.0 * inch, 1.0 * inch]),
            Spacer(1, 12),
            Paragraph("Table A2. Matched pre-statement depth inference", styles["caption"]),
            _table(
                inference,
                [
                    0.92 * inch,
                    0.38 * inch,
                    0.70 * inch,
                    0.72 * inch,
                    0.66 * inch,
                    0.72 * inch,
                    0.58 * inch,
                    0.56 * inch,
                    0.72 * inch,
                ],
            ),
            Spacer(1, 12),
            Paragraph("Table A3. Median absolute mechanism components", styles["caption"]),
            _table(
                mechanism,
                [
                    1.03 * inch,
                    0.72 * inch,
                    0.38 * inch,
                    0.74 * inch,
                    0.74 * inch,
                    0.72 * inch,
                    0.82 * inch,
                ],
            ),
            PageBreak(),
            Paragraph("Table A4. Scalar macro first-quote fraction at five minutes", styles["caption"]),
            _table(macro_h1, [1.0 * inch, 0.55 * inch, 0.65 * inch, 1.25 * inch, 0.9 * inch]),
            Spacer(1, 12),
            Paragraph("Table A5. Month-clustered macro depth inference", styles["caption"]),
            _table(
                macro_depth,
                [0.98 * inch, 0.55 * inch, 0.72 * inch, 0.76 * inch, 0.70 * inch, 0.55 * inch, 0.55 * inch, 0.72 * inch],
            ),
            PageBreak(),
            Paragraph("Table A6. Source-verified corporate-news event/control summary", styles["caption"]),
            _table(
                corporate,
                [1.55 * inch, 0.48 * inch, 0.58 * inch, 0.55 * inch, 0.72 * inch, 0.78 * inch, 0.65 * inch, 0.72 * inch],
            ),
            Spacer(1, 16),
            Paragraph("Table A7. Proposal question completion status", styles["caption"]),
            _table(
                question_status,
                [0.52 * inch, 1.25 * inch, 4.85 * inch],
            ),
        ]
    )
    return story


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    document = PaperDocTemplate(str(OUTPUT))
    document.build(_build_story())
    print(f"Wrote {OUTPUT}")


if __name__ == "__main__":
    main()
