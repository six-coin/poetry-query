"""导出共用的路径与错误处理。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_INVALID_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


class ExportError(RuntimeError):
    """可直接展示给用户的导出错误。"""


@dataclass(frozen=True)
class ExportResult:
    path: Path
    overwritten: bool
    size: int


def sanitize_filename(title: str, fallback: str = "未命名") -> str:
    name = _INVALID_FILENAME.sub("", title or "")
    name = re.sub(r"\s+", " ", name).strip().strip(".")
    if not name:
        name = fallback
    if name.upper() in _RESERVED:
        name = f"_{name}"
    return name[:80].rstrip(" .")


def resolve_output_path(output_dir: Path, title: str, suffix: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = sanitize_filename(title)
    return output_dir / f"{stem}{suffix}"
