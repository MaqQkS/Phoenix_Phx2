"""Static check: no real Discord webhook URLs in source or test files.

The Discord webhook URL is treated as a secret. This test scans the dispatch
and adapter trees for any string that looks like a real Discord webhook URL
(``discord.com/api/webhooks/<id>/<token>`` or its ``discordapp.com``
variant). Test fixtures and code must use a non-routable placeholder such as
``https://example.invalid/webhook``.
"""

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]

WEBHOOK_PATTERN = re.compile(r"discord(?:app)?\.com/api/webhooks/\d+/[A-Za-z0-9_-]+")

SCAN_DIRECTORIES = [
    REPO_ROOT / "PHX2" / "dispatch",
    REPO_ROOT / "PHX2" / "renderers" / "adapters",
    REPO_ROOT / "PHX2" / "tests" / "dispatch",
    REPO_ROOT / "PHX2" / "tests" / "renderers",
]

ALLOWED_PLACEHOLDERS = {
    "https://example.invalid/webhook",
    "https://discord.example/webhook",
}


def test_no_real_discord_webhook_urls_in_source():
    matches = []
    for directory in SCAN_DIRECTORIES:
        if not directory.exists():
            continue
        for path in directory.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for match in WEBHOOK_PATTERN.finditer(text):
                if match.group(0) not in ALLOWED_PLACEHOLDERS:
                    matches.append(f"{path}: {match.group(0)}")
    assert not matches, "Real Discord webhook URLs found:\n" + "\n".join(matches)
