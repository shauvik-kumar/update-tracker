import json, os, smtplib
import httpx
from bs4 import BeautifulSoup
from email.mime.text import MIMEText
from datetime import datetime
from urllib.parse import urlparse, urlunparse

STATE_FILE = "tracker/state.json"
LOG_FILE   = "tracker/updates_log.json"
SOURCES    = json.load(open("tracker/sources.json"))

def load(path, default):
    try:
        return json.load(open(path))
    except:
        return default

def save(path, data):
    json.dump(data, open(path, "w"), indent=2)

def clean_url(raw, fallback_base):
    """
    Normalize URLs so ?utm=… or anchors don't trigger false 'new' links.
    """
    if not raw:
        return fallback_base
    if raw.startswith("/"):
        parsed_base = urlparse(fallback_base)
        raw = f"{parsed_base.scheme}://{parsed_base.netloc}{raw}"
    p = urlparse(raw)
    # drop query and fragment
    p = p._replace(query="", fragment="")
    return urlunparse(p)

def send_email(subject, body):
    msg = MIMEText(body, "html")
    msg["Subject"] = subject
    msg["From"]    = os.environ["GMAIL_USER"]
    msg["To"]      = os.environ["NOTIFY_EMAIL"]
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(os.environ["GMAIL_USER"], os.environ["GMAIL_APP_PASSWORD"])
        s.send_message(msg)

def alert(log, source_name, title, link):
    log.insert(0, {
        "source": source_name,
        "title": title,
        "link": link,
        "detected_at": datetime.utcnow().isoformat()
    })
    send_email(
        f"🔔 NEW UPDATE: {source_name}",
        f"<h1>{title}</h1><p><a href='{link}'>{link}</a></p>"
    )
    print(f"[ALERT] {source_name} -> {title} | {link}")

def check_html(source, state, log):
    resp = httpx.get(
        source["url"],
        timeout=20,
        follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0"}
    )
    soup = BeautifulSoup(resp.text, "html.parser")
    el = soup.select_one(source["selector"])
    if not el:
        print(f"[WARN] No element found for {source['name']}")
        return

    title = el.get_text(strip=True)

    # Figure out link element and clean URL
    link_el = None
    if source.get("link_selector"):
        link_el = soup.select_one(source["link_selector"])
    if not link_el:
        link_el = el

    raw_link = link_el.get(source.get("link_attr", "href"), source["url"])
    link = clean_url(raw_link, source["url"])

    key = f"{title}||{link}"  # composite key for stability
    last_key = state.get(source["name"])

    print(f"[DEBUG] {source['name']} -> title='{title}' link='{link}'")
    if last_key == key:
        # no real change
        return

    # update state and send alert once
    state[source["name"]] = key
    alert(log, source["name"], title, link)

state = load(STATE_FILE, {})
log   = load(LOG_FILE, [])

for src in SOURCES:
    try:
        check_html(src, state, log)
    except Exception as e:
        print(f"[ERROR] {src['name']}: {e}")

save(STATE_FILE, state)
save(LOG_FILE, log[:100])

print("✅ Check complete")
