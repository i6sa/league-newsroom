# 📺 NFL Newsroom

Posts real NFL news from ESPN into a Discord server's NFL Newsroom channels, about a minute
after ESPN publishes it:

| Channel | What goes there |
|---|---|
| `#headlines` | Breaking NFL headlines |
| `#injury-report` | Injury status changes for QBs, RBs, WRs, TEs and kickers, plus "back" updates |
| `#nfl-trades` | Real NFL trades, in the teams' colors and logos |

Nothing here pings anyone, and it never mentions anyone's fantasy team.

## How it runs

- A free [cron-job.org](https://cron-job.org) job starts the GitHub Action every minute
  (`.github/workflows/newsroom.yml`). A 15-minute GitHub schedule is the backup.
- It finds the channels above by name (emoji and capitals don't matter; change the names in
  `channels.json`).
- `data/state.json` remembers what's already been posted, so nothing goes out twice.

This repo is public so GitHub Actions minutes are free. It only uses ESPN's public NFL feeds;
the Discord bot token is a GitHub secret (`DISCORD_BOT_TOKEN`) and never appears here.

## Run it by hand

Actions → NFL Newsroom → Run workflow. Tick "dry run" to print what it would post without posting.

## Develop

```
pip install requests pytest
pytest
```
