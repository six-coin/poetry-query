"""把一条诗文记录组装成界面/PDF 共用的阅读文档。"""

from __future__ import annotations

import re

from .alignment import align_prose, text_similarity, verse_indices
from .annotations import parse_annotations, paragraphs_with_notes, title_with_notes
from .models import (
    AnnotationStatus,
    NoteView,
    PoemRecord,
    ReadingDocument,
    SectionView,
)


def _split_text(value: str) -> list[str]:
    return [line.strip() for line in (value or "").splitlines() if line.strip()]


def _valid_alignment(groups, prose_count: int, translation_count: int) -> bool:
    covered_content: list[int] = []
    covered_translation: list[int] = []
    translated_content = 0
    for group in groups:
        covered_content.extend(group.content_indices)
        covered_translation.extend(group.translation_indices)
        if group.translation_indices:
            translated_content += len(group.content_indices)
    if covered_content != list(range(prose_count)):
        return False
    if covered_translation != list(range(translation_count)):
        return False
    if prose_count and translated_content / prose_count < 0.55:
        return False
    for group in groups:
        if group.translation_indices and group.score < 0.015:
            return False
    return True


def _sections_from_alignment(paragraphs, translations, verse: list[int], groups):
    verse_set = set(verse)
    prose_original = [index for index in range(len(paragraphs)) if index not in verse_set]
    sections: list[SectionView] = []
    prose_cursor = 0
    index = 0
    group_by_start = {group.content_indices[0]: group for group in groups}

    while index < len(paragraphs):
        if index in verse_set:
            sections.append(SectionView(paragraphs=[paragraphs[index]], translations=[], kind="whole"))
            index += 1
            continue

        group = group_by_start.get(prose_cursor)
        if group is None:
            return None
        original_indices = [prose_original[item] for item in group.content_indices]
        grouped_paragraphs = [paragraphs[item] for item in original_indices]
        grouped_translations = [translations[item] for item in group.translation_indices]
        if len(grouped_paragraphs) == 1 and len(grouped_translations) == 1:
            kind = "paired"
        elif not grouped_translations:
            kind = "whole"
        else:
            kind = "grouped"
        sections.append(
            SectionView(paragraphs=grouped_paragraphs, translations=grouped_translations, kind=kind)
        )
        prose_cursor += len(group.content_indices)
        index = original_indices[-1] + 1
    return sections


_SENTENCE_END = re.compile(r"(?<=[。！？；])")


def _split_sentences(text: str) -> list[str]:
    return [part.strip() for part in _SENTENCE_END.split(text) if part.strip()]


def _split_translation_between(previous: str, current: str, translation: str) -> tuple[str, str] | None:
    """当一段译文同时覆盖韵文前、后的两段原文时，按句子相似度拆开。

    典型例子是《屈原列传》的“屈原到了江滨……渔父……”：数据库把渔父故事
    与“于是怀石……自投汨罗”放在同一个译文自然段里，而原文中间夹着《怀沙》。
    这里只在相似度有明确落差时才拆，拆不出来就保持原样。
    """
    sentences = _split_sentences(translation)
    if len(sentences) < 3:
        return None

    scores = [(text_similarity(sentence, previous), text_similarity(sentence, current)) for sentence in sentences]
    for index in range(1, len(sentences)):
        left_previous = sum(pair[0] for pair in scores[:index])
        left_current = sum(pair[1] for pair in scores[:index])
        right_previous = sum(pair[0] for pair in scores[index:])
        right_current = sum(pair[1] for pair in scores[index:])
        if left_previous <= left_current + 0.05:
            continue
        if right_current <= right_previous + 0.02:
            continue

        moved = "".join(sentences[:index])
        kept = "".join(sentences[index:])
        # 分句后可能把右引号留在后一段开头，归回前一段更自然。
        while kept and kept[0] in "”’\\\"'":
            moved += kept[0]
            kept = kept[1:]
        if len(moved) < 10 or len(kept) < 4:
            return None
        return moved, kept
    return None


def _split_translations_across_verse(sections: list[SectionView]) -> list[SectionView]:
    sections = list(sections)
    last_prose: int | None = None
    crossed_verse = False

    for index, section in enumerate(sections):
        is_verse_gap = (
            not section.translations
            and any("兮" in paragraph.plain for paragraph in section.paragraphs)
        )
        if is_verse_gap:
            crossed_verse = True
            continue
        if not section.translations:
            continue

        if crossed_verse and last_prose is not None:
            previous = sections[last_prose]
            if (
                len(previous.paragraphs) == 1
                and len(previous.translations) == 1
                and len(section.paragraphs) == 1
                and len(section.translations) == 1
            ):
                split = _split_translation_between(
                    previous.paragraphs[0].plain,
                    section.paragraphs[0].plain,
                    section.translations[0],
                )
                if split:
                    moved, kept = split
                    sections[last_prose] = SectionView(
                        paragraphs=previous.paragraphs,
                        translations=[previous.translations[0] + moved],
                        kind=previous.kind,
                    )
                    sections[index] = SectionView(
                        paragraphs=section.paragraphs,
                        translations=[kept],
                        kind=section.kind,
                    )

        crossed_verse = False
        last_prose = index
    return sections


def _build_sections(paragraphs, translations: list[str]) -> list[SectionView]:
    n = len(paragraphs)
    m = len(translations)
    if n == 0:
        return [SectionView(paragraphs=[], translations=translations, kind="whole")] if m else []
    if m == 0:
        return [SectionView(paragraphs=paragraphs, translations=[], kind="whole")]
    if n == 1:
        return [SectionView(paragraphs=paragraphs, translations=translations, kind="single")]
    if n == m:
        return [
            SectionView(paragraphs=[paragraphs[index]], translations=[translations[index]], kind="paired")
            for index in range(n)
        ]

    # 多段散文中间夹楚辞体韵文时，韵文常常没有逐句译文。
    # 先排除“兮”字段落，再对其余散文做保序对齐；失败则退回整篇译文。
    verse = verse_indices([paragraph.plain for paragraph in paragraphs])
    if verse and len(verse) < n:
        verse_set = set(verse)
        prose = [paragraph.plain for index, paragraph in enumerate(paragraphs) if index not in verse_set]
        groups = align_prose(prose, translations)
        if groups and _valid_alignment(groups, len(prose), m):
            sections = _sections_from_alignment(paragraphs, translations, verse, groups)
            if sections:
                return _split_translations_across_verse(sections)

    # 段数不一致且无可靠对齐时：正文与译文各自成块，保持顺序。
    return [SectionView(paragraphs=paragraphs, translations=translations, kind="whole")]


def build_reading(poem: PoemRecord) -> ReadingDocument:
    parsed = parse_annotations(poem.annotation, poem.content, poem.title)
    translation_paragraphs = _split_text(poem.translation)

    paragraphs = paragraphs_with_notes(poem.content, parsed.body)
    title_segments, title_notes, title_references = title_with_notes(poem.title, parsed.title)

    note_count = len(parsed.body) + len(parsed.title)
    if parsed.raw_line_count == 0:
        status = AnnotationStatus(ok=True, state="empty", message="本篇没有注释。", note_count=0)
    else:
        extra = f"，另有 {len(parsed.appendix)} 条附注" if parsed.appendix else ""
        status = AnnotationStatus(
            ok=True,
            state="ok",
            message=f"共 {note_count} 条笺注{extra}。",
            note_count=note_count,
        )

    appendix = [
        NoteView(number=0, label=note.label, text=note.text)
        for note in parsed.appendix
        if note.text.strip()
    ]

    return ReadingDocument(
        poem={
            "id": poem.id,
            "title": poem.title,
            "author": poem.author,
            "dynasty": poem.dynasty,
        },
        title_segments=title_segments,
        title_notes=title_notes,
        title_references=title_references,
        sections=_build_sections(paragraphs, translation_paragraphs),
        annotation=status,
        appendix=appendix,
        translation_paragraphs=translation_paragraphs,
    )
