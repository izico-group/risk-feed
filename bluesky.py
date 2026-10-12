#!/usr/bin/env python3
"""Bluesky collector (free public API, no key). Writes data/bluesky.json every run."""
import json, os, urllib.request, urllib.parse
from datetime import datetime, timezone, timedelta

HANDLES = [  # verified 2026-10-12; add more, one per line
    "bellingcat.com",
    "eliothiggins.bsky.social",
    "osinttechnical.bsky.social",
    "netblocks.org",
]
ROOT = os.path.dirname(os.path.abspath(__file__))
NOW = datetime.now(timezone.utc)

def cfg(name):
    p = os.path.join(ROOT, "config", name)
    return [l.strip() for l in open(p, encoding="utf-8") if l.strip() and not l.startswith("#")] if os.path.exists(p) else []

KW = [k.lower() for k in cfg("keywords.txt")]
EM = cfg("emojis.txt")
handles = HANDLES + [h for h in cfg("bluesky.txt") if h not in HANDLES]

items, errors = [], []
cutoff = NOW - timedelta(hours=72)
for h in handles:
    url = "https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed?" + urllib.parse.urlencode({"actor": h, "limit": 15, "filter": "posts_no_replies"})
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "risk-feed"}), timeout=20) as r:
            feed = json.load(r).get("feed", [])
    except Exception as e:
        errors.append(f"{h}: {e}"); continue
    for f in feed:
        p = f.get("post", {}); rec = p.get("record", {})
        text, ts = rec.get("text", ""), rec.get("createdAt", "")
        try:
            if datetime.fromisoformat(ts.replace("Z", "+00:00")) < cutoff: continue
        except Exception:
            pass
        kw = [k for k in KW if k in text.lower()]; em = [e for e in EM if e in text]
        rkey = p.get("uri", "").rsplit("/", 1)[-1]
        items.append({"id": "bsky:" + p.get("uri", ""), "kind": "bsky", "src": h, "text": text[:600],
                      "url": f"https://bsky.app/profile/{h}/post/{rkey}", "time": ts,
                      "keywords": kw, "emojis": em, "alert": bool(kw or em)})

items.sort(key=lambda i: i["time"], reverse=True)
os.makedirs(os.path.join(ROOT, "data"), exist_ok=True)
json.dump({"updated": NOW.isoformat(), "accounts": len(handles), "errors": errors, "items": items[:400]},
          open(os.path.join(ROOT, "data", "bluesky.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"bluesky: {len(items)} posts from {len(handles)} accounts, {len(errors)} errors")
