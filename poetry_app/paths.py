"""应用路径解析。

开发时以项目根目录为准；打包后优先使用 PyInstaller 的 _MEIPASS 资源目录，
输出目录始终位于可执行文件旁边，避免写入只读的程序目录。
"""

from __future__ import annotations

import sys
from pathlib import Path


def _is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def project_root() -> Path:
    if _is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resource_root() -> Path:
    if _is_frozen() and hasattr(sys, "_MEIPASS"):
        return Path(getattr(sys, "_MEIPASS")).resolve()
    return project_root()


PROJECT_ROOT = project_root()
RESOURCE_ROOT = resource_root()

DB_PATH = RESOURCE_ROOT / "assets" / "poetry.db"
if not DB_PATH.exists():
    DB_PATH = PROJECT_ROOT / "assets" / "poetry.db"

WEB_DIR = RESOURCE_ROOT / "poetry_app" / "web"
ICON_PATH = RESOURCE_ROOT / "assets" / "app_icon.ico"
OUTPUT_DIR = PROJECT_ROOT / "output"
LOG_DIR = PROJECT_ROOT / "logs"
CONFIG_DIR = PROJECT_ROOT / "config"
CONFIG_PATH = CONFIG_DIR / "config.json"


def ensure_runtime_dirs() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
