import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path):
    # Keeps the API key out of shell history and chat logs. Real environment variables win.
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition("=")
        if sep and not line.lstrip().startswith("#"):
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


_load_dotenv(ROOT / ".env")
DATA_DIR = Path(os.getenv("FINN_DATA_DIR", ROOT / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "finn.db"

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Two tiers. Bulk extraction goes to FAST, anything that has to weigh evidence goes to SMART.
# Override with env vars when Google renames things.
# The 2.5 models are closed to new API keys as of Nov 2026, and 3.5-flash's free daily quota ran out
# within one day of research runs, so SMART uses 3.8-flash (the model Google's 404 recommended).
MODEL_FAST = os.getenv("FINN_MODEL_FAST", "gemini-3.5-flash-lite")
MODEL_SMART = os.getenv("FINN_MODEL_SMART", "gemini-3.8-flash")

# USD per 1M tokens (input, output) - only used to show what the free-tier usage would have cost.
# Paid-tier list prices from ai.google.dev/gemini-api/docs/pricing, checked 11 Nov 2026. The flash models
# had no listed price that day, so their calls are counted but not priced rather than guessed at.
PRICES = {
    "gemini-3.5-flash-lite": (0.30, 2.50),
}

# Set this to get real phone notifications through ntfy.sh (free, no account).
NTFY_TOPIC = os.getenv("FINN_NTFY_TOPIC", "")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)
