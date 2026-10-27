"""
Check Yahoo Mail for new messages from watched domains and send a Telegram
alert via the Telegram Bot API.

Designed to be run repeatedly (e.g. every 10 min from GitHub Actions).
"Since the last run" is tracked with the IMAP UID of the last message seen,
stored in state.json.
"""
import base64
import email
import imaplib
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from email.header import decode_header, make_header
from email.utils import parseaddr

import config


# ---------------------------------------------------------------- state ------

def load_state() -> dict:
    if config.STATE_FILE.exists():
        try:
            return json.loads(config.STATE_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {}


def save_state(uidvalidity: int, last_uid: int) -> None:
    config.STATE_FILE.write_text(
        json.dumps({"uidvalidity": uidvalidity, "last_uid": last_uid}, indent=2) + "\n",
        encoding="utf-8",
    )


# ------------------------------------------------------------- matching ------

def _in_domains(domain: str, domains: list) -> bool:
    return any(domain == d or domain.endswith("." + d) for d in domains)


def domain_matches(address: str) -> bool:
    if "@" not in address:
        return False
    domain = address.rsplit("@", 1)[1].lower().strip(">").strip()
    if _in_domains(domain, config.EXCLUDE_DOMAINS):    # exclusion always wins
        return False
    return _in_domains(domain, config.WATCH_DOMAINS)


def decode(value: str) -> str:
    try:
        return str(make_header(decode_header(value or "")))
    except Exception:
        return value or ""


# ----------------------------------------------------------------- IMAP ------

def fetch_new(conn: imaplib.IMAP4_SSL, last_uid: int):
    """Return (matches, max_uid_seen) for UIDs greater than last_uid."""
    typ, data = conn.uid("SEARCH", None, f"UID {last_uid + 1}:*")
    if typ != "OK":
        raise RuntimeError("IMAP SEARCH failed")
    # IMAP returns the highest message even when it is <= last_uid, so filter.
    uids = [int(u) for u in data[0].split() if int(u) > last_uid]
    matches, max_uid = [], last_uid
    for uid in uids:
        typ, msg_data = conn.uid("FETCH", str(uid), "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT)])")
        max_uid = max(max_uid, uid)
        if typ != "OK" or not msg_data or not isinstance(msg_data[0], tuple):
            continue
        msg = email.message_from_bytes(msg_data[0][1])
        name, addr = parseaddr(decode(msg.get("From", "")))
        if domain_matches(addr):
            matches.append({"uid": uid, "from": addr, "name": name, "subject": decode(msg.get("Subject", ""))})
    return matches, max_uid


# -------------------------------------------------------------- Telegram ------

def clean(text: str, limit: int) -> str:
    """Collapse all whitespace (newlines, tabs, repeated spaces) to single spaces.

    Keeps the alert on one tidy line.
    """
    text = re.sub(r"\s+", " ", text).strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def build_message(matches: list) -> str:
    """Single-line alert text."""
    shown = matches[: config.MAX_SENDERS_IN_MESSAGE]
    items = [f"{clean(m['name'] or m['from'], 40)} - {clean(m['subject'], 80)}" for m in shown]
    text = f"{len(matches)} new: " + " | ".join(items)
    if len(matches) > len(shown):
        text += f" | +{len(matches) - len(shown)} more"
    return clean(text, config.MAX_MESSAGE_CHARS)


def send_alert(text: str) -> None:
    token, chat_id = config.telegram_token(), config.telegram_chat_id()
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode("utf-8")

    last_err = "unknown error"
    for attempt in (1, 2):
        req = urllib.request.Request(url, data=payload, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                if resp.status == 200:
                    return      # Telegram accepted it (delivery is near-instant)
                last_err = f"HTTP {resp.status}"
        except urllib.error.HTTPError as e:
            last_err = f"HTTP {e.code}"
            if e.code < 500:    # 4xx = bad token / chat id (or you never messaged the bot): retry won't help
                break
        except urllib.error.URLError as e:
            last_err = f"network error: {e.reason}"
        if attempt == 1:
            time.sleep(5)
    raise RuntimeError(f"Telegram send failed ({last_err})")


# ----------------------------------------------------------------- main ------

def main() -> int:
    conn = imaplib.IMAP4_SSL(config.IMAP_HOST, config.IMAP_PORT)
    try:
        conn.login(config.yahoo_user(), config.yahoo_app_password())
        conn.select(config.MAILBOX, readonly=True)

        uidvalidity = int(conn.response("UIDVALIDITY")[1][0])
        state = load_state()

        # First run, or mailbox UIDs were reset: set a baseline, do not alert.
        if state.get("uidvalidity") != uidvalidity or "last_uid" not in state:
            typ, data = conn.uid("SEARCH", None, "ALL")
            ids = data[0].split()
            baseline = int(ids[-1]) if ids else 0
            save_state(uidvalidity, baseline)
            print(f"Baseline set at UID {baseline}. No alerts on first run.")
            return 0

        matches, max_uid = fetch_new(conn, state["last_uid"])
    finally:
        try:
            conn.logout()
        except Exception:
            pass

    if matches:
        send_alert(build_message(matches))   # if this raises, state is NOT advanced -> retried next run
        print(f"Telegram alert sent for {len(matches)} email(s).")
    else:
        print("No new mail from watched domains.")

    save_state(uidvalidity, max_uid)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # keep secrets out of tracebacks
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)