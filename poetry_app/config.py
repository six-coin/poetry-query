"""全局常量与界面/导出共用的样式约定。"""

from __future__ import annotations

APP_NAME = "诗笺"
APP_TITLE = "诗笺 · 古诗文查询与笺注"
APP_VERSION = "1.0.0"

WINDOW_WIDTH = 1240
WINDOW_HEIGHT = 880
WINDOW_MIN_WIDTH = 960
WINDOW_MIN_HEIGHT = 660

SEARCH_PAGE_SIZE = 60
SEARCH_MAX_QUERY = 80

# 中文段落缩进：两个全角空格
PARAGRAPH_INDENT = "\u3000\u3000"

SUPERSCRIPT_DIGITS = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")


def superscript(number: int) -> str:
    """把整数转换为 Unicode 上标，供纯文本或调试使用。"""
    return str(number).translate(SUPERSCRIPT_DIGITS)


# PDF 字体候选：优先使用单文件 TTF，TTC 由 ReportLab 的 subfontIndex 处理。
PDF_SERIF_FONTS = [
    ("STSong", "STSONG.TTF"),
    ("SimSun", "simsun.ttc"),
    ("NotoSerifSC", "NotoSerifSC-VF.ttf"),
    ("FangSong", "simfang.ttf"),
]
PDF_KAI_FONTS = [
    ("STKaiti", "STKAITI.TTF"),
    ("KaiTi", "simkai.ttf"),
]
PDF_SANS_FONTS = [
    ("DengXian", "Deng.ttf"),
    ("MicrosoftYaHei", "msyh.ttc"),
    ("SimHei", "simhei.ttf"),
]
PDF_FANGSONG_FONTS = [
    ("STFangsong", "STFANGSO.TTF"),
    ("FangSong", "simfang.ttf"),
]
