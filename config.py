import os

API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
WORKERS = int(os.environ.get("WORKERS", "5"))

DB_URI = os.environ.get("DB_URI", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "filestore")

# Private channel where files are stored (bot must be admin). Looks like -100123...
DB_CHANNEL = int(os.environ.get("DB_CHANNEL", "0"))

# Comma-separated Telegram user IDs allowed to upload / make links
ADMINS = [int(x) for x in os.environ.get("ADMINS", "").split(",") if x.strip()]

AUTO_DEL = int(os.environ.get("AUTO_DEL", "300"))  # seconds, 0 = off
PROTECT = os.environ.get("PROTECT", "true").lower() == "true"  # block forwarding
