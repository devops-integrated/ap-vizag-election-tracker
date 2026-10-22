#!/usr/bin/env python3
"""Collect election headlines and monitor official APSEC/GVMC pages.
News headlines are reported items; content linked from government domains is labelled
as an official-source page and still needs to be checked for the exact legal status.
"""
import json
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "news.json"
IST = ZoneInfo("Asia/Kolkata")
USER_AGENT = "Mozilla/5.0 (compatible; AP-Vizag-Election-Tracker/1.0)"
KEYWORDS = (
    "election", "ward", "reservation", "candidate", "contesting", "result",
    "notification", "nomination", "municipal", "local body", "delimitation",
    "poll", "corporator", "seat", "violence", "attack", "attacked", "intimidation",
    "threat", "clash", "arson", "firing", "assault", "complaint", "fir", "arrest",
    "nomination paper", "snatched", "torn", "house arrest", "supreme court", "petition"
)
QUERIES = [
    ("Andhra Pradesh elections", '(Andhra Pradesh OR AP) election (SEC OR municipal OR local body OR candidate)'),
    ("Visakhapatnam / GVMC", '(Visakhapatnam OR Vizag OR GVMC) (election OR ward OR corporator OR candidate)'),
    ("AP State Election Commission", 'site:sec.ap.gov.in election Andhra Pradesh'),
    ("APSEC notices and candidates", 'site:demo8.cgg.gov.in/apsec (election OR candidate OR result OR notification)'),
    ("GVMC official notices", 'site:gvmc.gov.in (election OR ward OR reservation OR notification)'),
    ("AP election violence and complaints", 'Andhra Pradesh local body election violence attack intimidation complaint nomination papers police October 2026'),
    ("AP election court and SEC actions", 'Andhra Pradesh State Election Commission Supreme Court election complaint violence nomination October 2026'),
    ("Vizag / GVMC incidents", '(Visakhapatnam OR Vizag OR GVMC) election violence complaint intimidation attack nomination'),
]
FEED_BASE = "https://news.google.com/rss/search"

# These are public pages. The collector does not access logins or protected portals.
OFFICIAL_PAGES = [
    ("GVMC official website", "https://www.gvmc.gov.in/"),
    ("AP State Election Commission portal", "https://demo8.cgg.gov.in/apsec/"),
    ("APSEC election notices", "https://demo8.cgg.gov.in/apsec/electionNotice"),
    ("APSEC contesting candidates", "https://demo8.cgg.gov.in/apsec/contestingCandidates"),
    ("APSEC results", "https://demo8.cgg.gov.in/apsec/electedRepresentatives"),
    ("APSEC voter portal", "https://demo8.cgg.gov.in/apsec/voterPortalHome"),
]


def text_of(parent, tag):
    node = parent.find(tag)
    return (node.text or "").strip() if node is not None else ""


def parse_date(value):
    if not value:
        return ""
    try:
        return parsedate_to_datetime(value).strftime("%d %b %Y, %I:%M %p %Z")
    except Exception:
        return value


def fetch(url, accept="text/html,application/xhtml+xml,application/rss+xml,application/xml;q=0.9,*/*;q=0.8"):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": accept})
    with urllib.request.urlopen(req, timeout=25) as response:
        return response.read(), response.geturl()


def scrape_official_page(label, page_url):
    found = []
    try:
        raw, final_url = fetch(page_url)
        soup = BeautifulSoup(raw, "html.parser")
        page_title = soup.title.get_text(" ", strip=True) if soup.title else label
        found.append({
            "title": f"{label}: page checked — {page_title[:180]}",
            "link": final_url,
            "source": label,
            "published": "",
            "feed": "Official website monitor",
            "status": "Official source",
            "note": "Official page checked automatically; open the source to inspect the latest notice."
        })
        for anchor in soup.find_all("a", href=True):
            link_text = " ".join(anchor.get_text(" ", strip=True).split())
            href = urljoin(final_url, anchor["href"].strip())
            if not link_text or href.startswith(("javascript:", "mailto:", "#")):
                continue
            if urlparse(href).scheme not in ("http", "https"):
                continue

            context = link_text
            # Walk up only a few levels and use the smallest nearby block containing a relevant keyword.
            parent = anchor
            for _ in range(4):
                parent = parent.parent
                if not parent:
                    break
                candidate = " ".join(parent.get_text(" ", strip=True).split())
                if candidate and len(candidate) <= 700 and any(k in candidate.lower() for k in KEYWORDS):
                    context = candidate
                    break
            if not any(k in (link_text + " " + context + " " + href).lower() for k in KEYWORDS):
                continue
            title = link_text
            if len(title) < 8 and context:
                title = context[:240]
            item = {
                "title": title[:240],
                "link": href,
                "source": label,
                "published": "",
                "feed": "Official website monitor",
                "status": "Official source",
                "note": "Collected from an official government/commission website; verify the linked notice itself."
            }
            found.append(item)
    except Exception as exc:
        print(f"Official source fetch failed for {label} ({page_url}): {exc}")
        found.append({
            "title": f"{label}: source could not be fetched during this check",
            "link": page_url,
            "source": label,
            "published": "",
            "feed": "Official website monitor",
            "status": "Source check failed",
            "note": "The site may be temporarily unavailable or may have changed its page structure."
        })
    return found


def main():
    items = []
    seen = set()
    checked = datetime.now(IST).strftime("%d %b %Y, %I:%M:%S %p IST")

    # First, inspect official government/commission pages directly.
    for label, page_url in OFFICIAL_PAGES:
        for item in scrape_official_page(label, page_url):
            key = item["link"] + "|" + item["title"]
            if key not in seen:
                seen.add(key)
                items.append(item)

    # Then gather broader media coverage through public RSS search feeds.
    for label, query in QUERIES:
        params = urllib.parse.urlencode({"q": query, "hl": "en-IN", "gl": "IN", "ceid": "IN:en"})
        url = FEED_BASE + "?" + params
        try:
            xml_data, _ = fetch(url, "application/rss+xml,application/xml;q=0.9,*/*;q=0.8")
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
                    "status": "Reported",
                    "note": "News-search result; not official confirmation."
                })
        except Exception as exc:
            print(f"News feed fetch failed for {label}: {exc}")

    # Keep a bounded feed file; prioritize official source links before media reports.
    payload = {
        "updated_at_ist": checked,
        "update_frequency": "Scheduled approximately every 3 hours; manual workflow runs are also supported",
        "source_note": "Official-source links are collected from public government pages. Media headlines are reported items, not official confirmation.",
        "items": items[:120]
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(payload['items'])} items to {OUT}; checked {len(OFFICIAL_PAGES)} official pages.")


if __name__ == "__main__":
    main()
