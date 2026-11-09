"""Finding the channels and remembering what was posted."""

import json

from newsroom import __main__ as cli


class FakeBot:
    def guilds(self):
        return [{"id": "g1"}]

    def guild_channels(self, guild_id):
        return [{"id": "1", "name": "📰┃Headlines", "type": 0}, {"id": "2", "name": "voice", "type": 2},
                {"id": "3", "name": "🚑-injury-report", "type": 0}]


def test_channels_are_found_by_name():
    router = cli.Router(FakeBot())
    assert router.target("wire_headlines") == ("1", "📰┃Headlines")
    assert router.target("wire_injuries") == ("3", "🚑-injury-report")
    assert router.target("wire_trades") is None


def test_needs_the_bot_token(monkeypatch, capsys):
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
    assert cli.main([]) == 1
    assert "DISCORD_BOT_TOKEN" in capsys.readouterr().out


def test_saves_state_only_when_something_changed(monkeypatch, tmp_path):
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "x")
    monkeypatch.setattr(cli, "STATE", tmp_path / "state.json")

    def fake_run(cfg, router, state, dry_run):
        state.setdefault("wire", {})["news"] = ["a"]
        return ["headlines: posted 1 to #headlines"]

    monkeypatch.setattr(cli.wire, "run", fake_run)
    assert cli.main([]) == 0
    assert json.loads((tmp_path / "state.json").read_text()) == {"wire": {"news": ["a"]}}
    (tmp_path / "state.json").unlink()
    assert cli.main(["--dry-run"]) == 0 and not (tmp_path / "state.json").exists()
