"""用户界面配置的磁盘持久化。

配置文件固定在项目根目录（打包后为可执行文件旁）的 config/config.json，
不依赖 WebView2 的 localStorage，重装/清理缓存后不会丢失。
"""

from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path

from .paths import CONFIG_PATH

DEFAULT_SETTINGS: dict = {
    "preset": "paper",
    "accent": "#a4422f",
    "paper": "#f7f3ea",
    "card": "#fffdf8",
    "ink": "#26231e",
    "contentPercent": 72,
    "originalFont": "song",
    "translationFont": "song",
    "notesFont": "song",
    "originalSize": 19.5,
    "translationSize": 16.5,
    "notesSize": 14.5,
}

FONT_IDS = {"song", "kai", "fangsong", "hei", "deng"}
_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
_LOCK = threading.Lock()


def default_settings() -> dict:
    return dict(DEFAULT_SETTINGS)


def _number(value, fallback: float, low: float, high: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return fallback
    return max(low, min(high, number))


def _color(value, fallback: str) -> str:
    text = str(value or "").strip()
    return text.lower() if _COLOR_RE.match(text) else fallback


def normalize_settings(value) -> dict:
    source = value if isinstance(value, dict) else {}
    settings = default_settings()
    settings["preset"] = str(source.get("preset") or "custom")
    for key in ("accent", "paper", "card", "ink"):
        settings[key] = _color(source.get(key), DEFAULT_SETTINGS[key])
    settings["contentPercent"] = int(_number(source.get("contentPercent"), 72, 50, 96))
    for key in ("originalFont", "translationFont", "notesFont"):
        candidate = str(source.get(key) or DEFAULT_SETTINGS[key])
        settings[key] = candidate if candidate in FONT_IDS else DEFAULT_SETTINGS[key]
    settings["originalSize"] = round(_number(source.get("originalSize"), 19.5, 14, 30) * 2) / 2
    settings["translationSize"] = round(_number(source.get("translationSize"), 16.5, 12, 26) * 2) / 2
    settings["notesSize"] = round(_number(source.get("notesSize"), 14.5, 11, 22) * 2) / 2
    return settings


def load_settings(path: Path = CONFIG_PATH) -> dict:
    path = Path(path)
    with _LOCK:
        try:
            if not path.exists():
                settings = default_settings()
                _write(path, settings)
                return settings
            data = json.loads(path.read_text(encoding="utf-8"))
            return normalize_settings(data)
        except (OSError, ValueError, TypeError):
            return default_settings()


def save_settings(value, path: Path = CONFIG_PATH) -> dict:
    path = Path(path)
    settings = normalize_settings(value)
    with _LOCK:
        _write(path, settings)
    return settings


def _write(path: Path, settings: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    text = json.dumps(settings, ensure_ascii=False, indent=2) + "\n"
    temp.write_text(text, encoding="utf-8")
    os.replace(temp, path)
