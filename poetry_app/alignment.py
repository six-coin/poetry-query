"""段落级译文对齐。

只在一个特定场景启用：多段正文中含“兮”字楚辞体段落，且译文段数不同。
这类文章常见结构是“散文叙事 + 中间插入韵文”，韵文往往没有逐句翻译。
先把韵文段落排除，再对散文与译文做保序对齐，可以避免把译文整体堆到文末。

对齐失败时调用方会退回“整篇译文”布局，不强行制造错误对应。
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

_CJK = re.compile(r"[^\u4e00-\u9fff]")


@dataclass(frozen=True)
class AlignmentGroup:
    content_indices: list[int]
    translation_indices: list[int]
    score: float
    kind: str  # pair | content | c2t1 | c1t2


def _grams(text: str) -> Counter:
    text = _CJK.sub("", text)
    grams: Counter = Counter(text[index:index + 2] for index in range(len(text) - 1))
    for char in text:
        grams[char] += 0.5
    return grams


def _similarity_matrix(content: list[str], translation: list[str]):
    cg = [_grams(item) for item in content]
    tg = [_grams(item) for item in translation]
    total = len(cg) + len(tg)
    df: Counter = Counter()
    for gram in cg + tg:
        for key in gram:
            df[key] += 1
    idf = {key: math.log((total + 1) / (value + 1)) + 1 for key, value in df.items()}
    cv = [{key: value * idf.get(key, 1) for key, value in gram.items()} for gram in cg]
    tv = [{key: value * idf.get(key, 1) for key, value in gram.items()} for gram in tg]

    def norm(vector):
        return math.sqrt(sum(value * value for value in vector.values()))

    cn = [norm(vector) for vector in cv]
    tn = [norm(vector) for vector in tv]

    def sim(i: int, j: int) -> float:
        left, right = cv[i], tv[j]
        common = sum(value * right.get(key, 0) for key, value in left.items())
        if not common or not cn[i] or not tn[j]:
            return 0.0
        cosine = common / (cn[i] * tn[j])
        containment = common / min(cn[i] ** 2, tn[j] ** 2)
        return max(0.4 * cosine + 0.6 * containment, containment * 0.92)

    return sim, [len(item) for item in content], [len(item) for item in translation]


def align_prose(content: list[str], translation: list[str]) -> list[AlignmentGroup] | None:
    """保序对齐散文段与译文段。

    content / translation 都是纯文本段落。允许 1:1、2:1、1:2 以及单侧留空，
    但禁止大段任意合并，以保持可读性。
    """
    n, m = len(content), len(translation)
    if n == 0 or m == 0:
        return None
    if n > 80 or m > 80:
        return None

    sim, cl, tl = _similarity_matrix(content, translation)
    total_c = sum(cl)
    total_t = sum(tl)
    global_ratio = total_c / max(total_t, 1)

    def deviation(cs: int, ts: int) -> float:
        return 0.05 * abs(math.log(((cs + 10) / (ts + 10)) / global_ratio))

    inf = float("inf")
    dp = [[inf] * (m + 1) for _ in range(n + 1)]
    back = [[None] * (m + 1) for _ in range(n + 1)]
    dp[0][0] = 0.0

    for i in range(n + 1):
        for j in range(m + 1):
            current = dp[i][j]
            if current >= inf:
                continue

            if i < n and j < m:
                score = sim(i, j)
                cost = max(0.05, 0.62 - 0.85 * score) + deviation(cl[i], tl[j])
                if score < 0.02:
                    cost = 0.95
                if current + cost < dp[i + 1][j + 1]:
                    dp[i + 1][j + 1] = current + cost
                    back[i + 1][j + 1] = ("pair", i, j, score)

            if i < n:
                cost = 0.52
                if current + cost < dp[i + 1][j]:
                    dp[i + 1][j] = current + cost
                    back[i + 1][j] = ("content", i, j, 0.0)

            if j < m:
                cost = 1.05
                if current + cost < dp[i][j + 1]:
                    dp[i][j + 1] = current + cost
                    back[i][j + 1] = ("translation", i, j, 0.0)

            if i + 1 < n and j < m:
                score = max(sim(i, j), sim(i + 1, j)) * 0.8 + 0.2 * min(sim(i, j), sim(i + 1, j))
                cost = max(0.1, 0.62 - 0.85 * score) + 0.28 + deviation(cl[i] + cl[i + 1], tl[j])
                if current + cost < dp[i + 2][j + 1]:
                    dp[i + 2][j + 1] = current + cost
                    back[i + 2][j + 1] = ("c2t1", i, j, score)

            if i < n and j + 1 < m:
                score = max(sim(i, j), sim(i, j + 1)) * 0.8 + 0.2 * min(sim(i, j), sim(i, j + 1))
                cost = max(0.1, 0.62 - 0.85 * score) + 0.32 + deviation(cl[i], tl[j] + tl[j + 1])
                if current + cost < dp[i + 1][j + 2]:
                    dp[i + 1][j + 2] = current + cost
                    back[i + 1][j + 2] = ("c1t2", i, j, score)

    path: list[tuple] = []
    i, j = n, m
    while i > 0 or j > 0:
        step = back[i][j]
        if step is None:
            return None
        kind, pi, pj, score = step
        path.append((kind, pi, i, pj, j, score))
        i, j = pi, pj
    path.reverse()

    groups: list[AlignmentGroup] = []
    for kind, ci, cj, tj, tjj, score in path:
        if kind == "translation":
            return None
        groups.append(
            AlignmentGroup(
                content_indices=list(range(ci, cj)),
                translation_indices=list(range(tj, tjj)),
                score=score,
                kind=kind,
            )
        )
    return groups


def text_similarity(left: str, right: str) -> float:
    """两个短文本的字符二元组相似度，用于把跨韵文的长译文拆回前后两段。"""
    left_grams = _grams(left)
    right_grams = _grams(right)
    if not left_grams or not right_grams:
        return 0.0
    common = sum(value * right_grams.get(key, 0) for key, value in left_grams.items())
    left_norm = math.sqrt(sum(value * value for value in left_grams.values()))
    right_norm = math.sqrt(sum(value * value for value in right_grams.values()))
    if not left_norm or not right_norm:
        return 0.0
    cosine = common / (left_norm * right_norm)
    containment = common / min(left_norm ** 2, right_norm ** 2)
    return 0.5 * cosine + 0.5 * containment


def verse_indices(paragraphs: list[str]) -> list[int]:
    return [index for index, text in enumerate(paragraphs) if "兮" in text]
