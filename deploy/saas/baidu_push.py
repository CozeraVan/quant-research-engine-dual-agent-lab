#!/usr/bin/env python3
"""百度站长平台主动推送：把 sitemap.xml 里的 URL 推送给百度，加速收录。

用法（ECS 上或本地均可）：
    BAIDU_PUSH_TOKEN=<token> python3 deploy/saas/baidu_push.py [--site https://www.aguhuice.com]

- token 从环境变量 BAIDU_PUSH_TOKEN 读取（存放在 ECS /etc/qre-saas.env，不入 git）。
- URL 列表默认取线上 sitemap.xml，也可用 --file 指定本地文本文件（一行一个 URL）。
- 新站每日推送配额很小（当前约 10 条/日），脚本会把剩余额度打印出来。
"""
from __future__ import annotations

import argparse
import os
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

# 无需收录的页面（登录页等）
EXCLUDE_SUBSTRINGS = ("/login",)

PUSH_API = "http://data.zz.baidu.com/urls"


def load_urls_from_sitemap(site: str) -> list[str]:
    with urllib.request.urlopen(f"{site}/sitemap.xml", timeout=15) as resp:
        root = ET.fromstring(resp.read())
    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    return [loc.text.strip() for loc in root.findall("sm:url/sm:loc", ns) if loc.text]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", default="https://www.aguhuice.com")
    parser.add_argument("--file", help="本地 URL 列表文件（一行一个），优先级高于 sitemap")
    args = parser.parse_args()

    token = os.environ.get("BAIDU_PUSH_TOKEN", "").strip()
    if not token:
        print("ERROR: 缺少环境变量 BAIDU_PUSH_TOKEN", file=sys.stderr)
        return 2

    if args.file:
        with open(args.file, encoding="utf-8") as fh:
            urls = [ln.strip() for ln in fh if ln.strip()]
    else:
        urls = load_urls_from_sitemap(args.site)
    urls = [u for u in urls if not any(s in u for s in EXCLUDE_SUBSTRINGS)]
    if not urls:
        print("没有可推送的 URL", file=sys.stderr)
        return 1

    endpoint = f"{PUSH_API}?site={args.site}&token={token}"
    body = "\n".join(urls).encode("utf-8")
    req = urllib.request.Request(endpoint, data=body, headers={"Content-Type": "text/plain"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            print(f"推送 {len(urls)} 条 → {resp.read().decode('utf-8')}")
    except urllib.error.HTTPError as exc:
        # 常见：配额不足（over quota）返回 400，正文里有具体原因
        print(f"推送失败 HTTP {exc.code}: {exc.read().decode('utf-8', 'replace')}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
