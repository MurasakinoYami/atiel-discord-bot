# Atiel Discord Bot

The Discord bot for an AION 2 guild community: field-boss respawn timers, scheduled event pings and group finding.

## Features

- **Boss timers:** report a kill with `/killed`, or set a timer from the in-game countdown with `/timer`. The bot tracks respawns for 24 field bosses, posting a live board and pinging opt-in roles 5 minutes before each spawn
- **Event pings:** rifts, sieges and other fixed-schedule events, on the game server's clock (GMT+9, no daylight saving) and converted for EU players
- **Legions:** `/legion register|invite|kick|promote|demote|transfer|disband|info|list` gives each guild its own role and private hall, with staff approval
- **Party voice channels:** join "Create Party" to get your own voice channel, managed with `/party name` and `/party limit`
- **/lfg:** post an expedition or dungeon group
- **/topreporters:** a leaderboard of who keeps the timers alive
- Every post uses Discord's **Components V2** card layout
- State is kept in a JSON file, so restarts lose nothing

## Run

```bash
pip install -r requirements.txt
cp config.example.json config.json   # fill in your guild, channel and role IDs
DISCORD_TOKEN=... python bot.py
```

In production it runs on a small Linux cloud VM as a systemd service (`atiel-bot.service`), with a memory cap and automatic restart.

Built with Python and discord.py. Developed with AI-assisted coding (Claude); I designed the features and ran and maintained the bot for the community.
