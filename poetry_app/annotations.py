"""注释解析与行内上标定位。

数据源里的“注释”并非严格结构化文本：有的一个自然段包含多条注释，
有的注释没有冒号，有的带序号，还有少量繁体/异体字。这里采用保守策略：

1. 只把能在正文或标题中定位到词条的注释视为“可内嵌注释”；
2. 其余整体性说明放入附录（附注），不伪造上标；
3. 若存在明确词条却无法定位，则标记解析失败，由界面拒绝完整注释视图。
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field

from .models import NoteView, ParagraphView, ReferenceView, SegmentView

# 全部标点（含全角/半角、书名号、引号、括号）
PUNCT_ALL = "，。！？；：、“”‘’《》〈〉（）()【】[]{}…—·.,!?;:\"' \t\u3000"

# 注释开头常见的“说明性”词语，避免被误当作词条。
_GENERAL_PREFIXES = (
    "选自", "本", "此", "以上", "以下", "这里", "其中", "所谓", "意思",
    "意谓", "即", "全句", "这句", "首句", "末句", "按", "注",
)

# 词条以这些字结尾时，通常是“子曰：”“诗云：”之类的引用，不是词条。
_SPEECH_SUFFIXES = ("曰", "说", "云", "问", "答", "道", "言", "称", "谓", "注", "载", "按", "案")

# 常见异体/通假/OCR 差异，仅用于匹配，不影响展示。
_VARIANTS = str.maketrans({
    "餔": "哺", "眜": "昧", "於": "于", "裏": "里", "儘": "尽",
    "歎": "叹", "嘆": "叹", "遊": "游", "臺": "台", "祇": "只",
    "祗": "只", "誖": "悖", "螿": "螀",
})

_HEADER_LINES = {"注释", "注解", "【注释】", "【注解】", "注释：", "注："}

_NUMBER_PATTERNS = (
    re.compile(r"^[（(\[【]\s*\d{1,3}\s*[）)\]】]\s*"),
    re.compile(r"^\d{1,3}\s*[.．、)]\s*"),
    re.compile(r"^[①-⑳⑴-⒇]\s*"),
    re.compile(r"^[一二三四五六七八九十百]{1,3}\s*[、.．]\s*"),
)

_SUFFIX_RE = re.compile(r"(二句|一句|两句|三句|四句|五句|六句|句下|以下|等|句)$")


@dataclass
class NoteEntry:
    label: str
    text: str
    order: int
    kind: str  # content | title | appendix | unmatched
    start: int | None = None
    end: int | None = None


@dataclass
class ParsedAnnotations:
    entries: list[NoteEntry] = field(default_factory=list)
    body: list[NoteEntry] = field(default_factory=list)
    title: list[NoteEntry] = field(default_factory=list)
    appendix: list[NoteEntry] = field(default_factory=list)
    unmatched: list[NoteEntry] = field(default_factory=list)
    error: str | None = None
    raw_line_count: int = 0

    @property
    def ok(self) -> bool:
        # 即使存在无法定位的词条，也不再拒绝阅读；
        # 这些词条会转入附注，由阅读页在文末展示。
        return True

    @property
    def has_annotation(self) -> bool:
        return self.raw_line_count > 0


@dataclass(frozen=True)
class ParagraphSpan:
    text: str
    start: int
    end: int


def _strip_number(value: str) -> str:
    value = value.strip()
    for pattern in _NUMBER_PATTERNS:
        new = pattern.sub("", value, count=1)
        if new != value:
            value = new.strip()
            break
    return value.strip()


def _remove_parens(value: str) -> str:
    previous = None
    while previous != value:
        previous = value
        value = re.sub(r"[（(][^（）()]{0,30}[）)]", "", value)
    return value


def _strip_wrapping(value: str) -> str:
    pairs = (("“", "”"), ("‘", "’"), ("《", "》"), ("【", "】"), ('"', '"'), ("'", "'"))
    value = value.strip().strip("，。；：、 ")
    changed = True
    while changed and len(value) > 1:
        changed = False
        for left, right in pairs:
            if value.startswith(left) and value.endswith(right):
                value = value[1:-1].strip()
                changed = True
    return value


def _strip_suffix(value: str) -> str:
    return _SUFFIX_RE.sub("", value).strip()


def _normalize_exact(value: str) -> str:
    value = _remove_parens(value.strip())
    for _ in range(2):
        value = _strip_suffix(_strip_wrapping(value))
    return value


def _strip_quote_wrapping(value: str) -> str:
    pairs = (("“", "”"), ("‘", "’"), ('"', '"'), ("'", "'"))
    value = value.strip().strip("，。；：、 ")
    changed = True
    while changed and len(value) > 1:
        changed = False
        for left, right in pairs:
            if value.startswith(left) and value.endswith(right):
                value = value[1:-1].strip()
                changed = True
    return value


def display_label(raw: str) -> str:
    """注释列表里展示的词条名，保留拼音括注与书名号。"""
    value = raw.strip().strip("，。；：、 ")
    for _ in range(2):
        value = _strip_suffix(_strip_quote_wrapping(value))
    return value or raw.strip()


def _normalize_for_match(raw: str) -> str:
    value = _remove_parens(raw.strip())
    for _ in range(2):
        value = _strip_suffix(_strip_wrapping(value))
    value = re.sub(r"[\s" + re.escape(PUNCT_ALL) + "]", "", value)
    # 去掉紧贴汉字的拼音，如“翕xī”“省（xing）”
    value = re.sub(r"[A-Za-z\u00c0-\u024f]+", "", value)
    return value.translate(_VARIANTS)


def _punctless(value: str) -> str:
    value = re.sub(r"[\s" + re.escape(PUNCT_ALL) + "]", "", value)
    value = re.sub(r"[A-Za-z\u00c0-\u024f]+", "", value)
    return value.translate(_VARIANTS)


def _find_in_normalized(text: str, needle: str) -> tuple[int, int] | None:
    if not needle:
        return None
    haystack = _punctless(text)
    index = haystack.find(needle)
    if index < 0:
        return None
    count = 0
    start = None
    for offset, char in enumerate(text):
        if re.match(r"[\s" + re.escape(PUNCT_ALL) + "]", char):
            continue
        # 与 _punctless 保持一致：拉丁字母也被忽略，否则索引会错位。
        if re.match(r"[A-Za-z\u00c0-\u024f]", char):
            continue
        if count == index:
            start = offset
        if count == index + len(needle) - 1:
            return (start, offset + 1)  # type: ignore[return-value]
        count += 1
    return None


def find_term(text: str, raw: str, start: int = 0) -> tuple[int, int] | None:
    """在正文/标题中定位词条，返回 start 之后首个命中的字符区间。"""
    if not text or not raw.strip():
        return None

    start = max(0, min(int(start), len(text)))
    raw = raw.strip()

    for candidate in (raw, _remove_parens(raw)):
        # 先尝试原样词条，让《离骚》这类书名号完整保留在正文中。
        direct = candidate.strip().strip("，。；：、 ")
        if direct:
            index = text.find(direct, start)
            if index >= 0:
                return (index, index + len(direct))
        normalized = _normalize_exact(candidate)
        if normalized:
            index = text.find(normalized, start)
            if index >= 0:
                return (index, index + len(normalized))

    needle = _normalize_for_match(raw)
    if not needle:
        return None
    hit = _find_in_normalized(text[start:], needle)
    if hit:
        return (start + hit[0], start + hit[1])

    # “瑾、瑜”“松源、漆公店”这类并列词条，命中第一项即可。
    parts = [part for part in re.split(r"[、，,]", _remove_parens(raw)) if part.strip()]
    if len(parts) > 1:
        for part in parts:
            part_needle = _normalize_for_match(part)
            if part_needle and part_needle != needle:
                hit = _find_in_normalized(text[start:], part_needle)
                if hit:
                    return (start + hit[0], start + hit[1])

    # “A句和B句”式的合并词条，命中前一项即可。
    if "和" in raw and len(needle) > 6:
        for part in raw.split("和"):
            part_needle = _normalize_for_match(part)
            if part_needle:
                hit = _find_in_normalized(text[start:], part_needle)
                if hit:
                    return (start + hit[0], start + hit[1])
    return None


def _is_term_like(raw: str) -> bool:
    raw = raw.strip()
    if not raw or len(raw) > 26:
        return False
    core = raw.strip("“”\"'‘’《》〈〉【】[]（）()")
    if not core:
        return False
    # 词条内部可以带逗号（如“纵一苇之所如，凌万顷之茫然”），
    # 但不能带句号、问号、分号、冒号等会切断注释结构的标点。
    if any(char in core for char in "。！？；："):
        return False
    if core in {"注", "按", "案", "说明", "提示"}:
        return False
    if core.endswith(_SPEECH_SUFFIXES):
        return False
    if core.startswith(_GENERAL_PREFIXES):
        return False
    return True


def _is_continuation(text: str) -> bool:
    if len(text) >= 200:
        return False
    if any(text.startswith(prefix) for prefix in _GENERAL_PREFIXES):
        return False
    return True


def _join_text(left: str, right: str) -> str:
    left = left.rstrip()
    right = right.lstrip()
    if not left:
        return right
    if not right:
        return left
    if left[-1] in "，。！？；：、" or right[0] in "，。！？；：、":
        return left + right
    return left + right


def _extract_line(
    line: str,
    content: str,
    title: str,
) -> tuple[list[tuple[str, str, str]], str]:
    """从一行里拆出一个或多个词条。

    只做结构切分与初步分类，真正的正文位置稍后统一分配。
    返回 (词条列表, 行首残余文字)，词条为 (展示名, 释义, kind)。
    """
    line = _strip_number(line)
    if not line:
        return [], ""

    candidates: list[tuple[int, int, str, str]] = []
    for colon_index, char in enumerate(line):
        if char not in "：:":
            continue
        boundary = 0
        for offset in range(colon_index - 1, -1, -1):
            if line[offset] in "。！？；":
                boundary = offset + 1
                break
        raw_term = line[boundary:colon_index].strip()
        if not _is_term_like(raw_term):
            continue

        hit = find_term(content, raw_term)
        kind = "content" if hit else ""
        if not hit:
            hit = find_term(title, raw_term)
            kind = "title" if hit else "unmatched"
        candidates.append((boundary, colon_index, raw_term, kind))

    if not candidates:
        return [], line

    accepted = []
    for index, candidate in enumerate(candidates):
        boundary, _colon, raw_term, kind = candidate
        if index == 0:
            if kind != "unmatched" or (boundary == 0 and len(display_label(raw_term)) <= 12):
                accepted.append(candidate)
        elif kind != "unmatched":
            accepted.append(candidate)

    if not accepted:
        return [], line

    prefix = line[: accepted[0][0]].strip()
    entries: list[tuple[str, str, str]] = []
    for index, (boundary, colon_index, raw_term, kind) in enumerate(accepted):
        definition_start = colon_index + 1
        definition_end = accepted[index + 1][0] if index + 1 < len(accepted) else len(line)
        definition = line[definition_start:definition_end].strip()
        entries.append((display_label(raw_term), definition, kind))
    return entries, prefix


def _assign_body_notes(notes: list[NoteEntry], content: str) -> int:
    """按注释原顺序为正文词条分配位置。

    优先在上一条之后寻找；若某一词条突然跳到很后面，而紧随其后的几条
    注释其实落在前面，则把该词条标记为“游离命中”，不推进游标，
    避免一个错位词条把后续注释全部带偏。
    """
    cursor = 0
    detached = 0
    for index, note in enumerate(notes):
        hit = find_term(content, note.label, cursor)
        if hit:
            is_detached = False
            if hit[0] - cursor > 80:
                for following in notes[index + 1 : index + 4]:
                    next_hit = find_term(content, following.label, cursor)
                    if next_hit and next_hit[0] < hit[0]:
                        is_detached = True
                        break
            note.start, note.end = hit
            if is_detached:
                detached += 1
            else:
                cursor = max(cursor, hit[0])
            continue

        # 后面的注释可能引用正文中更早的词语；回退到首个命中，但不移动游标。
        earlier = find_term(content, note.label, 0)
        if earlier:
            note.start, note.end = earlier
            detached += 1
        else:
            note.kind = "unmatched"
    return detached


def _assign_title_notes(notes: list[NoteEntry], title: str) -> None:
    for note in notes:
        hit = find_term(title, note.label, 0)
        if hit:
            note.start, note.end = hit
        else:
            note.kind = "unmatched"


def parse_annotations(annotation: str, content: str, title: str) -> ParsedAnnotations:
    raw_lines = [line.strip() for line in (annotation or "").splitlines() if line.strip()]
    result = ParsedAnnotations(raw_line_count=len(raw_lines))
    if not raw_lines:
        return result

    previous: NoteEntry | None = None
    order = 0

    for raw_line in raw_lines:
        if raw_line in _HEADER_LINES:
            continue

        extracted, prefix = _extract_line(raw_line, content, title)
        if not extracted:
            text = prefix.strip()
            if not text:
                continue
            if previous is not None and _is_continuation(text):
                previous.text = _join_text(previous.text, text)
            else:
                entry = NoteEntry(label="", text=text, order=order, kind="appendix")
                order += 1
                result.entries.append(entry)
                result.appendix.append(entry)
                previous = entry
            continue

        if prefix:
            entry = NoteEntry(label="", text=prefix, order=order, kind="appendix")
            order += 1
            result.entries.append(entry)
            result.appendix.append(entry)

        for label, definition, kind in extracted:
            entry = NoteEntry(label=label, text=definition, order=order, kind=kind)
            order += 1
            result.entries.append(entry)
            previous = entry

    body_notes = [entry for entry in result.entries if entry.kind == "content"]
    title_notes = [entry for entry in result.entries if entry.kind == "title"]

    _assign_body_notes(body_notes, content)
    _assign_title_notes(title_notes, title)

    # 无法在正文/标题中定位的词条不再让整篇失败，统一转入附注。
    for entry in result.entries:
        if entry.kind == "unmatched":
            entry.kind = "appendix"

    result.body = _dedupe_notes([entry for entry in body_notes if entry.kind == "content"])
    result.title = _dedupe_notes([entry for entry in title_notes if entry.kind == "title"])
    result.appendix = [entry for entry in result.entries if entry.kind == "appendix"]
    result.unmatched = []
    result.error = None
    return result


def _dedupe_notes(notes: list[NoteEntry]) -> list[NoteEntry]:
    seen: set[tuple[int, int]] = set()
    output: list[NoteEntry] = []
    for note in notes:
        if note.start is None or note.end is None:
            continue
        key = (note.start, note.end)
        if key in seen:
            continue
        seen.add(key)
        output.append(note)
    return output


def split_paragraph_spans(content: str) -> list[ParagraphSpan]:
    spans: list[ParagraphSpan] = []
    for match in re.finditer(r"[^\n]+", content or ""):
        raw = match.group()
        text = raw.strip()
        if not text:
            continue
        leading = len(raw) - len(raw.lstrip())
        start = match.start() + leading
        spans.append(ParagraphSpan(text=text, start=start, end=start + len(text)))
    return spans


def _build_segments(text: str, insertions: list[tuple[int, int]]) -> list[SegmentView]:
    """insertions: (字符位置, 上标编号)，位置指在该字符之后插入。"""
    buckets: dict[int, list[int]] = defaultdict(list)
    for position, number in insertions:
        buckets[max(0, min(position, len(text)))].append(number)

    segments: list[SegmentView] = []
    cursor = 0
    for position in sorted(buckets):
        if position < cursor:
            position = cursor
        segments.append(SegmentView(text=text[cursor:position], notes=buckets[position]))
        cursor = position
    segments.append(SegmentView(text=text[cursor:], notes=[]))
    return segments


def paragraphs_with_notes(content: str, notes: list[NoteEntry]) -> list[ParagraphView]:
    spans = split_paragraph_spans(content)
    if not spans:
        return []

    buckets: list[list[tuple[NoteEntry, int, int]]] = [[] for _ in spans]
    for note in notes:
        if note.start is None or note.end is None:
            continue
        index = None
        for i, span in enumerate(spans):
            if span.start <= note.start < span.end or note.start == span.end:
                index = i
                break
        if index is None:
            index = len(spans) - 1 if note.start > spans[-1].end else 0

        span = spans[index]
        relative_start = min(max(note.start, span.start), span.end) - span.start
        relative_end = min(max(note.end, span.start), span.end) - span.start
        buckets[index].append((note, relative_start, relative_end))

    paragraphs: list[ParagraphView] = []
    for span, bucket in zip(spans, buckets):
        bucket.sort(key=lambda item: (item[2], item[1], item[0].order))
        note_views: list[NoteView] = []
        references: list[ReferenceView] = []
        insertions: list[tuple[int, int]] = []
        for number, (note, relative_start, relative_end) in enumerate(bucket, start=1):
            note_views.append(NoteView(number=number, label=note.label, text=note.text))
            references.append(ReferenceView(number=number, start=relative_start, end=relative_end))
            insertions.append((relative_end, number))
        paragraphs.append(
            ParagraphView(
                plain=span.text,
                segments=_build_segments(span.text, insertions),
                notes=note_views,
                references=references,
            )
        )
    return paragraphs


def title_with_notes(
    title: str, notes: list[NoteEntry]
) -> tuple[list[SegmentView], list[NoteView], list[ReferenceView]]:
    if not notes:
        return [SegmentView(text=title, notes=[])], [], []

    ordered = sorted(notes, key=lambda note: (note.end or 0, note.start or 0, note.order))
    note_views: list[NoteView] = []
    references: list[ReferenceView] = []
    insertions: list[tuple[int, int]] = []
    for number, note in enumerate(ordered, start=1):
        note_views.append(NoteView(number=number, label=note.label, text=note.text))
        references.append(
            ReferenceView(number=number, start=note.start or 0, end=note.end or 0)
        )
        insertions.append((note.end or 0, number))
    return _build_segments(title, insertions), note_views, references
