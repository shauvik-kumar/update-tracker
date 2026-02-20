import json, os, smtplib, feedparser
import httpx
from bs4 import BeautifulSoup
from email.mime.text import MIMEText
from datetime import datetime

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
    print(f"ALERT: {source_name} - {title}")

def check_html(source, state, log):
    resp = httpx.get(
        source["url"],
        timeout=15,
        follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0"}
    )
    soup = BeautifulSoup(resp.text, "html.parser")
    el = soup.select_one(source["selector"])
    if not el:
        print(f"No element found for {source['name']}")
        return

    title = el.get_text(strip=True)

    # If same as last time, nothing to do
    if state.get(source["name"]) == title:
        return

    state[source["name"]] = title

    # Figure out link
    link_el = soup.select_one(source.get("link_selector", "")) if source.get("link_selector") else el
    link = link_el.get("href", source["url"]) if link_el else source["url"]
    if link.startswith("/"):
        link = source["url"].rstrip("/") + link

    alert(log, source["name"], title, link)

state = load(STATE_FILE, {})
log   = load(LOG_FILE, [])

for src in SOURCES:
    try:
        check_html(src, state, log)
    except Exception as e:
        print(f"Error [{src['name']}]: {e}")

save(STATE_FILE, state)
save(LOG_FILE, log[:100])

print("✅ Check complete")
