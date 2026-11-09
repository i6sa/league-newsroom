"""📺 NFL Newsroom: real NFL news in the Discord, styled in each team's colors.

- #headlines: ESPN's breaking NFL headlines (headline, one-line summary, link, photo).
- #injury-report: every NFL QB/RB/WR/TE/K whose injury status changes (Questionable → Out,
  placed on IR, back to practice...). Whole NFL, and it never pings or mentions anyone's
  fantasy team, so nobody in the league gets a heads-up the others don't.
- #nfl-trades: every real NFL trade, both teams' sides merged into one post.

Runs with the 30-minute trade check during the season and every 6 hours in the off-season.
Each post's side bar is the team's color (its second color when the first is close to black)
with the team's logo. Everything comes from ESPN's public NFL feeds.
"""

import re
from datetime import datetime, timedelta, timezone

import requests

SITE = "https://site.api.espn.com/apis/site/v2/sports/football/nfl"
NFL_BLUE = 0x013369
POSITIONS = {"QB", "RB", "WR", "TE", "K", "PK"}
BACKFILL_HOURS = 12         # first run: injury changes from the last 12 hours (at most 10)
BACKFILL_NEWS = 5           # first run: the latest 5 headlines
MAX_PER_RUN = 25            # never flood a channel in one go
FLICKER_HOURS = 12          # ESPN's injury feed sometimes drops a player for a minute; remember them this long
TRADE = re.compile(r"\b(acquired|traded)\b", re.I)


# ------------------------------------------------------------------ ESPN

def _get(path: str, **params) -> dict:
    resp = requests.get(f"{SITE}/{path}", params=params, timeout=20)
    resp.raise_for_status()
    return resp.json()


def _hex(value: str | None) -> int | None:
    try:
        return int(value, 16) if value else None
    except ValueError:
        return None


def _dark(color: int) -> bool:
    """Too dark to see on Discord's dark background (black, deep navy)."""
    return max((color >> 16) & 255, (color >> 8) & 255, color & 255) < 60


def teams() -> dict:
    """ESPN team id / abbreviation / names -> display name, color and logo."""
    out = {}
    for wrap in _get("teams")["sports"][0]["leagues"][0]["teams"]:
        t = wrap["team"]
        color, alt = _hex(t.get("color")), _hex(t.get("alternateColor"))
        if color is None or (_dark(color) and alt is not None and not _dark(alt)):
            color = alt if alt is not None else NFL_BLUE
        info = {"id": str(t["id"]), "abbr": t.get("abbreviation", ""), "name": t.get("displayName", ""),
                "short": t.get("shortDisplayName") or t.get("name", ""), "city": t.get("location", ""),
                "color": color, "logo": (t.get("logos") or [{}])[0].get("href")}
        for key in (info["id"], info["abbr"], info["name"]):
            out[key] = info
    return out


def _when(stamp: str | None) -> datetime | None:
    if not stamp:
        return None
    try:
        return datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return None


def _embed(team: dict | None, **fields) -> dict:
    embed = {"color": team["color"] if team else NFL_BLUE, **{k: v for k, v in fields.items() if v}}
    if team and "author" not in embed:
        embed["author"] = {"name": team["name"], **({"icon_url": team["logo"]} if team.get("logo") else {})}
    return embed


# ------------------------------------------------------------------ headlines

def _key(article: dict) -> str:
    return str(article.get("id") or article.get("headline"))


def headlines(all_teams: dict, seen: set, first_run: bool) -> tuple[list[tuple[str, dict]], list[str]]:
    """(posts, every headline key now in the feed)."""
    articles = [a for a in _get("news", limit=50).get("articles", []) if a.get("type") == "HeadlineNews"]
    articles.sort(key=lambda a: a.get("published", ""))
    new = [a for a in articles if _key(a) not in seen]
    if first_run:
        new = new[-BACKFILL_NEWS:]
    out = []
    for a in new[-MAX_PER_RUN:]:
        team = next((all_teams.get(str(c.get("teamId"))) for c in a.get("categories", [])
                     if c.get("type") == "team" and str(c.get("teamId")) in all_teams), None)
        image = next((i.get("url") for i in a.get("images", []) if i.get("url")), None)
        link = (a.get("links", {}).get("web") or {}).get("href")
        out.append((_key(a),
                    _embed(team, title=a.get("headline", "")[:256], url=link, description=(a.get("description") or "")[:600],
                           image={"url": image} if image else None, footer={"text": "ESPN"}, timestamp=a.get("published"))))
    return out, [_key(a) for a in articles]


# ------------------------------------------------------------------ injuries

NOT_INJURIES = {"coach's decision", "coaches decision", "personal", "not injury related", "rest"}
STATUS_EMOJI = {"questionable": "🟡", "doubtful": "🟠", "out": "🔴", "injured reserve": "🚑", "suspension": "⛔",
                "physically unable to perform": "🚑", "day-to-day": "🟡"}


def _status_line(prev: str | None, now: str) -> str:
    return f"{prev} → {now}" if prev and prev != now else now


def injuries(all_teams: dict, known: dict, first_run: bool, gone: dict | None = None):
    """(posts, updated statuses, recently missing). known: athlete id -> last status seen.

    gone: athlete id -> [last status, when they dropped out of the feed]. ESPN's feed flickers
    (a player can vanish for a minute and come back), so a player who reappears within
    FLICKER_HOURS keeps his old status instead of being posted again as a new injury."""
    now = datetime.now(timezone.utc)
    current, out = {}, []
    gone = dict(gone or {})

    def missing_for(pid):
        since = _when(gone[pid][1]) if pid in gone else None
        return now - since if since else None
    for team_block in _get("injuries").get("injuries", []):
        team = all_teams.get(str(team_block.get("id"))) or all_teams.get(team_block.get("displayName", ""))
        for inj in team_block.get("injuries", []):
            ath = inj.get("athlete") or {}
            pos = (ath.get("position") or {}).get("abbreviation")
            pid = str(ath.get("id") or ath.get("displayName"))
            status = inj.get("status") or ""
            if pos not in POSITIONS or not status:
                continue
            reason = ((inj.get("details") or {}).get("type") or "").lower()
            if reason in NOT_INJURIES:
                continue                            # healthy scratches and the like aren't injuries
            current[pid] = status
            prev = known.get(pid)
            if prev is None and pid in gone and (missing_for(pid) or timedelta(days=99)) <= timedelta(hours=FLICKER_HOURS):
                prev = gone[pid][0]                 # it was only a flicker
            when = _when(inj.get("date"))
            if status == "Active":
                if prev and prev != "Active":      # was hurt, now back
                    out.append((when, pid, _injury_embed(team, ath, pos, inj, prev, back=True)))
                continue
            if prev == status:
                continue
            if first_run and not (when and now - when <= timedelta(hours=BACKFILL_HOURS)):
                continue                            # first run only shows the last few hours
            if not first_run and prev is None and when and now - when > timedelta(days=3):
                continue                            # an old listing we just hadn't seen yet
            out.append((when, pid, _injury_embed(team, ath, pos, inj, prev)))
    out.sort(key=lambda r: r[0] or now)
    cap = 10 if first_run else MAX_PER_RUN
    stamp = now.strftime("%Y-%m-%dT%H:%MZ")
    for pid, status in known.items():
        if pid not in current:
            gone.setdefault(pid, [status, stamp])
    for pid in list(gone):
        if pid in current or (missing_for(pid) or timedelta(days=99)) > timedelta(hours=FLICKER_HOURS):
            del gone[pid]
    return [(pid, embed) for _, pid, embed in out[-cap:]], current, gone


def _injury_embed(team, ath, pos, inj, prev, back=False) -> dict:
    name = ath.get("displayName", "?")
    status = inj.get("status", "")
    d = inj.get("details") or {}
    if back:
        title = f"✅ {name} · {pos} is back"
        lines = [f"**{prev} → Active**"]
    else:
        title = f"{STATUS_EMOJI.get(status.lower(), '🩹')} {name} · {pos} → {status}"
        hurt = d.get("type") or (inj.get("type") or {}).get("description", "")
        detail = d.get("detail") if d.get("detail") and d.get("detail") not in ("Not Specified", hurt) else ""
        what = " ".join(x for x in (hurt, f"({detail.lower()})" if detail else "") if x)
        back_by = _when(d.get("returnDate") + "T12:00:00+00:00") if d.get("returnDate") else None
        lines = [f"**{_status_line(prev, status)}**" + (f" · {what}" if what else "")
                 + (f" · expected back around {back_by:%b} {back_by.day}" if back_by else "")]
    note = inj.get("shortComment") or ""
    if note:
        lines.append(note[:700])
    head = (ath.get("headshot") or {}).get("href")
    thumb = head or (team or {}).get("logo")
    return _embed(team, title=title[:256], description="\n\n".join(lines),
                  thumbnail={"url": thumb} if thumb else None, footer={"text": "ESPN injury report"},
                  timestamp=inj.get("date"))


# ------------------------------------------------------------------ NFL trades

def _trade_sentences(text: str) -> list[str]:
    """Each trade in a transaction on its own (one entry can hold two trades)."""
    # a sentence ends at a period after a real word, not after initials or Jr. ("J.J. McCarthy")
    parts = re.split(r"(?<=[a-z0-9]{2}\.)\s+(?=[A-Z])", text.strip())
    return [p for p in parts if TRADE.search(p)] or [text.strip()]


def _mentions(text: str, all_teams: dict, own: str) -> set:
    """Other teams a transaction names. Shared cities (New York, Los Angeles) only count with the nickname."""
    unique = {t["abbr"]: t for t in all_teams.values()}.values()
    cities = [t["city"] for t in unique]
    found = set()
    for info in unique:
        if info["abbr"] == own:
            continue
        names = [info["name"], info["short"]] + ([info["city"]] if cities.count(info["city"]) == 1 else [])
        if any(n and re.search(rf"\b{re.escape(n)}\b", text) for n in names):
            found.add(info["abbr"])
    return found


PLAYER = re.compile(r"\b(?:[A-Z]{1,3}s?) ((?:[A-Z][\w.'-]*\.? ){1,3}[A-Z][\w.'-]+)")


def _players(text: str) -> set:
    return {" ".join(m.group(1).split()[-2:]).rstrip(".") for m in PLAYER.finditer(text)}


def _headline(sides: dict, all_teams: dict, involved=frozenset()) -> str:
    for abbr, sentence in sides.items():
        m = re.match(r"Acquired ((?:[A-Z]{1,3}s?) [^,]+?)(?: and | from |,)", sentence)
        if m:
            return f"🔁 TRADE: {all_teams[abbr]['short']} acquire {m.group(1)}"
    for abbr, sentence in sides.items():
        m = re.match(r"Traded ((?:[A-Z]{1,3}s?) [^,]+?)(?: and | to )", sentence)
        if m:
            others = [a for a in sides if a != abbr] or sorted(_mentions(sentence, all_teams, abbr) | set(involved) - {abbr})
            team = all_teams[others[0]]["short"] if others else ""
            return f"🔁 TRADE: {team} acquire {m.group(1)}" if team else f"🔁 TRADE: {m.group(1)}"
    return "🔁 NFL TRADE"


def nfl_trades(all_teams: dict, seen: set, since: datetime) -> list[tuple[str, dict]]:
    """Trades since `since`, oldest first, one post per trade."""
    rows = []
    for page in range(1, 10):
        data = _get("transactions", limit=100, page=page)
        batch = data.get("transactions", [])
        for t in batch:
            when = _when(t.get("date"))
            if when and when < since:
                continue
            if TRADE.search(t.get("description", "")):
                for sentence in _trade_sentences(t["description"]):
                    rows.append((when, (t.get("team") or {}).get("abbreviation", ""), sentence))
        oldest = min((_when(t.get("date")) for t in batch if t.get("date")), default=None)
        if page >= data.get("pageCount", 1) or (oldest and oldest < since):
            break
    # each trade shows up once per team: put the halves back together (same teams within a day,
    # or the same player within ten days, since ESPN's two write-ups don't always agree)
    groups = []   # {"day", "teams", "players", "sides"}
    for when, abbr, sentence in sorted(rows, key=lambda r: r[0] or since):
        if abbr not in all_teams:
            continue
        day = when.date() if when else since.date()
        involved = {abbr} | _mentions(sentence, all_teams, abbr)
        players = _players(sentence)
        repeat = next((g for g in groups if abbr in g["sides"] and players and players & g["players"]
                       and abs((g["day"] - day).days) <= 10), None)
        if repeat:   # ESPN listed the same team's side twice: keep the fuller write-up
            if len(sentence) > len(repeat["sides"][abbr]):
                repeat["sides"][abbr] = sentence
            continue
        match = next((g for g in groups if abbr not in g["sides"] and abs((g["day"] - day).days) <= 10 and (
            (g["teams"] == involved and abs((g["day"] - day).days) <= 1 and not (players and g["players"]
                                                                                  and not players & g["players"]))
            or (players & g["players"]))), None)
        if match:
            match["teams"] |= involved
            match["players"] |= players
            match["sides"][abbr] = sentence
        else:
            groups.append({"day": day, "teams": set(involved), "players": players, "sides": {abbr: sentence}})
    out = []
    for g in groups:
        day, sides = g["day"], g["sides"]
        key = f"{day}:{'-'.join(sorted(g['players']) or sorted(g['teams']))}"
        if key in seen:
            continue
        teams_in = [all_teams[a] for a in sorted(g["teams"], key=lambda a: (a not in sides, a))]
        title = _headline(sides, all_teams, g["teams"])
        star = next((t for t in teams_in if title.startswith(f"🔁 TRADE: {t['short']} ")), teams_in[0])
        other = next((t for t in teams_in if t is not star), None)
        fields = [{"name": all_teams[a]["name"], "value": s[:1000]} for a, s in sides.items()]
        author = {"name": " ↔ ".join([star["short"]] + [t["short"] for t in teams_in if t is not star])}
        if other and other.get("logo"):
            author["icon_url"] = other["logo"]
        out.append((key, _embed(star, author=author, title=title[:256], fields=fields,
                                thumbnail={"url": star["logo"]} if star.get("logo") else None,
                                footer={"text": f"ESPN transactions · {day:%b} {day.day}" if day else "ESPN transactions"})))
    return out[-MAX_PER_RUN:]


# ------------------------------------------------------------------ posting

def run(cfg, router, state: dict, dry_run: bool) -> list[str]:
    bot = router.bot
    if not bot:
        return ["skipped: needs the bot account"]
    wire = state.setdefault("wire", {})
    notes = []
    try:
        all_teams = teams()
    except Exception as err:  # noqa: BLE001 - ESPN being down shouldn't break the other jobs
        return [f"couldn't reach ESPN's NFL feeds ({str(err)[:120]})"]
    me = None

    def send(key: str, embeds: list[tuple[str, dict]], label: str):
        nonlocal me
        found = router.target(key)
        if not found and not dry_run:
            notes.append(f"{label}: no #{cfg.channels.get(key, key)} channel yet")
            return False
        channel_id, name = found or (None, f"{cfg.channels.get(key, key)} (not created yet)")
        if dry_run:
            notes.append(f"{label}: would post {len(embeds)} to #{name}")
            for _, e in embeds[:12]:
                body = e.get("description") or " // ".join(f"{f['name']}: {f['value']}" for f in e.get("fields", []))
                notes.append(f"    [{e.get('color', 0):06x}] {(e.get('author') or {}).get('name', '')} | {e.get('title')} | {body[:170]}")
            return True
        if channel_id in router.objects:
            try:
                me = me or bot.me()
                bot.make_read_only(router.objects[channel_id], me["id"])
            except RuntimeError:
                pass
        for _, embed in embeds:
            bot.post_embed(channel_id, embed)
        notes.append(f"{label}: posted {len(embeds)} to #{name}")
        return True

    try:
        seen = set(wire.get("news", []))
        posts, in_feed = headlines(all_teams, seen, first_run="news" not in wire)
        if send("wire_headlines", posts, "headlines") and not dry_run:
            wire["news"] = list(dict.fromkeys(wire.get("news", []) + in_feed))[-300:]
    except Exception as err:  # noqa: BLE001
        notes.append(f"headlines failed: {str(err)[:120]}")
    try:
        posts, current, gone = injuries(all_teams, wire.get("injuries", {}), first_run="injuries" not in wire,
                                        gone=wire.get("injuries_gone", {}))
        if send("wire_injuries", posts, "injuries") and not dry_run:
            wire["injuries"] = current
            wire["injuries_gone"] = gone
    except Exception as err:  # noqa: BLE001
        notes.append(f"injuries failed: {str(err)[:120]}")
    try:
        first = "trades" not in wire
        since = (datetime.now(timezone.utc) - timedelta(days=21 if not first else 120))
        posts = nfl_trades(all_teams, set(wire.get("trades", [])), since)
        if send("wire_trades", posts, "nfl trades") and not dry_run:
            wire["trades"] = (wire.get("trades", []) + [k for k, _ in posts])[-300:]
    except Exception as err:  # noqa: BLE001
        notes.append(f"nfl trades failed: {str(err)[:120]}")
    return notes
