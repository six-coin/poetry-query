"""暴露给前端 JavaScript 的应用接口。"""

from __future__ import annotations

import logging
import os
import platform
import subprocess
import threading
from collections import OrderedDict
from dataclasses import asdict
from pathlib import Path

from .config import APP_NAME, APP_VERSION
from .database import PoemRepository
from .exporters.common import ExportError
from .exporters.pdf import PdfExporter
from .exporters.text import export_text
from .reading import build_reading
from .settings_store import CONFIG_PATH, load_settings as load_user_settings, save_settings as save_user_settings

logger = logging.getLogger(__name__)


class Api:
    def __init__(self, repository: PoemRepository, output_dir: Path) -> None:
        self.repository = repository
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._detail_cache: OrderedDict[int, dict] = OrderedDict()
        self._pdf_lock = threading.Lock()
        self._settings_lock = threading.Lock()

    # ---------- 配置 ----------

    def get_settings(self) -> dict:
        try:
            with self._settings_lock:
                settings = load_user_settings(CONFIG_PATH)
            return {"ok": True, "settings": settings, "path": str(CONFIG_PATH)}
        except Exception as exc:
            logger.exception("get_settings failed")
            return {"ok": False, "error": f"读取配置失败：{exc}"}

    def save_settings(self, settings: dict) -> dict:
        try:
            if not isinstance(settings, dict):
                return {"ok": False, "error": "配置格式无效。"}
            with self._settings_lock:
                saved = save_user_settings(settings, CONFIG_PATH)
            return {"ok": True, "settings": saved, "path": str(CONFIG_PATH)}
        except Exception as exc:
            logger.exception("save_settings failed")
            return {"ok": False, "error": f"保存配置失败：{exc}"}

    # ---------- 查询与阅读 ----------

    def get_meta(self) -> dict:
        try:
            total = self.repository.count_all()
            return {
                "ok": True,
                "appName": APP_NAME,
                "version": APP_VERSION,
                "poemCount": total,
                "outputDir": str(self.output_dir),
                "dbPath": str(self.repository.db_path),
                "platform": platform.system(),
            }
        except Exception as exc:
            logger.exception("get_meta failed")
            return {"ok": False, "error": f"无法读取诗文数据库：{exc}"}

    def search(self, query: str, offset: int = 0, limit: int = 60) -> dict:
        try:
            page = self.repository.search(str(query or ""), int(offset or 0), int(limit or 60))
            return {
                "ok": True,
                "items": [asdict(item) for item in page.items],
                "total": page.total,
            }
        except Exception as exc:
            logger.exception("search failed")
            return {"ok": False, "error": f"检索失败：{exc}"}

    def get_detail(self, poem_id: int) -> dict:
        try:
            poem_id = int(poem_id)
        except (TypeError, ValueError):
            return {"ok": False, "error": "无效的诗文编号。"}

        if poem_id in self._detail_cache:
            self._detail_cache.move_to_end(poem_id)
            return {"ok": True, "document": self._detail_cache[poem_id]}

        try:
            poem = self.repository.get(poem_id)
            if poem is None:
                return {"ok": False, "error": "没有找到这篇诗文。"}
            document = build_reading(poem).to_dict()
            self._detail_cache[poem_id] = document
            self._detail_cache.move_to_end(poem_id)
            while len(self._detail_cache) > 64:
                self._detail_cache.popitem(last=False)
            return {"ok": True, "document": document}
        except Exception as exc:
            logger.exception("get_detail failed")
            return {"ok": False, "error": f"读取诗文失败：{exc}"}

    # ---------- 导出 ----------

    def export_text(self, poem_id: int, style: str = "reading") -> dict:
        style = str(style or "reading")
        if style not in {"reading", "standard"}:
            return {"ok": False, "error": "未知的文本导出样式。"}
        try:
            poem = self.repository.get(int(poem_id))
            if poem is None:
                return {"ok": False, "error": "没有找到这篇诗文。"}
            result = export_text(poem, self.output_dir, style)
            return {
                "ok": True,
                "path": str(result.path),
                "size": result.size,
                "overwritten": result.overwritten,
                "kind": "text",
            }
        except Exception as exc:
            logger.exception("export_text failed")
            return {"ok": False, "error": f"导出文本失败：{exc}"}

    def export_pdf(
        self,
        poem_id: int,
        mode: str = "full",
        settings: dict | None = None,
        background: bool = True,
    ) -> dict:
        mode = str(mode or "full")
        if mode not in {"original", "translation", "full"}:
            return {"ok": False, "error": "未知的导出模式。"}
        try:
            poem = self.repository.get(int(poem_id))
            if poem is None:
                return {"ok": False, "error": "没有找到这篇诗文。"}
            document = build_reading(poem)
            options = settings if isinstance(settings, dict) else None
            with self._pdf_lock:
                exporter = PdfExporter(options, background=bool(background))
                result = exporter.export(document, mode, self.output_dir)
            return {
                "ok": True,
                "path": str(result.path),
                "size": result.size,
                "overwritten": result.overwritten,
                "kind": "pdf",
            }
        except ExportError as exc:
            logger.warning("export_pdf rejected: %s", exc)
            return {"ok": False, "error": str(exc)}
        except Exception as exc:
            logger.exception("export_pdf failed")
            return {"ok": False, "error": f"导出 PDF 失败：{exc}"}

    # ---------- 系统 ----------

    def open_path(self, path: str) -> dict:
        try:
            target = Path(str(path)).resolve()
            output_root = self.output_dir.resolve()
            if not target.exists():
                return {"ok": False, "error": "文件不存在，可能已被移动。"}
            if not target.is_relative_to(output_root):
                return {"ok": False, "error": "只能打开导出目录中的文件。"}
            _open_in_shell(target)
            return {"ok": True}
        except Exception as exc:
            logger.exception("open_path failed")
            return {"ok": False, "error": f"无法打开文件：{exc}"}

    def open_output_dir(self) -> dict:
        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
            _open_in_shell(self.output_dir)
            return {"ok": True}
        except Exception as exc:
            logger.exception("open_output_dir failed")
            return {"ok": False, "error": f"无法打开导出目录：{exc}"}


def _open_in_shell(target: Path) -> None:
    if os.name == "nt":
        os.startfile(str(target))  # type: ignore[attr-defined]
    elif platform.system() == "Darwin":
        subprocess.Popen(["open", str(target)])
    else:
        subprocess.Popen(["xdg-open", str(target)])
