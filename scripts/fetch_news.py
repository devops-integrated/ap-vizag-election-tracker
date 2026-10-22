#!/usr/bin/env python3
"""Fetch election-related Google News RSS results into a small static JSON feed.
Items are reported news, not official election records.
"""
import json
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "news.json"
QUERIES = [
    ("Andhra Pradesh elections", '(Andhra Pradesh OR AP) election (SEC OR municipal OR local body OR candidate)'),
    ("Visakhapatnam / GVMC", '(Visakhapatnam OR Vizag OR GVMC) (election OR ward OR corporator OR candidate)'),
    ("AP State Election Commission", 'site:sec.ap.gov.in election Andhra Pradesh'),
    ("GVMC official notices", 'site:gvmc.gov.in election ward Visakhapatnam'),
]
FEED_BASE = "https://news.google.com/rss/search"
IST = ZoneInfo("Asia/Kolkata")


def text_of(parent, tag):
    node = parent.find(tag)
    return (node.text or "").strip() if node is not None else ""


def parse_date(value):
    if not value:
        return ""
    try:
        dt = parsedate_to_datetime(value)
        return dt.strftime("%d %b %Y, %I:%M %p %Z")
    except Exception:
        return value


def main():
    items = []
    seen = set()
    checked = datetime.now(IST).strftime("%d %b %Y, %I:%M:%S %p IST")
    for label, query in QUERIES:
        params = urllib.parse.urlencode({
            "q": query, "hl": "en-IN", "gl": "IN", "ceid": "IN:en"
        })
        url = FEED_BASE + "?" + params
        req = urllib.request.Request(url, headers={"User-Agent": "AP-Vizag-Election-Tracker/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=25) as response:
                xml_data = response.read()
            root = ET.fromstring(xml_data)
            for node in root.findall("./channel/item"):
                title = text_of(node, "title")
                link = text_of(node, "link")
                if not title or not link or link in seen:
                    continue
                seen.add(link)
                source_node = node.find("source")
                source = (source_node.text or "").strip() if source_node is not None else label
                items.append({
                    "title": title,
                    "link": link,
                    "source": source or label,
                    "published": parse_date(text_of(node, "pubDate")),
                    "feed": label,
                    "status": "Reported"
                })
        except Exception as exc:
            print(f"Feed fetch failed for {label}: {exc}")

    # Newest first where the publisher date can be parsed.
    def sort_key(item):
        try:
            return parsedate_to_datetime(item.get("published_raw", ""))
        except Exception:
            return datetime.min.replace(tzinfo=ZoneInfo("UTC"))

    # Preserve the RSS feed ordering while deduplicating; cap the published feed size.
    payload = {
        "updated_at_ist": checked,
        "update_frequency": "Scheduled approximately every 3 hours",
        "source_note": "Search-feed headlines are reported items, not official confirmation.",
        "items": items[:80]
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(payload['items'])} unique headlines to {OUT}")


if __name__ == "__main__":
    main()
