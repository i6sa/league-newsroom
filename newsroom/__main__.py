"""📺 NFL Newsroom: real NFL headlines, injuries and trades from ESPN, posted to Discord.

    python -m newsroom            # post anything new
    python -m newsroom --dry-run  # print what would be posted
"""

import argparse
import json
import os
import sys
from pathlib import Path

from . import wire
from .discordbot import BotClient

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "data" / "state.json"
CHANNELS = json.loads((ROOT / "channels.json").read_text())


def norm(name: str) -> str:
    return "".join(ch for ch in name.lower() if ch.isalnum())


class Config:
    def __init__(self, channels: dict):
        self.channels = channels


class Router:
    """Finds the newsroom channels by name in the bot's server (emoji, symbols and case ignored)."""

    def __init__(self, bot):
        self.bot, self.objects, self._found = bot, {}, None

    def _channels(self) -> dict:
        if self._found is None:
            self._found = {}
            for guild in self.bot.guilds():
                for c in self.bot.guild_channels(guild["id"]):
                    if c.get("type") in (0, 5):  # text and announcement channels
                        self._found.setdefault(norm(c["name"]), (c["id"], c["name"]))
                        self.objects[c["id"]] = c
        return self._found

    def target(self, key: str):
        name = CHANNELS.get(key)
        return self._channels().get(norm(name)) if name else None


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    token = os.environ.get("DISCORD_BOT_TOKEN", "").strip()
    if not token:
        print("Add the DISCORD_BOT_TOKEN secret to this repo first (Settings → Secrets and variables → Actions).")
        return 1
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    before = json.dumps(state, sort_keys=True)
    for line in wire.run(Config(CHANNELS), Router(BotClient(token)), state, args.dry_run):
        print(line)
    if not args.dry_run and json.dumps(state, sort_keys=True) != before:
        STATE.parent.mkdir(exist_ok=True)
        STATE.write_text(json.dumps(state, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
