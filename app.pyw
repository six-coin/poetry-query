"""诗笺桌面应用入口。

运行：
    python app.pyw
"""

from __future__ import annotations

import logging
import os
import sys
import traceback
from logging.handlers import RotatingFileHandler

from poetry_app.api import Api
from poetry_app.config import (
    APP_TITLE,
    WINDOW_HEIGHT,
    WINDOW_MIN_HEIGHT,
    WINDOW_MIN_WIDTH,
    WINDOW_WIDTH,
)
from poetry_app.database import PoemRepository
from poetry_app.paths import DB_PATH, ICON_PATH, LOG_DIR, OUTPUT_DIR, WEB_DIR, ensure_runtime_dirs


def setup_logging() -> None:
    ensure_runtime_dirs()
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")

    try:
        handler = RotatingFileHandler(
            LOG_DIR / "app.log", maxBytes=1_500_000, backupCount=3, encoding="utf-8"
        )
        handler.setFormatter(formatter)
        root.addHandler(handler)
    except OSError:
        pass

    if sys.stderr is not None:
        console = logging.StreamHandler()
        console.setFormatter(formatter)
        root.addHandler(console)


def _message_box(title: str, text: str) -> None:
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(0, text, title, 0x10)
    except Exception:
        print(f"{title}: {text}", file=sys.stderr)


def main() -> None:
    setup_logging()
    logger = logging.getLogger("poetry_app")
    logger.info("starting shijian desktop app")

    if not WEB_DIR.joinpath("index.html").exists():
        _message_box(APP_TITLE, f"界面文件缺失：{WEB_DIR}")
        return
    if not DB_PATH.exists():
        _message_box(APP_TITLE, f"诗文数据库缺失：\n{DB_PATH}")
        return

    try:
        import webview
    except Exception as exc:
        logger.exception("pywebview import failed")
        _message_box(APP_TITLE, f"无法启动界面组件 pywebview：\n{exc}")
        return

    repository = PoemRepository(DB_PATH)
    api = Api(repository, OUTPUT_DIR)
    storage = LOG_DIR / "webview"
    storage.mkdir(parents=True, exist_ok=True)

    webview.create_window(
        APP_TITLE,
        url=WEB_DIR.joinpath("index.html").as_uri(),
        js_api=api,
        width=WINDOW_WIDTH,
        height=WINDOW_HEIGHT,
        min_size=(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT),
        background_color="#F7F3EA",
        text_select=True,
        confirm_close=False,
        easy_drag=False,
    )

    debug = os.environ.get("POETRY_DEBUG", "").lower() in {"1", "true", "yes"}
    try:
        webview.start(
            debug=debug,
            private_mode=False,
            storage_path=str(storage),
            menu=[],
            icon=str(ICON_PATH) if ICON_PATH.exists() else None,
        )
    except Exception as exc:
        logger.exception("webview.start failed")
        _message_box(
            APP_TITLE,
            "启动窗口失败。请确认系统已安装 Microsoft Edge WebView2 运行库。\n\n"
            f"{exc}",
        )


if __name__ == "__main__":
    try:
        main()
    except Exception:
        detail = traceback.format_exc()
        try:
            setup_logging()
            logging.getLogger("poetry_app").error("fatal error\n%s", detail)
        except Exception:
            pass
        _message_box(APP_TITLE, f"程序发生未处理的错误：\n\n{detail[-1800:]}")
        raise
