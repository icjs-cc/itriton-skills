#!/usr/bin/env python3
"""Refresh places scene table from official 2022 tour XML (network)."""

from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path

BASE = "https://3d.xmut.edu.cn/2022/indexdata"
MESSAGES = f"{BASE}/index_messages_zh.xml"
OUT = Path(__file__).resolve().parents[1] / "references" / "scene_index.md"


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "xmut-panorama-skill/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="replace")


def main() -> None:
    text = fetch(MESSAGES)
    titles = re.findall(
        r'<data name="zh_(pano\d+)_title"><!\[CDATA\[(.*?)\]\]></data>', text
    )
    lines = [
        "# 2022 场景索引（自动生成）",
        "",
        "来源：`index_messages_zh.xml`",
        "",
        "| scene_id | 标题 | 3D 深链 |",
        "|----------|------|---------|",
    ]
    for scene_id, title in titles:
        url = f"https://3d.xmut.edu.cn/2022/?startscene={scene_id}"
        lines.append(f"| `{scene_id}` | {title} | {url} |")
    lines.append("")
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {OUT} ({len(titles)} scenes)")
    print(json.dumps({k: v for k, v in titles}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
