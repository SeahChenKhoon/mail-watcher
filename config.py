"""
Configuration for check_mail.py.

Secrets are NOT stored in this file. They come from environment variables:
  - locally: put them in a git-ignored file called `mail-watcher.env` (see .env.example)
  - on GitHub Actions: store them as repository Secrets (Settings > Secrets and variables > Actions)
"""
import os
from pathlib import Path


_ENV_FILES_FOUND: list = []


def _load_dotenv(path: Path) -> None:
    """Tiny .env loader (no extra dependency). Real env vars win over .env."""
    if not path.exists():
        return
    _ENV_FILES_FOUND.append(path.name)
    # utf-8-sig strips the BOM that Windows Notepad adds, which would corrupt the first key
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


for _name in ("mail-watcher.env", ".env"):     # first file found wins; real env vars always win
    _load_dotenv(Path(__file__).parent / _name)


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        here = Path(__file__).parent
        found = ", ".join(_ENV_FILES_FOUND) or "none"
        raise RuntimeError(
            f"Missing required setting: {name}. "
            f"Looked in folder: {here} | env files found: {found}. "
            f"Expected a file named exactly 'mail-watcher.env' (or '.env') there, "
            f"containing a line {name}=<value> with a non-empty value. "
            f"(On GitHub Actions, set it as a repository Secret instead.)"
        )
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
]

# Senders from these domains are ignored, even if they also match WATCH_DOMAINS.
# Same rule as above: matches the domain itself and any subdomain of it.
EXCLUDE_DOMAINS = [
    "notify.gov.sg",
    "crowdtask.gov.sg",
]

MAX_SENDERS_IN_MESSAGE = 5     # extra ones are summarised as "+N more"
MAX_MESSAGE_CHARS = 600         # well under Telegram's 4096-char limit

STATE_FILE = Path(__file__).parent / "state.json"


# ---- Secrets (read lazily so importing this file never leaks them) ----------

def yahoo_user() -> str:
    return os.environ.get("YAHOO_USER", "chenkhoon@yahoo.com").strip()


def yahoo_app_password() -> str:
    return _required("YAHOO_APP_PASSWORD")


def telegram_token() -> str:
    """Bot token from @BotFather, e.g. 123456789:AAF..."""
    return _required("TELEGRAM_BOT_TOKEN")


def telegram_chat_id() -> str:
    """Your numeric chat id (from https://api.telegram.org/bot<TOKEN>/getUpdates)."""
    return _required("TELEGRAM_CHAT_ID")