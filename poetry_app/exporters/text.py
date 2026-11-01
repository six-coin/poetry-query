"""纯文本导出。

提供两种样式：
- reading：与阅读页一致，原文带行内上标，译文随后，本段注释集中为一行；
- standard：标题/朝代/作者 + 【原文】【译文】【注释】分节。
"""

from __future__ import annotations

from pathlib import Path

from ..annotations import parse_annotations
from ..config import PARAGRAPH_INDENT, superscript
from ..models import NoteView, PoemRecord
from ..reading import build_reading
from .common import ExportResult, resolve_output_path


def _paragraphs(value: str) -> list[str]:
    return [line.strip() for line in (value or "").splitlines() if line.strip()]


def _segments_text(segments) -> str:
    parts: list[str] = []
    for segment in segments:
        parts.append(segment.text)
        for number in segment.notes:
            parts.append(superscript(number))
    return "".join(parts)


def _run_on_notes(notes: list[NoteView]) -> str:
    parts: list[str] = []
    for note in notes:
        if note.number > 0:
            parts.append(superscript(note.number))
        if note.label:
            parts.append(note.label + "：")
        parts.append(note.text.strip())
    return "".join(parts)


def _note_lines(poem: PoemRecord) -> list[str]:
    parsed = parse_annotations(poem.annotation, poem.content, poem.title)
    lines: list[str] = []
    if parsed.entries:
        for entry in parsed.entries:
            text = entry.text.strip()
            if not text:
                continue
            if entry.label:
                lines.append(f"{PARAGRAPH_INDENT}{entry.label}：{text}")
            else:
                lines.append(f"{PARAGRAPH_INDENT}{text}")
    elif poem.annotation.strip():
        # 结构完全无法解析时，保留原始注释，避免导出丢信息。
        lines.extend(f"{PARAGRAPH_INDENT}{line.strip()}" for line in _paragraphs(poem.annotation))
    return lines


def _standard_content(poem: PoemRecord) -> str:
    blocks: list[str] = [
        f"标题：{poem.title}",
        f"朝代：{poem.dynasty}",
        f"作者：{poem.author}",
        "",
        "【原文】",
    ]
    blocks.extend(f"{PARAGRAPH_INDENT}{line}" for line in _paragraphs(poem.content))
    blocks.extend(["", "【译文】"])
    blocks.extend(f"{PARAGRAPH_INDENT}{line}" for line in _paragraphs(poem.translation))
    notes = _note_lines(poem)
    if notes:
        blocks.extend(["", "【注释】"])
        blocks.extend(notes)
    return "\n".join(blocks).rstrip() + "\n"


def _reading_content(poem: PoemRecord) -> str:
    document = build_reading(poem)
    lines: list[str] = []

    if document.title_notes:
        lines.append(document.poem["title"])
        lines.append(PARAGRAPH_INDENT + _run_on_notes(document.title_notes))
        lines.append("")

    for section in document.sections:
        if section.kind in {"paired", "single"}:
            for paragraph in section.paragraphs:
                lines.append(PARAGRAPH_INDENT + _segments_text(paragraph.segments))
            for translation in section.translations:
                lines.append(PARAGRAPH_INDENT + translation)
            for paragraph in section.paragraphs:
                notes = _run_on_notes(paragraph.notes)
                if notes:
                    lines.append(PARAGRAPH_INDENT + notes)
        else:
            for paragraph in section.paragraphs:
                lines.append(PARAGRAPH_INDENT + _segments_text(paragraph.segments))
            for translation in section.translations:
                lines.append(PARAGRAPH_INDENT + translation)
            for paragraph in section.paragraphs:
                notes = _run_on_notes(paragraph.notes)
                if notes:
                    lines.append(PARAGRAPH_INDENT + notes)
        if lines and lines[-1] != "":
            lines.append("")

    if document.appendix:
        for note in document.appendix:
            if note.label:
                lines.append(PARAGRAPH_INDENT + note.label + "：" + note.text.strip())
            else:
                lines.append(PARAGRAPH_INDENT + note.text.strip())

    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines).rstrip() + "\n"


def export_text(poem: PoemRecord, output_dir: Path, style: str = "reading") -> ExportResult:
    path = resolve_output_path(output_dir, poem.title, ".txt")
    overwritten = path.exists()
    content = _standard_content(poem) if style == "standard" else _reading_content(poem)
    path.write_text(content, encoding="utf-8-sig")
    return ExportResult(path=path, overwritten=overwritten, size=path.stat().st_size)
