#!/usr/bin/env python3
"""Fully automatic AI daily briefing.

Fetches RSS feeds -> summarizes with Gemini (free tier) -> writes a web page
into docs/ (GitHub Pages) -> optionally sends it to Telegram.
Runs unattended from GitHub Actions. No server needed.
"""
import html
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import feedparser
import requests
import yaml

ROOT = Path(__file__).parent
CFG = yaml.safe_load((ROOT / "config.yaml").read_text())
IST = timezone(timedelta(hours=5, minutes=30))
GEMINI_KEY = os.getenv("GEMINI_API_KEY", "")
TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TG_CHAT = os.getenv("TELEGRAM_CHAT_ID", "")


def collect():
    cutoff = datetime.now(timezone.utc) - timedelta(hours=CFG.get("hours_back", 26))
    items = []
    for feed in CFG["feeds"]:
        try:
            parsed = feedparser.parse(feed["url"], agent="autodigest/1.0")
        except Exception as e:  # keep going if one feed breaks
            print(f"feed failed {feed['name']}: {e}", file=sys.stderr)
            continue
        n = 0
        for e in parsed.entries:
            ts = e.get("published_parsed") or e.get("updated_parsed")
            if ts and datetime(*ts[:6], tzinfo=timezone.utc) < cutoff:
                continue
            items.append({
                "source": feed["name"],
                "title": e.get("title", "").strip(),
                "link": e.get("link", ""),
                "summary": html.unescape(e.get("summary", ""))[:400],
            })
            n += 1
            if n >= CFG.get("max_items_per_feed", 8):
                break
    return items


def ask_gemini(prompt):
    if not GEMINI_KEY:
        return None
    url = ("https://generativelanguage.googleapis.com/v1beta/models/"
           f"{CFG.get('model', 'gemini-2.5-flash')}:generateContent")
    body = {"contents": [{"parts": [{"text": prompt}]}]}
    for attempt in range(3):
        r = requests.post(url, params={"key": GEMINI_KEY}, json=body, timeout=90)
        if r.status_code == 200:
            try:
                return r.json()["candidates"][0]["content"]["parts"][0]["text"]
            except (KeyError, IndexError):
                return None
        time.sleep(5 * (attempt + 1))
    return None


def summarize(items):
    if not items:
        return "No new items in the last window."
    listing = "\n".join(
        f"{i+1}. [{x['source']}] {x['title']} - {x['summary'][:200]} ({x['link']})"
        for i, x in enumerate(items))
    prompt = (
        f"You are my personal news editor. My interests: {CFG['interests']}.\n"
        "From the items below write a concise morning briefing in Markdown: "
        "a 3-sentence overview, then 'Top stories' (max 7 bullets, each with a "
        "one-line why-it-matters and the link), then 'Worth watching' (max 3). "
        "Do not invent facts; use only the items.\n\n" + listing)
    out = ask_gemini(prompt)
    if out:
        return out
    # Fallback without AI so the pipeline never fails
    return "\n".join(f"- [{x['title']}]({x['link']}) ({x['source']})" for x in items)


def md_to_html(md):
    out, in_list = [], False
    for line in md.splitlines():
        s = html.escape(line.rstrip())
        if s.startswith(("- ", "* ")):
            if not in_list:
                out.append("<ul>"); in_list = True
            s = s[2:]
            s = _links(s)
            out.append(f"<li>{s}</li>")
            continue
        if in_list:
            out.append("</ul>"); in_list = False
        if s.startswith("#"):
            lvl = min(len(s) - len(s.lstrip("#")), 3)
            out.append(f"<h{lvl+1}>{_links(s.lstrip('# '))}</h{lvl+1}>")
        elif s:
            out.append(f"<p>{_links(s)}</p>")
    if in_list:
        out.append("</ul>")
    return "\n".join(out)


def _links(s):
    import re
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    return re.sub(r"\[(.+?)\]\((https?://[^)\s]+)\)", r'<a href="\2">\1</a>', s)


def write_site(md, items):
    docs = ROOT / "docs"
    (docs / "archive").mkdir(parents=True, exist_ok=True)
    today = datetime.now(IST).strftime("%Y-%m-%d")
    stamp = datetime.now(IST).strftime("%A, %d %B %Y %H:%M IST")
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(CFG['title'])}</title>
<style>
:root{{--bg:#fff;--fg:#1a1a1a;--mut:#666;--ac:#0b57d0}}
@media(prefers-color-scheme:dark){{:root{{--bg:#121212;--fg:#eee;--mut:#999;--ac:#8ab4f8}}}}
body{{background:var(--bg);color:var(--fg);font:17px/1.6 system-ui,sans-serif;max-width:720px;margin:0 auto;padding:16px}}
a{{color:var(--ac)}} .m{{color:var(--mut);font-size:14px}} li{{margin:.5em 0}}
</style></head><body>
<h1>{html.escape(CFG['title'])}</h1><p class="m">{stamp} &middot; {len(items)} items scanned &middot; <a href="archive/">archive</a></p>
{md_to_html(md)}
</body></html>"""
    (docs / "index.html").write_text(page)
    (docs / "archive" / f"{today}.html").write_text(page)
    days = sorted(p.stem for p in (docs / "archive").glob("2*.html"))[::-1]
    idx = "<!doctype html><meta charset=utf-8><title>Archive</title><h1>Archive</h1><ul>" + \
        "".join(f'<li><a href="{d}.html">{d}</a></li>' for d in days) + "</ul>"
    (docs / "archive" / "index.html").write_text(idx)
    (docs / "latest.json").write_text(json.dumps(
        {"date": today, "markdown": md, "count": len(items)}, indent=2))


def telegram(md):
    if not (TG_TOKEN and TG_CHAT):
        print("Telegram not configured; skipping.")
        return
    for i in range(0, len(md), 3800):
        requests.post(
            f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
            json={"chat_id": TG_CHAT, "text": md[i:i + 3800],
                  "disable_web_page_preview": True}, timeout=30)


def main():
    items = collect()
    print(f"collected {len(items)} items")
    md = summarize(items)
    write_site(md, items)
    telegram(md)
    print("done")


if __name__ == "__main__":
    main()
