"""跨层共享的数据模型。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class PoemRecord:
    id: int
    title: str
    author: str
    dynasty: str
    content: str
    translation: str
    annotation: str


@dataclass(frozen=True)
class PoemSummary:
    id: int
    title: str
    author: str
    dynasty: str
    excerpt: str


@dataclass(frozen=True)
class SearchPage:
    items: list[PoemSummary]
    total: int


@dataclass(frozen=True)
class SegmentView:
    text: str
    notes: list[int] = field(default_factory=list)


@dataclass(frozen=True)
class NoteView:
    number: int
    label: str
    text: str


@dataclass(frozen=True)
class ReferenceView:
    number: int
    start: int
    end: int


@dataclass(frozen=True)
class ParagraphView:
    plain: str
    segments: list[SegmentView]
    notes: list[NoteView]
    references: list[ReferenceView] = field(default_factory=list)


@dataclass(frozen=True)
class SectionView:
    paragraphs: list[ParagraphView]
    translations: list[str]
    kind: str  # paired | single | whole


@dataclass(frozen=True)
class AnnotationStatus:
    ok: bool
    state: str  # ok | empty | failed
    message: str
    issues: list[dict[str, str]] = field(default_factory=list)
    note_count: int = 0


@dataclass(frozen=True)
class ReadingDocument:
    poem: dict[str, Any]
    title_segments: list[SegmentView]
    title_notes: list[NoteView]
    title_references: list[ReferenceView]
    sections: list[SectionView]
    annotation: AnnotationStatus
    appendix: list[NoteView] = field(default_factory=list)
    translation_paragraphs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
