import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("FINN_DATA_DIR", ROOT / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "finn.db"

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Two tiers. Bulk extraction goes to FAST, anything that has to weigh evidence goes to SMART.
# Override with env vars when Google renames things.
MODEL_FAST = os.getenv("FINN_MODEL_FAST", "gemini-2.5-flash-lite")
MODEL_SMART = os.getenv("FINN_MODEL_SMART", "gemini-2.5-flash")

# USD per 1M tokens (input, output) - only used to show what the free-tier usage would have cost.
PRICES = {
    MODEL_FAST: (0.10, 0.40),
    MODEL_SMART: (0.30, 2.50),
}

# Set this to get real phone notifications through ntfy.sh (free, no account).
NTFY_TOPIC = os.getenv("FINN_NTFY_TOPIC", "")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)
