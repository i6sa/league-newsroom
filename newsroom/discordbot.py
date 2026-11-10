"""The few Discord calls the newsroom needs, made with the bot token."""

import time

import requests

API = "https://discord.com/api/v10"
SEND_MESSAGES = 1 << 11
BOT_CAN = (1 << 10) | (1 << 11) | (1 << 14) | (1 << 16)  # view, send, embed links, read history


class BotClient:
    def __init__(self, token: str):
        self.headers = {
            "Authorization": f"Bot {token}",
            "User-Agent": "DiscordBot (https://github.com/i6sa/league-newsroom, 1.0)",
        }

    def _request(self, method: str, path: str, payload=None, params=None, missing_ok=False):
        for _ in range(5):
            resp = requests.request(method, API + path, headers=self.headers, json=payload,
                                    params=params, timeout=20)
            if resp.status_code == 429:
                time.sleep(float(resp.json().get("retry_after", 2)) + 0.25)
                continue
            if missing_ok and resp.status_code in (403, 404):
                return None
            if resp.status_code >= 400:
                raise RuntimeError(f"Discord {method} {path.split('?')[0]} failed: "
                                   f"{resp.status_code} {resp.text[:300]}")
            time.sleep(0.4)
            return resp.json() if resp.content else {}
        raise RuntimeError("Discord kept rate-limiting the bot")

    def post_embed(self, channel_id: str, embed: dict, content: str = "") -> str:
        """One ready-made embed, never pinging anyone."""
        payload = {"embeds": [embed], "allowed_mentions": {"parse": []}, **({"content": content} if content else {})}
        return self._request("POST", f"/channels/{channel_id}/messages", payload)["id"]

    def messages(self, channel_id: str, before: str | None = None) -> list[dict]:
        """Up to 100 messages, newest first."""
        params = {"limit": 100, **({"before": before} if before else {})}
        return self._request("GET", f"/channels/{channel_id}/messages", params=params) or []

    def delete(self, channel_id: str, message_id: str) -> None:
        self._request("DELETE", f"/channels/{channel_id}/messages/{message_id}", missing_ok=True)

    def me(self) -> dict:
        return self._request("GET", "/users/@me")

    def guilds(self) -> list[dict]:
        return self._request("GET", "/users/@me/guilds")

    def guild_channels(self, guild_id: str) -> list[dict]:
        return self._request("GET", f"/guilds/{guild_id}/channels")

    def make_read_only(self, channel: dict, bot_id: str) -> bool:
        """Members can read and react but not post; the bot can post. Keeps other permission settings."""
        current = {o["id"]: o for o in channel.get("permission_overwrites", [])}
        changed = False
        for target, kind, allow_bits, deny_bits in ((bot_id, 1, BOT_CAN, 0), (channel["guild_id"], 0, 0, SEND_MESSAGES)):
            o = current.get(target, {"allow": "0", "deny": "0"})
            allow, deny = int(o["allow"]), int(o["deny"])
            new_allow, new_deny = (allow | allow_bits) & ~deny_bits, (deny | deny_bits) & ~allow_bits
            if (new_allow, new_deny) != (allow, deny):
                self._request("PUT", f"/channels/{channel['id']}/permissions/{target}",
                              {"type": kind, "allow": str(new_allow), "deny": str(new_deny)})
                changed = True
        return changed
