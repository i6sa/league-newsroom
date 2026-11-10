"""One-off cleanup: delete the bot's repeated injury posts from the last few hours.

A repeat is a post whose title (player + new status) the bot already posted earlier in the
window, e.g. a second "Joshua Palmer · WR → Out". The first one of each is kept.
"""

from datetime import datetime, timedelta, timezone

DISCORD_EPOCH_MS = 1420070400000


def _sent_at(message_id: str) -> datetime:
    return datetime.fromtimestamp(((int(message_id) >> 22) + DISCORD_EPOCH_MS) / 1000, timezone.utc)


def repeats(messages: list[dict], bot_id: str) -> list[dict]:
    """The bot's posts whose title already appeared in an earlier post (oldest first wins)."""
    seen, out = set(), []
    for m in sorted(messages, key=lambda m: int(m["id"])):
        if (m.get("author") or {}).get("id") != bot_id or not m.get("embeds"):
            continue
        title = m["embeds"][0].get("title", "")
        if not title:
            continue
        if title in seen:
            out.append(m)
        else:
            seen.add(title)
    return out


def run(bot, channel_id: str, hours: float, dry_run: bool) -> list[str]:
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    me = bot.me()["id"]
    messages, before = [], None
    while True:
        page = bot.messages(channel_id, before)
        if not page:
            break
        messages += [m for m in page if _sent_at(m["id"]) >= since]
        if _sent_at(page[-1]["id"]) < since or len(page) < 100:
            break
        before = page[-1]["id"]
    dupes = repeats(messages, me)
    notes = [f"cleanup: {len(messages)} posts in the last {hours:g} hours, {len(dupes)} repeats"]
    for m in dupes:
        notes.append(f"  {'would delete' if dry_run else 'deleted'}: {m['embeds'][0]['title']} "
                     f"({_sent_at(m['id']):%H:%M} UTC)")
        if not dry_run:
            bot.delete(channel_id, m["id"])
    return notes
