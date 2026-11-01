"""精细排版 PDF 导出。

版式与网页阅读页保持一致：主题色、纸色、正文/译文/注释字体与字号、内容宽度，
都会从界面设置传入；页码与页眉页脚单独处理。
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from html import escape
from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    CondPageBreak,
    Frame,
    HRFlowable,
    KeepTogether,
    PageTemplate,
    Paragraph,
    Spacer,
)

from ..config import (
    PDF_FANGSONG_FONTS,
    PDF_KAI_FONTS,
    PDF_SANS_FONTS,
    PDF_SERIF_FONTS,
)
from ..models import NoteView, ParagraphView, ReadingDocument, SectionView
from .common import ExportError, ExportResult, resolve_output_path

PAGE_W, PAGE_H = A4
MARGIN_TOP = 30 * mm
MARGIN_BOTTOM = 22 * mm
DEFAULT_MARGIN_X = 24 * mm

FONT_DIRS = [
    Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts",
    Path.home() / "AppData" / "Local" / "Microsoft" / "Windows" / "Fonts",
]

_BODY_SUPER = '<super size="6.6" rise="3.6">'
_NOTE_SUPER = '<super size="6.4" rise="3.2">'
_TITLE_SUPER = '<super size="8.4" rise="6.0">'


@dataclass(frozen=True)
class FontSet:
    serif: str
    kai: str
    sans: str
    fangsong: str


@dataclass(frozen=True)
class Palette:
    accent: str
    paper: str
    ink: str
    muted: str
    note: str
    rule: str
    rule_light: str


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _hex(value, fallback: str) -> str:
    text = str(value or "").strip()
    if len(text) == 7 and text.startswith("#"):
        try:
            int(text[1:], 16)
            return text.lower()
        except ValueError:
            pass
    return fallback


def _mix_hex(left: str, right: str, amount_right: float) -> str:
    amount_right = _clamp(amount_right, 0.0, 1.0)

    def rgb(value: str):
        text = value.lstrip("#")
        return (int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16))

    a = rgb(left)
    b = rgb(right)
    parts = [round(a[i] * (1 - amount_right) + b[i] * amount_right) for i in range(3)]
    return "#" + "".join(f"{part:02x}" for part in parts)


def _palette(settings: dict | None) -> Palette:
    settings = settings or {}
    accent = _hex(settings.get("accent"), "#a4422f")
    paper = _hex(settings.get("paper"), "#f7f3ea")
    ink = _hex(settings.get("ink"), "#26231e")
    return Palette(
        accent=accent,
        paper=paper,
        ink=ink,
        muted=_mix_hex(ink, paper, 0.46),
        note=_mix_hex(ink, paper, 0.18),
        rule=_mix_hex(ink, paper, 0.84),
        rule_light=_mix_hex(ink, paper, 0.92),
    )


def _content_margin(settings: dict | None):
    settings = settings or {}
    try:
        percent = _clamp(float(settings.get("contentPercent", 72)), 50, 96)
    except (TypeError, ValueError):
        percent = 72
    # PDF 需要保留印刷安全边距，不完全照搬屏幕的百分比。
    margin_mm = _clamp(24 + (72 - percent) * 0.5, 14, 36)
    return margin_mm * mm


def _font_path(filename: str) -> Path | None:
    for directory in FONT_DIRS:
        candidate = directory / filename
        if candidate.exists():
            return candidate
    return None


def _register_first(candidates, prefix: str) -> str | None:
    for index, (_name, filename) in enumerate(candidates):
        path = _font_path(filename)
        if path is None:
            continue
        font_name = f"{prefix}{index}"
        try:
            pdfmetrics.registerFont(TTFont(font_name, str(path), subfontIndex=0))
            return font_name
        except Exception:
            continue
    return None


_FONTS: FontSet | None = None


def get_fonts() -> FontSet:
    global _FONTS
    if _FONTS is not None:
        return _FONTS
    serif = _register_first(PDF_SERIF_FONTS, "PoemSerif")
    kai = _register_first(PDF_KAI_FONTS, "PoemKai")
    sans = _register_first(PDF_SANS_FONTS, "PoemSans")
    fangsong = _register_first(PDF_FANGSONG_FONTS, "PoemFang")
    if not serif:
        raise ExportError("未找到可用的中文字体，无法生成 PDF。")
    _FONTS = FontSet(serif=serif, kai=kai or serif, sans=sans or serif, fangsong=fangsong or serif)
    return _FONTS


def _clean_inline(value: str) -> str:
    return " ".join((value or "").split())


def _plain(value: str) -> str:
    return escape(_clean_inline(value), quote=False)


def _segments_markup(segments, supers: bool, size: str = _BODY_SUPER) -> str:
    parts: list[str] = []
    for segment in segments:
        parts.append(escape(segment.text, quote=False))
        if supers and segment.notes:
            for number in segment.notes:
                parts.append(f'{size}<font name="Times-Roman">{number}</font></super>')
    return "".join(parts)


class PdfExporter:
    def __init__(self, settings: dict | None = None, background: bool = True) -> None:
        self.settings = settings or {}
        self.background = bool(background)
        self.fonts = get_fonts()
        self.palette = _palette(self.settings)
        self.margin_x = _content_margin(self.settings)
        self.original_font = self._font_for(self.settings.get("originalFont"))
        self.translation_font = self._font_for(self.settings.get("translationFont"))
        self.notes_font = self._font_for(self.settings.get("notesFont"))
        self.styles = self._build_styles()

    def _font_for(self, font_id) -> str:
        mapping = {
            "song": self.fonts.serif,
            "kai": self.fonts.kai,
            "fangsong": self.fonts.fangsong,
            "hei": self.fonts.sans,
            "deng": self.fonts.sans,
        }
        return mapping.get(str(font_id or "song"), self.fonts.serif)

    def _num(self, key: str, default: float) -> float:
        try:
            return float(self.settings.get(key, default))
        except (TypeError, ValueError):
            return default

    def _build_styles(self):
        f = self.fonts
        p = self.palette
        body_size = _clamp(self._num("originalSize", 19.5) * 0.64, 10, 18)
        trans_size = _clamp(self._num("translationSize", 16.5) * 0.64, 8.5, 15)
        note_size = _clamp(self._num("notesSize", 14.5) * 0.64, 7.5, 12.5)
        body_leading = body_size * 1.8
        trans_leading = trans_size * 1.76
        note_leading = note_size * 1.62
        return {
            "title": ParagraphStyle(
                "Title", fontName=f.kai, fontSize=26, leading=35,
                textColor=HexColor(p.ink), spaceAfter=5,
            ),
            "meta": ParagraphStyle(
                "Meta", fontName=f.sans, fontSize=10.2, leading=16,
                textColor=HexColor(p.muted), spaceAfter=9,
            ),
            "body": ParagraphStyle(
                "Body", fontName=self.original_font, fontSize=body_size,
                leading=body_leading, firstLineIndent=body_size * 2,
                textColor=HexColor(p.ink), spaceAfter=7,
                allowWidows=0, allowOrphans=0, wordWrap="CJK",
            ),
            "translation": ParagraphStyle(
                "Translation", fontName=self.translation_font, fontSize=trans_size,
                leading=trans_leading, firstLineIndent=trans_size * 2,
                textColor=HexColor(p.muted), spaceAfter=5,
                allowWidows=0, allowOrphans=0, wordWrap="CJK",
            ),
            "note": ParagraphStyle(
                "Note", fontName=self.notes_font, fontSize=note_size,
                leading=note_leading, leftIndent=13, firstLineIndent=-13,
                textColor=HexColor(p.note), spaceAfter=3.4,
                allowWidows=0, allowOrphans=0, wordWrap="CJK",
            ),
            "ending": ParagraphStyle(
                "Ending", fontName=f.sans, fontSize=8.2, leading=12,
                alignment=1, textColor=HexColor(p.accent),
            ),
        }

    # ---------- 页面 ----------

    def _paint_page(self, canvas, doc, title: str, author: str, dynasty: str) -> None:
        p = self.palette
        canvas.saveState()
        if self.background:
            canvas.setFillColor(HexColor(p.paper))
            canvas.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)

        if doc.page > 1:
            canvas.setFont(self.fonts.sans, 8)
            canvas.setFillColor(HexColor(p.muted))
            canvas.drawString(self.margin_x, PAGE_H - 16 * mm, title)
            canvas.drawRightString(PAGE_W - self.margin_x, PAGE_H - 16 * mm, f"{dynasty} · {author}")
            canvas.setStrokeColor(HexColor(p.rule))
            canvas.setLineWidth(0.55)
            canvas.line(self.margin_x, PAGE_H - 19 * mm, PAGE_W - self.margin_x, PAGE_H - 19 * mm)

        canvas.setStrokeColor(HexColor(p.rule_light))
        canvas.setLineWidth(0.55)
        canvas.line(self.margin_x, 15 * mm, PAGE_W - self.margin_x, 15 * mm)
        canvas.setFont(self.fonts.sans, 8)
        canvas.setFillColor(HexColor(p.muted))
        canvas.drawCentredString(PAGE_W / 2, 10 * mm, f"· {doc.page} ·")
        canvas.restoreState()

    # ---------- 内容 ----------

    def _header_flowables(self, doc: ReadingDocument, mode: str) -> list:
        styles = self.styles
        p = self.palette
        poem = doc.poem
        full = mode == "full"
        if full and doc.title_notes:
            title_markup = _segments_markup(doc.title_segments, supers=True, size=_TITLE_SUPER)
        else:
            title_markup = _plain(poem["title"])

        flow: list = [
            Paragraph(title_markup, styles["title"]),
            Paragraph(f"{_plain(poem['dynasty'])} · {_plain(poem['author'])}", styles["meta"]),
            HRFlowable(width="100%", thickness=0.7, color=HexColor(p.rule), spaceBefore=1, spaceAfter=12),
        ]

        if full and doc.title_notes:
            flow.extend(self._notes_block(doc.title_notes))
            flow.append(Spacer(1, 10))
        return flow

    def _notes_block(self, notes: list[NoteView]) -> list:
        p = self.palette
        visible = [note for note in notes if note.text.strip() or note.label]
        if not visible:
            return []
        flow: list = [
            HRFlowable(
                width=16 * mm,
                thickness=0.9,
                color=HexColor(p.accent),
                spaceBefore=1,
                spaceAfter=5,
                hAlign="LEFT",
            )
        ]
        total = 0
        for note in visible:
            total += len(note.text) + len(note.label)
            flow.append(Paragraph(self._note_markup(note), self.styles["note"]))
        if total <= 1000 and len(visible) <= 8:
            return [KeepTogether(flow)]
        return flow

    def _note_markup(self, note: NoteView) -> str:
        number = ""
        if note.number > 0:
            number = f'{_NOTE_SUPER}<font name="Times-Roman">{note.number}</font></super> '
        label = ""
        if note.label:
            label = f'<font color="{self.palette.accent}">{escape(note.label, quote=False)}</font>：'
        return f"{number}{label}{escape(_clean_inline(note.text), quote=False)}"

    def _original_paragraph(self, paragraph: ParagraphView, full: bool) -> Paragraph:
        markup = _segments_markup(paragraph.segments, supers=full) if full else _plain(paragraph.plain)
        return Paragraph(markup, self.styles["body"])

    def _translation_paragraphs(self, paragraphs: list[str]) -> list:
        return [Paragraph(_plain(text), self.styles["translation"]) for text in paragraphs]

    def _paragraph_block(self, paragraph: ParagraphView, full: bool, translations: list[str]) -> list:
        original = self._original_paragraph(paragraph, full)
        translated = self._translation_paragraphs(translations) if translations else []
        size = len(paragraph.plain) + sum(len(t) for t in translations)

        if translated and size <= 420:
            flow: list = [KeepTogether([original, *translated])]
        else:
            flow = [original, *translated]

        if full and paragraph.notes:
            flow.extend(self._notes_block(paragraph.notes))
        flow.append(Spacer(1, 9))
        return flow

    def _section_flowables(self, section: SectionView, mode: str) -> list:
        full = mode == "full"
        include_translation = mode in {"translation", "full"}
        flow: list = []

        if section.kind in {"paired", "single"}:
            for paragraph in section.paragraphs:
                flow.extend(
                    self._paragraph_block(
                        paragraph,
                        full,
                        section.translations if include_translation else [],
                    )
                )
        else:
            for paragraph in section.paragraphs:
                flow.extend(self._paragraph_block(paragraph, full, []))
            if include_translation and section.translations:
                flow.append(Spacer(1, 7))
                flow.extend(self._translation_paragraphs(section.translations))
                flow.append(Spacer(1, 9))
        return flow

    def _appendix_flowables(self, doc: ReadingDocument) -> list:
        if not doc.appendix:
            return []
        flow: list = [CondPageBreak(42 * mm)]
        flow.extend(self._notes_block(doc.appendix))
        return flow

    def _closing(self) -> list:
        return [
            Spacer(1, 14),
            Paragraph("·  完  ·", self.styles["ending"]),
        ]

    def _story(self, doc: ReadingDocument, mode: str) -> list:
        story = self._header_flowables(doc, mode)
        if not doc.sections:
            story.append(Paragraph("暂无正文。", self.styles["body"]))
        else:
            for section in doc.sections:
                story.extend(self._section_flowables(section, mode))
        if mode == "full":
            story.extend(self._appendix_flowables(doc))
        story.extend(self._closing())
        return story

    # ---------- 构建 ----------

    def export(self, doc: ReadingDocument, mode: str, output_dir: Path) -> ExportResult:
        if mode not in {"original", "translation", "full"}:
            raise ExportError("未知的导出模式。")

        path = resolve_output_path(output_dir, doc.poem["title"], ".pdf")
        overwritten = path.exists()
        temp = path.with_name(path.name + ".tmp")
        poem = doc.poem

        def paint(canvas, document):
            self._paint_page(canvas, document, poem["title"], poem["author"], poem["dynasty"])

        try:
            base = BaseDocTemplate(
                str(temp),
                pagesize=A4,
                leftMargin=self.margin_x,
                rightMargin=self.margin_x,
                topMargin=MARGIN_TOP,
                bottomMargin=MARGIN_BOTTOM,
                title=poem["title"],
                author=poem["author"],
                subject=f"{poem['dynasty']} · {poem['author']}《{poem['title']}》笺注",
                creator="诗笺",
            )
            frame = Frame(
                self.margin_x,
                MARGIN_BOTTOM,
                PAGE_W - 2 * self.margin_x,
                PAGE_H - MARGIN_TOP - MARGIN_BOTTOM,
                id="main",
                leftPadding=0,
                rightPadding=0,
                topPadding=0,
                bottomPadding=0,
            )
            base.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=paint)])
            base.build(self._story(doc, mode))
            os.replace(temp, path)
        except ExportError:
            raise
        except Exception as exc:  # pragma: no cover
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass
            raise ExportError(f"PDF 生成失败：{exc}") from exc

        return ExportResult(path=path, overwritten=overwritten, size=path.stat().st_size)
