"""
Configuration for check_mail.py.

Secrets are NOT stored in this file. They come from environment variables:
  - locally: put them in a git-ignored file called `.env` (see .env.example)
  - on GitHub Actions: store them as repository Secrets (Settings > Secrets and variables > Actions)
"""
import os
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    """Tiny .env loader (no extra dependency). Real env vars win over .env."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(Path(__file__).parent / ".env")


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required setting: {name} (set it in .env or as a GitHub Secret)")
    return value


# ---- Non-secret settings (safe to commit) -----------------------------------

IMAP_HOST = "imap.mail.yahoo.com"
IMAP_PORT = 993
MAILBOX = "INBOX"

# A sender matches if its domain equals one of these, or is a subdomain of one.
# "gov.sg" therefore matches moe.gov.sg, mom.gov.sg, etc.
# Confirm the LIVO domain; change it here if their real domain differs.
WATCH_DOMAINS = [
    "livo.com",
    "gov.sg",
    "smfccl.sg",
    "smfederation.org.sg",
    "healthhub.sg",
]

# Senders from these domains are ignored, even if they also match WATCH_DOMAINS.
# Same rule as above: matches the domain itself and any subdomain of it.
EXCLUDE_DOMAINS = [
    "notify.gov.sg",
]

MAX_SENDERS_IN_MESSAGE = 5      # extra ones are summarised as "+N more"
MAX_MESSAGE_CHARS = 600         # keeps the template variable well under WhatsApp's limit

STATE_FILE = Path(__file__).parent / "state.json"


# ---- Secrets (read lazily so importing this file never leaks them) ----------

def yahoo_user() -> str:
    return os.environ.get("YAHOO_USER", "chenkhoon@yahoo.com").strip()


def yahoo_app_password() -> str:
    return _required("YAHOO_APP_PASSWORD")


def twilio_sid() -> str:
    return _required("TWILIO_ACCOUNT_SID")


def twilio_token() -> str:
    return _required("TWILIO_AUTH_TOKEN")


def twilio_whatsapp_from() -> str:
    """Your Twilio WhatsApp sender in E.164, e.g. +14155238886 (the shared sandbox number)."""
    return _required("TWILIO_WHATSAPP_FROM")


def whatsapp_to() -> str:
    """Your own WhatsApp number in E.164, e.g. +6597868397."""
    number = _required("WHATSAPP_TO").replace(" ", "")
    return number if number.startswith("+") else "+" + number


def twilio_content_sid() -> str:
    """SID (starts with HX) of your approved Content Template. Empty = send freeform text instead.

    Freeform only works inside the 24-hour window after you last messaged the sender,
    which is fine for testing in the sandbox but not for real alerts.
    """
    return os.environ.get("TWILIO_CONTENT_SID", "").strip()