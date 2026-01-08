# live48_scraper.py
import re
import requests
from bs4 import BeautifulSoup
from typing import Dict, List

DT_RE = re.compile(r"(\d{4})年(\d{2})月(\d{2})日(\d{2}:\d{2}:\d{2})")

def _clean_lines(text: str) -> List[str]:
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    return lines

def _extract_one_show_from_lines(lines: List[str]) -> Dict[str, object] | None:
    """
    从一个 watchcontent 块的文本行中提取一场公演。
    """
    show_idx = None
    show_line = None
    for i, ln in enumerate(lines):
        if DT_RE.search(ln):
            show_idx = i
            show_line = ln
            break

    if show_idx is None or show_line is None:
        return None

    m = DT_RE.search(show_line)
    yyyy, mm, dd, hms = m.groups()
    date_dash = f"{yyyy}-{mm}-{dd}"
    datetime_str = f"{yyyy}-{mm}-{dd} {hms}"
    show_name = show_line[:m.start()].strip()

    members: List[str] = []
    for ln in lines[show_idx + 1:]:
        if "查看所有参演人员" in ln:
            break

        # 过滤明显无关
        if ln in ("即将开始", "登录", "历史公演", "公演直播"):
            continue

        # 通常成员名 2~6 中文字符
        if re.fullmatch(r"[\u4e00-\u9fff]{2,6}", ln):
            members.append(ln)

    # 去重保序
    seen = set()
    members = [x for x in members if not (x in seen or seen.add(x))]

    return {
        "show_name": show_name,
        "date_dash": date_dash,
        "datetime": datetime_str,
        "members": members,
    }

def fetch_shows_and_members(url: str) -> List[Dict[str, object]]:
    """
    返回页面上所有 watchcontent 的公演数据（一天两场也能抓到）。
    """
    html = requests.get(url, timeout=20).text
    soup = BeautifulSoup(html, "html.parser")

    blocks = soup.select(".watchcontent")
    results: List[Dict[str, object]] = []

    # 有些情况下 selector 可能拿不到（页面结构变动/类名不同），做个 fallback
    if not blocks:
        text = soup.get_text("\n", strip=True)
        one = _extract_one_show_from_lines(_clean_lines(text))
        return [one] if one else []

    for b in blocks:
        text = b.get_text("\n", strip=True)
        lines = _clean_lines(text)
        one = _extract_one_show_from_lines(lines)
        if one:
            results.append(one)

    # 去重：同一场可能被重复渲染（保险）
    uniq = []
    seen = set()
    for x in results:
        key = (x["show_name"], x["datetime"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(x)

    return uniq
