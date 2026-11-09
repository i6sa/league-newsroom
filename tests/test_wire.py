"""📡 The Wire: real NFL trades merged into one post, injury status changes, headlines, team colors."""

from datetime import datetime, timedelta, timezone
from unittest import mock

from newsroom import wire

TEAMS = [("22", "ARI", "Arizona Cardinals", "Cardinals", "Arizona", "a40227"),
         ("33", "BAL", "Baltimore Ravens", "Ravens", "Baltimore", "29126f"),
         ("34", "HOU", "Houston Texans", "Texans", "Houston", "03202f"),
         ("23", "PIT", "Pittsburgh Steelers", "Steelers", "Pittsburgh", "000000"),
         ("6", "DAL", "Dallas Cowboys", "Cowboys", "Dallas", "002a5c"),
         ("16", "MIN", "Minnesota Vikings", "Vikings", "Minnesota", "4f2683"),
         ("19", "NYG", "New York Giants", "Giants", "New York", "003c7f"),
         ("20", "NYJ", "New York Jets", "Jets", "New York", "115740"),
         ("13", "LV", "Las Vegas Raiders", "Raiders", "Las Vegas", "000000")]


def all_teams():
    out = {}
    for tid, abbr, name, short, city, color in TEAMS:
        info = {"id": tid, "abbr": abbr, "name": name, "short": short, "city": city, "color": int(color, 16),
                "logo": f"https://a.espncdn.com/i/teamlogos/nfl/500/{abbr.lower()}.png"}
        for key in (tid, abbr, name):
            out[key] = info
    return out


def tx(date, abbr, text):
    return {"date": date, "team": {"abbreviation": abbr}, "description": text}


FEED = {"pageCount": 1, "transactions": [
    tx("2026-11-06T08:00Z", "ARI", "Acquired a 2027 fourth round pick and a 2028 seventh-round pick from Baltimore in exchange for QB Jacoby Brissett and a 2027 fifth-round pick."),
    tx("2026-11-06T08:00Z", "BAL", "Acquired QB Jacoby Brissett and a 2027 fifth-round pick from Arizona Cardinals for a 2027 fourth round pick and a 2028 seventh-round pick."),
    tx("2026-10-12T07:00Z", "ARI", "Traded WR Marvin Harrison Jr. and a 2027 sixth-round draft pick to Houston for 2027 second- and seventh-round draft picks."),
    tx("2026-10-07T07:00Z", "PIT", "Signed DB Doneiko Slaughter to the practice squad. Traded CB Joey Porter Jr. to Dallas in exchange for a 2027 sixth-round pick and a 2028 second-round pick."),
    tx("2026-10-01T07:00Z", "DAL", "Acquired DB Joey Porter Jr. from Dallas in exchange for a 2027 sixth-round draft pick and a 2028 second-round draft pick."),
    tx("2026-09-28T07:00Z", "NYG", "Acquired QB J.J. McCarthy from Minnesota in exchange for a 2027 fifth-round draft pick. Waived QB Jake Haener."),
    tx("2026-09-28T07:00Z", "MIN", "Traded QB J.J. McCarthy to New York Giants for a 2027 fifth-round draft pick."),
    tx("2026-09-27T07:00Z", "LV", "Signed WR Somebody to the practice squad."),
]}

MIXED = {"pageCount": 1, "transactions": [
    tx("2026-08-20T07:00Z", "GB", "Acquired a 2028 sixth-round draft pick from Miami in exchange for QB Kyle McCord. Acquired TE Mark Redman from the Los Angeles Rams in exchange for a 2028 seventh-round draft pick."),
    tx("2026-08-20T07:00Z", "MIA", "Acquired QB Kyle McCord from Green Bay Packers for a 2028 sixth-round draft pick."),
    tx("2026-08-21T07:00Z", "MIA", "Acquired QB Kyle McCord from the Green Bay Packers in exchange for a 2028 sixth-round draft pick."),
]}


def trades(seen=()):
    since = datetime(2026, 7, 1, tzinfo=timezone.utc)
    with mock.patch.object(wire, "_get", return_value=FEED):
        return wire.nfl_trades(all_teams(), set(seen), since)


def test_each_trade_is_one_post_with_both_sides():
    posts = trades()
    titles = [e["title"] for _, e in posts]
    assert titles == ["🔁 TRADE: Giants acquire QB J.J. McCarthy",
                      "🔁 TRADE: Cowboys acquire DB Joey Porter Jr.",
                      "🔁 TRADE: Texans acquire WR Marvin Harrison Jr.",
                      "🔁 TRADE: Ravens acquire QB Jacoby Brissett"]
    mccarthy = posts[0][1]
    assert [f["name"] for f in mccarthy["fields"]] == ["New York Giants", "Minnesota Vikings"]
    assert mccarthy["fields"][0]["value"].startswith("Acquired QB J.J. McCarthy")      # the "Waived" part is dropped
    assert "Waived" not in mccarthy["fields"][0]["value"]
    porter = posts[1][1]
    assert {f["name"] for f in porter["fields"]} == {"Pittsburgh Steelers", "Dallas Cowboys"}   # ESPN's halves disagree
    assert "Signed" not in " ".join(f["value"] for f in porter["fields"])
    brissett = posts[3][1]
    assert brissett["color"] == 0x29126F and brissett["thumbnail"]["url"].endswith("/bal.png")
    assert brissett["author"]["name"] == "Ravens ↔ Cardinals" and brissett["author"]["icon_url"].endswith("/ari.png")
    assert "content" not in brissett                                                  # nobody gets pinged


def test_trades_post_once():
    first = trades()
    assert trades(seen={k for k, _ in first}) == []


def test_dark_team_colors_use_their_second_color():
    payload = {"sports": [{"leagues": [{"teams": [
        {"team": {"id": "13", "abbreviation": "LV", "displayName": "Las Vegas Raiders", "shortDisplayName": "Raiders",
                  "location": "Las Vegas", "color": "000000", "alternateColor": "a5acaf", "logos": [{"href": "lv.png"}]}},
        {"team": {"id": "4", "abbreviation": "CIN", "displayName": "Cincinnati Bengals", "shortDisplayName": "Bengals",
                  "location": "Cincinnati", "color": "fb4f14", "alternateColor": "000000", "logos": [{"href": "cin.png"}]}}]}]}]}
    with mock.patch.object(wire, "_get", return_value=payload):
        t = wire.teams()
    assert t["LV"]["color"] == 0xA5ACAF and t["13"]["logo"] == "lv.png"
    assert t["CIN"]["color"] == 0xFB4F14


def _injury_feed(entries):
    return {"injuries": [{"id": "33", "displayName": "Baltimore Ravens", "injuries": entries}]}


def _inj(pid, name, pos, status, hours_ago, **extra):
    when = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%MZ")
    return {"athlete": {"id": pid, "displayName": name, "position": {"abbreviation": pos}},
            "status": status, "date": when, **extra}


def test_injuries_post_status_changes_for_the_whole_nfl():
    feed = _injury_feed([
        _inj("1", "Lamar Jackson", "QB", "Injured Reserve", 3, shortComment="Jackson is scheduled to undergo thumb surgery.",
             details={"type": "Thumb", "detail": "Surgery", "returnDate": "2026-12-13"}),
        _inj("2", "Kyle Hamilton", "S", "Out", 2),                      # not a fantasy position
        _inj("3", "Derrick Henry", "RB", "Active", 1),                  # healthy, never was hurt
        _inj("4", "Zay Flowers", "WR", "Questionable", 40),             # older than the first-run window
    ])
    with mock.patch.object(wire, "_get", return_value=feed):
        posts, known, _ = wire.injuries(all_teams(), {}, first_run=True)
    assert [k for k, _ in posts] == ["1"]
    lamar = posts[0][1]
    assert lamar["title"] == "🚑 Lamar Jackson · QB → Injured Reserve"
    assert lamar["description"].startswith("**Injured Reserve** · Thumb (surgery) · expected back around Dec 13")
    assert lamar["color"] == 0x29126F and lamar["author"]["name"] == "Baltimore Ravens"
    assert known == {"1": "Injured Reserve", "3": "Active", "4": "Questionable"}

    later = _injury_feed([_inj("1", "Lamar Jackson", "QB", "Injured Reserve", 1),
                          _inj("4", "Zay Flowers", "WR", "Out", 1), _inj("3", "Derrick Henry", "RB", "Active", 1)])
    with mock.patch.object(wire, "_get", return_value=later):
        posts, known, _ = wire.injuries(all_teams(), known, first_run=False)
    assert [e["title"] for _, e in posts] == ["🔴 Zay Flowers · WR → Out"]
    assert posts[0][1]["description"].startswith("**Questionable → Out**")

    healed = _injury_feed([_inj("4", "Zay Flowers", "WR", "Active", 0)])
    with mock.patch.object(wire, "_get", return_value=healed):
        posts, _, _ = wire.injuries(all_teams(), known, first_run=False)
    assert posts[0][1]["title"] == "✅ Zay Flowers · WR is back"


def test_a_player_who_flickers_out_of_the_feed_is_not_posted_twice():
    yankoff = _inj("5", "Colson Yankoff", "TE", "Questionable", 1)
    known = {"5": "Questionable"}
    with mock.patch.object(wire, "_get", return_value=_injury_feed([])):        # ESPN drops him for a minute
        posts, known, gone = wire.injuries(all_teams(), known, first_run=False)
    assert posts == [] and known == {} and gone["5"][0] == "Questionable"
    with mock.patch.object(wire, "_get", return_value=_injury_feed([yankoff])):  # and he's back
        posts, known, gone = wire.injuries(all_teams(), known, first_run=False, gone=gone)
    assert posts == [] and known == {"5": "Questionable"} and gone == {}
    out = _injury_feed([_inj("5", "Colson Yankoff", "TE", "Out", 0)])            # a real change still posts
    with mock.patch.object(wire, "_get", return_value=out):
        posts, _, _ = wire.injuries(all_teams(), known, first_run=False)
    assert posts[0][1]["title"] == "🔴 Colson Yankoff · TE → Out"


def test_a_player_gone_for_a_long_time_counts_as_new_when_he_returns():
    long_ago = (datetime.now(timezone.utc) - timedelta(hours=30)).strftime("%Y-%m-%dT%H:%MZ")
    with mock.patch.object(wire, "_get", return_value=_injury_feed([_inj("5", "Colson Yankoff", "TE", "Questionable", 0)])):
        posts, _, gone = wire.injuries(all_teams(), {}, first_run=False, gone={"5": ["Questionable", long_ago]})
    assert len(posts) == 1 and gone == {}


def test_headlines_first_run_posts_a_few_and_remembers_the_rest():
    articles = [{"id": i, "type": "HeadlineNews", "headline": f"Story {i}", "published": f"2026-11-09T0{i}:00Z",
                 "description": "Summary", "links": {"web": {"href": f"https://espn.com/{i}"}},
                 "images": [{"url": f"https://img/{i}.jpg"}], "categories": [{"type": "team", "teamId": 33}]}
                for i in range(1, 8)] + [{"id": 99, "type": "Media", "headline": "A video", "published": "2026-11-09T09:00Z"}]
    with mock.patch.object(wire, "_get", return_value={"articles": articles}):
        posts, in_feed = wire.headlines(all_teams(), set(), first_run=True)
        assert [e["title"] for _, e in posts] == [f"Story {i}" for i in range(3, 8)]
        assert posts[-1][1]["image"]["url"] == "https://img/7.jpg" and posts[-1][1]["url"] == "https://espn.com/7"
        assert len(in_feed) == 7                                            # the video isn't a headline
        again, _ = wire.headlines(all_teams(), set(in_feed), first_run=False)
    assert again == []


def test_two_trades_in_one_entry_and_double_listings():
    TEAMS.extend([("9", "GB", "Green Bay Packers", "Packers", "Green Bay", "204e32"),
                  ("15", "MIA", "Miami Dolphins", "Dolphins", "Miami", "008e97"),
                  ("14", "LAR", "Los Angeles Rams", "Rams", "Los Angeles", "003594"),
                  ("24", "LAC", "Los Angeles Chargers", "Chargers", "Los Angeles", "0080c6")])
    with mock.patch.object(wire, "_get", return_value=MIXED):
        posts = wire.nfl_trades(all_teams(), set(), datetime(2026, 7, 1, tzinfo=timezone.utc))
    titles = sorted(e["title"] for _, e in posts)
    assert titles == ["🔁 TRADE: Dolphins acquire QB Kyle McCord", "🔁 TRADE: Packers acquire TE Mark Redman"]
    redman = next(e for _, e in posts if "Redman" in e["title"])
    assert redman["author"]["name"] == "Packers ↔ Rams"                   # "Los Angeles" alone would be ambiguous
    assert wire._dark(0xA40227) is False and wire._dark(0x0B162A) is True  # Cardinals red stays, Bears navy swaps
