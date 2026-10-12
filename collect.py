#!/usr/bin/env python3
"""Risk-feed collector: military aircraft (ADS-B), public Telegram channels, RSS news, optional X accounts.
Runs every 5 minutes on GitHub Actions. Standard library only. Writes data/feed.json and data/alerts.json."""
import json, os, re, time, html, urllib.request, urllib.parse, xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

ROOT = os.path.dirname(os.path.abspath(__file__))
CFG = os.path.join(ROOT, "config"); OUT = os.path.join(ROOT, "data")
UA = {"User-Agent": "Mozilla/5.0 (risk-feed collector)"}
NOW = datetime.now(timezone.utc)
MAX_ITEMS, MAX_AGE_H = 800, 72

def lines(name):
    p = os.path.join(CFG, name)
    if not os.path.exists(p): return []
    return [l.strip() for l in open(p, encoding="utf-8") if l.strip() and not l.startswith("#")]

def get(url, headers=None, timeout=20):
    req = urllib.request.Request(url, headers={**UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")

KEYWORDS = [k.lower() for k in lines("keywords.txt")]
EMOJIS = lines("emojis.txt")

def score(text):
    t = (text or "").lower()
    kw = [k for k in KEYWORDS if k in t]
    em = [e for e in EMOJIS if e in (text or "")]
    return kw, em

def item(src, kind, id_, text, url, ts, extra=None):
    kw, em = score(text)
    d = {"id": f"{kind}:{id_}", "kind": kind, "src": src, "text": (text or "")[:600], "url": url,
         "time": ts, "keywords": kw, "emojis": em, "alert": bool(kw or em)}
    if extra: d.update(extra)
    return d

# ---------- ADS-B military aircraft ----------
def adsb():
    out = []
    lat0, lat1, lon0, lon1 = 12, 40, 30, 62
    try:
        j = json.loads(get("https://api.adsb.lol/v2/mil"))
        ts = datetime.fromtimestamp(j.get("now", time.time() * 1000) / 1000, timezone.utc).isoformat()
        for a in j.get("ac", []):
            lat, lon = a.get("lat"), a.get("lon")
            if lat is None or lon is None or not (lat0 <= lat <= lat1 and lon0 <= lon <= lon1): continue
            out.append({"hex": a.get("hex"), "cs": (a.get("flight") or "").strip(), "type": a.get("t"),
                        "lat": lat, "lon": lon, "alt": a.get("alt_baro"), "time": ts})
    except Exception as e:
        print("adsb error", e)
    return out

# ---------- Telegram public previews ----------
MSG = re.compile(r'data-post="([^"]+)".*?(?:tgme_widget_message_text[^>]*>(.*?)</div>)?.*?<time[^>]*datetime="([^"]+)"', re.S)
def strip(h): return html.unescape(re.sub(r"<br\s*/?>", "\n", re.sub(r"<(?!br)[^>]+>", "", h or ""))).strip()
def telegram():
    out = []
    for ch in lines("telegram.txt"):
        try:
            page = get(f"https://t.me/s/{ch}")
            for block in page.split('tgme_widget_message_wrap')[1:][-15:]:
                post = re.search(r'data-post="([^"]+)"', block)
                ts = re.search(r'<time[^>]*datetime="([^"]+)"', block)
                body = re.search(r'tgme_widget_message_text[^>]*>(.*?)</div>', block, re.S)
                txt = strip(body.group(1)) if body else ""
                if not (post and txt): continue
                out.append(item(ch, "tg", post.group(1), txt, f"https://t.me/{post.group(1)}", ts.group(1) if ts else NOW.isoformat()))
        except Exception as e:
            print("tg error", ch, e)
        time.sleep(0.7)
    return out

# ---------- RSS / Google News ----------
def rss():
    out = []
    for url in lines("rss.txt"):
        try:
            root = ET.fromstring(get(url).encode("utf-8"))
            for it in root.iter("item"):
                title = (it.findtext("title") or "").strip()
                link = (it.findtext("link") or "").strip()
                desc = strip(it.findtext("description") or "")
                pub = it.findtext("pubDate") or ""
                try: ts = datetime.strptime(pub[:25].strip(), "%a, %d %b %Y %H:%M:%S").replace(tzinfo=timezone.utc).isoformat()
                except Exception: ts = NOW.isoformat()
                src = urllib.parse.urlparse(url).netloc
                out.append(item(src, "rss", link or title, f"{title} — {desc[:300]}", link, ts))
        except Exception as e:
            print("rss error", url, e)
    return out

# ---------- X (only with a paid API key in the X_BEARER_TOKEN secret) ----------
def x_accounts(state):
    token = os.environ.get("X_BEARER_TOKEN")
    if not token: return []
    H = {"Authorization": f"Bearer {token}"}
    accts = lines("x_accounts.txt"); ids = state.setdefault("x_ids", {})
    missing = [a for a in accts if a not in ids]
    for i in range(0, len(missing), 100):
        try:
            j = json.loads(get("https://api.x.com/2/users/by?usernames=" + ",".join(missing[i:i+100]), H))
            for u in j.get("data", []): ids[u["username"]] = u["id"]
        except Exception as e: print("x lookup error", e)
    batch = int(os.environ.get("X_PER_RUN", "25"))           # rotate through the list to respect rate limits
    start = state.get("x_cursor", 0) % max(1, len(accts)); sel = (accts + accts)[start:start + batch]
    state["x_cursor"] = start + batch
    since = (NOW - timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%SZ")
    out = []
    for name in sel:
        uid = ids.get(name)
        if not uid: continue
        try:
            j = json.loads(get(f"https://api.x.com/2/users/{uid}/tweets?max_results=5&start_time={since}&tweet.fields=created_at", H))
            for t in j.get("data", []):
                out.append(item(name, "x", t["id"], t["text"], f"https://x.com/{name}/status/{t['id']}", t.get("created_at", NOW.isoformat())))
        except Exception as e: print("x error", name, e)
    return out

def main():
    os.makedirs(OUT, exist_ok=True)
    fp, sp = os.path.join(OUT, "feed.json"), os.path.join(OUT, "state.json")
    feed = json.load(open(fp, encoding="utf-8")) if os.path.exists(fp) else {"items": []}
    state = json.load(open(sp, encoding="utf-8")) if os.path.exists(sp) else {}
    new = telegram() + rss() + x_accounts(state)
    seen = {i["id"]: i for i in feed["items"]}
    added = 0
    for i in new:
        if i["id"] not in seen:
            i["collected"] = NOW.isoformat(); seen[i["id"]] = i; added += 1
    cutoff = (NOW - timedelta(hours=MAX_AGE_H)).isoformat()
    items = sorted((i for i in seen.values() if i.get("collected", i["time"]) >= cutoff), key=lambda i: i["time"], reverse=True)[:MAX_ITEMS]
    out = {"updated": NOW.isoformat(), "aircraft": adsb(), "items": items,
           "counts": {"telegram_channels": len(lines("telegram.txt")), "rss_feeds": len(lines("rss.txt")),
                      "x_accounts": len(lines("x_accounts.txt")), "x_enabled": bool(os.environ.get("X_BEARER_TOKEN"))}}
    json.dump(out, open(fp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump({"updated": out["updated"], "alerts": [i for i in items if i["alert"]][:200]},
              open(os.path.join(OUT, "alerts.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(state, open(sp, "w", encoding="utf-8"))
    print(f"added {added}, total {len(items)}, aircraft {len(out['aircraft'])}")

if __name__ == "__main__":
    main()
