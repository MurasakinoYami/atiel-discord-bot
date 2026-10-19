"""Atiel Asmodians bot: Altgard field-boss timers, scheduled-event pings, expedition LFG.
Everything it posts is a Components V2 card. State lives in state.json next to this file."""
import asyncio, json, os, re, time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import discord
from discord import app_commands, ui

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = json.load(open(os.path.join(HERE, "config.json"), encoding="utf-8"))
STATE_FILE = os.path.join(HERE, "state.json")
GUILD = discord.Object(id=int(CFG["guild"]))
CH, RO = CFG["channels"], CFG["roles"]
TZ = timezone(timedelta(hours=9))   # Global server clock, GMT+9, no DST (AION2 Hub, confirmed in game)
GOLD, RED, PURPLE, GREEN, BROWN, TEAL = 0xC9A227, 0xB71C1C, 0x4527A0, 0x2E7D32, 0x5D4037, 0x00695C
LEAD = 5 * 60          # boss ping lead
WINDOW = 10 * 60       # bosses appear within ~10 min after the timer ends

# Altgard field bosses: id, name, location / note, respawn minutes
BOSSES = [
    ("gartua", "Immortal Gartua", "Immortal Isle, SW", 720), ("lagta", "High Commander Lagta", "Lagta Fortress", 720),
    ("kashapa", "Soul Ruler Kashapa", "Fafnite Deposit", 360), ("dartan", "Silent Dartan", "Basfelt Ruins", 360),
    ("vishwada", "Dark Shadow Vishwada", "", 360), ("shylak", "Sharp Shylak", "Expert's refining", 360),
    ("guruta", "Drakan Battalion Weapon Guruta", "Expert's refining", 360), ("karuka", "Visionary Karuka", "Spiritstone", 240),
    ("barthien", "Executioner Barthien", "Expert's refining", 240), ("axios", "Specter Archon Axios", "", 240),
    ("newbold", "Desecrator Newbold", "", 240), ("hardirun", "Addicted Hardirun", "", 180), ("shujakan", "Veteran Shujakan", "", 180),
    ("resana", "Advisor Resana", "", 180), ("linx", "Special Ops Leader Linx", "", 180), ("garsan", "Predator Garsan", "Raw Leather", 120),
    ("trid", "Deceiver Trid", "", 120), ("kelpina", "Blue Wave Kelpina", "", 120), ("nutah", "High Overseer Nutah", "", 120),
    ("lannar", "Blood Warrior Lannar", "", 90), ("vargor", "Berserker Vargor", "", 60), ("danar", "Melted Danar", "", 30),
    ("rajit", "Faithful Rajit", "", 30), ("aed", "Black Warrior Aed", "", 30),
]
BOSS = {b[0]: {"name": b[1], "note": b[2], "iv": b[3] * 60} for b in BOSSES}

# Fixed events. Source: AION2 Hub (https://aion2hub.com/tools/event-timer and /tools/world-bosses), datamined from the
# Global client; every Global region (EU included) runs on a GMT+9 server clock with NO daylight saving.
# days: Mon=0 .. Sun=6 (None = every day). lead in minutes. ping=False: listed only, never pinged.
EVENTS = [
    {"id": "rift", "name": "Spacetime Rift", "hours": [0, 3, 6, 9, 12, 15, 18, 21], "min": 0, "days": None, "lead": 5,
     "role": "p_rift", "ch": "rifts", "colour": PURPLE, "emoji": "🌌", "note": "Portals are open for the first 10 minutes."},
    {"id": "kaira", "name": "Watcher Kaira", "hours": [1, 4, 7, 10, 13, 16, 19, 22], "min": 0, "days": None, "lead": 5,
     "role": "p_boss", "ch": "bosscalls", "colour": RED, "emoji": "👁️", "note": "Chaotic Lower Reshanta world boss."},
    {"id": "artifact", "name": "Abyss Artifact Event", "hours": [21], "min": 0, "days": [0, 3, 5], "lead": 15,
     "role": "p_siege", "ch": "siege", "colour": BROWN, "emoji": "🏰", "note": "Get into Siege-Comms.", "dur": 10},
    {"id": "executors", "name": "Executors Argo, Kaira and Tamasa", "hours": [21], "min": 30, "days": [0, 3, 5], "lead": 10,
     "role": "p_siege", "ch": "siege", "colour": BROWN, "emoji": "⚔️", "note": "Chaotic Lower Reshanta world bosses."},
    {"id": "siegeboss", "name": "Abyss Siege Boss", "hours": [21], "min": 0, "days": [4, 6], "lead": 15,
     "role": "p_siege", "ch": "siege", "colour": BROWN, "emoji": "🐲", "note": "Get into Siege-Comms."},
    {"id": "beritra", "name": "Beritra Air Raid", "hours": list(range(24)), "min": 30, "days": None, "lead": 5,
     "role": "p_field", "ch": "fieldevents", "colour": RED, "emoji": "🐉", "note": "Field boss event, about 13 minutes. Also: Accursed Sword, Incursion of the Spirits."},
    {"id": "minigames", "name": "Field minigames", "hours": list(range(24)), "min": 0, "days": None, "lead": 0, "ping": False,
     "role": "p_field", "ch": "fieldevents", "colour": TEAL, "emoji": "🎪", "note": ""},
    {"id": "daily", "name": "Daily reset", "hours": [16], "min": 0, "days": None, "lead": 0, "ping": False,
     "role": "p_event", "ch": "general", "colour": GOLD, "emoji": "🔄", "note": ""},
    {"id": "weekly", "name": "Weekly reset", "hours": [16], "min": 0, "days": [2], "lead": 0, "ping": False,
     "role": "p_event", "ch": "general", "colour": GOLD, "emoji": "📆", "note": ""},
]
MINIGAMES = ["Defend Shugo Merchants", "Goldrin's Treasure", "Hidden Lugi", "Jump Jump", "Mysterious Track", "Not This Tile?",
             "Nyerk Shooter", "Odyle Flight Frenzy", "Shugo's Dilemma", "Up! Up! Up!", "Wraith Evasion"]
SIEGE_EVENTS = ("artifact", "executors", "siegeboss")
CREDIT = "-# Schedule data: [AION2 Hub](https://aion2hub.com/tools/event-timer), datamined from the Global client. Huge thanks to them!"

def load():
    try: return json.load(open(STATE_FILE, encoding="utf-8"))
    except Exception: return {}
S = load()
for _k in ("spawn", "by", "pinged", "lfg", "reports", "legions", "legion_req", "temp_vc", "tickets", "sched_events"):
    S.setdefault(_k, {})
def save():
    tmp = STATE_FILE + ".tmp"
    json.dump(S, open(tmp, "w", encoding="utf-8")); os.replace(tmp, STATE_FILE)

def ts(t, f="R"): return f"<t:{int(t)}:{f}>"
def parse_dur(s):
    """'1h23m', '1:23', '83', '83m', '2h' -> seconds"""
    s = s.strip().lower().replace(" ", "")
    m = re.fullmatch(r"(\d+):(\d{1,2})(?::(\d{1,2}))?", s)
    if m: return int(m[1]) * 3600 + int(m[2]) * 60 + int(m[3] or 0)
    m = re.fullmatch(r"(?:(\d+)h)?(?:(\d+)m?)?(?:(\d+)s)?", s)
    if m and any(m.groups()): return int(m[1] or 0) * 3600 + int(m[2] or 0) * 60 + int(m[3] or 0)
    raise ValueError(s)

def card(colour, *parts, buttons=None, ping=None):
    """Build a V2 LayoutView: parts are strings (text) or None (divider).
    V2 messages can't have plain content, so a ping goes in as the first text line."""
    v = ui.LayoutView(timeout=None)
    items = ([ui.TextDisplay(ping)] if ping else []) + [ui.Separator() if p is None else ui.TextDisplay(p) for p in parts]
    if buttons: items.append(ui.ActionRow(*buttons))
    v.add_item(ui.Container(*items, accent_colour=colour))
    return v

def pcard(ping, colour, *parts, **kw): return card(colour, *parts, ping=ping, **kw)

def killed_button(bid):
    return ui.Button(label="Killed just now", emoji="✅", style=discord.ButtonStyle.success, custom_id=f"killed:{bid}")

def next_event(e, after):
    now = datetime.fromtimestamp(after, TZ)
    for d in range(0, 8):
        day = (now + timedelta(days=d)).date()
        if e["days"] is not None and day.weekday() not in e["days"]: continue
        for h in e["hours"]:
            t = datetime(day.year, day.month, day.day, h, e["min"], tzinfo=TZ).timestamp()
            if t > after: return t
    return None

intents = discord.Intents.default()
intents.members = True
intents.voice_states = True
client = discord.Client(intents=intents, activity=discord.Activity(type=discord.ActivityType.watching, name="Altgard boss timers"))
_hits = {}
def rate_ok(uid, kind, limit, window):
    """Sliding-window limiter: at most `limit` actions per `window` seconds per user."""
    now = time.time(); key = (uid, kind)
    q = [t for t in _hits.get(key, []) if t > now - window]
    if len(q) >= limit: _hits[key] = q; return False
    q.append(now); _hits[key] = q
    if len(_hits) > 5000:  # keep memory bounded during a join wave
        for k in [k for k, v in _hits.items() if not v or v[-1] < now - 300]: _hits.pop(k, None)
    return True

class Tree(app_commands.CommandTree):
    async def interaction_check(self, inter: discord.Interaction) -> bool:
        # autocomplete fires once per keystroke: never count it, or typing a boss name eats the whole allowance
        if inter.type == discord.InteractionType.autocomplete: return True
        if rate_ok(inter.user.id, "cmd", 20, 30): return True
        try: await inter.response.send_message("Slow down a little, try again in a few seconds.", ephemeral=True)
        except discord.HTTPException: pass
        return False
tree = Tree(client)

# ---------- board ----------
def board_view():
    now = time.time()
    known, up, unknown = [], [], []
    for bid, b in BOSS.items():
        t = S["spawn"].get(bid)
        if t is None: unknown.append(b["name"]); continue
        if t + WINDOW < now: unknown.append(b["name"] + " *(window passed, unconfirmed)*"); continue
        (up if t <= now else known).append((t, bid, b))
    known.sort(); up.sort()
    def line(t, b, live=False):
        tag = f" · {b['note']}" if b["note"] else ""
        return (f"🟢 **{b['name']}**: spawning now, window ends {ts(t + WINDOW)}{tag}" if live
                else f"⏳ **{b['name']}**: {ts(t)} ({ts(t, 't')}){tag}")
    parts = ["# 🐉 Altgard Field Bosses", "-# Live board. Report a kill with `/killed`, or copy the in-game countdown with `/timer`. "
             "Bosses appear within ~10 minutes after the timer ends."]
    if up: parts += [None, "### Spawning now\n" + "\n".join(line(t, b, True) for t, _, b in up)]
    if known: parts += [None, "### Upcoming\n" + "\n".join(line(t, b) for t, _, b in known)]
    nxt = []
    for e in EVENTS:
        if e["id"] == "minigames": continue
        t = next_event(e, now)
        if t: nxt.append((t, e))
    nxt.sort(key=lambda x: x[0])
    parts += [None, "### 📅 Next scheduled\n" + "\n".join(f"{e['emoji']} **{e['name']}**: {ts(t)} ({ts(t, 'f')})" for t, e in nxt)]
    if unknown: parts += [None, "-# ❔ No timer yet: " + ", ".join(unknown)]
    parts.append(f"-# Updated {ts(now)}\n" + CREDIT)
    text = "\n".join(p for p in parts if p)
    # TextDisplay max is 4000 chars per component, split on dividers
    return card(GOLD, *parts)

async def refresh_board():
    ch = client.get_channel(int(CH["timers"]))
    view = board_view()
    mid = S.get("board")
    try:
        if mid:
            msg = ch.get_partial_message(int(mid)); await msg.edit(view=view); return
    except discord.NotFound:
        pass
    msg = await ch.send(view=view, allowed_mentions=discord.AllowedMentions.none())
    S["board"] = str(msg.id); save()

# ---------- ticking ----------
async def ticker():
    await client.wait_until_ready()
    last_board = 0
    while not client.is_closed():
        try:
            now = time.time(); changed = False
            for bid, t in list(S["spawn"].items()):
                key = f"{bid}:{int(t)}"
                if t - LEAD <= now < t + WINDOW and key not in S["pinged"]:
                    S["pinged"][key] = now; changed = True
                    b = BOSS[bid]
                    ch = client.get_channel(int(CH["bosscalls"]))
                    await ch.send(view=pcard(f"<@&{RO['p_boss']}>", RED,
                        f"## 🐉 {b['name']} spawns {ts(t)}",
                        f"Spawn time {ts(t, 't')}" + (f" · {b['note']}" if b["note"] else "") + f"\n-# Timer reported by <@{S['by'].get(bid, '0')}>",
                        buttons=[killed_button(bid)]),
                        allowed_mentions=discord.AllowedMentions(roles=True))
            for e in EVENTS:
                t = next_event(e, now)
                key = f"{e['id']}:{int(t)}"
                if t and e.get("ping", True) and t - e["lead"] * 60 <= now and key not in S["pinged"]:
                    S["pinged"][key] = now; changed = True
                    ch = client.get_channel(int(CH[e["ch"]]))
                    await ch.send(view=pcard(f"<@&{RO[e['role']]}>", e["colour"],
                        f"## {e['emoji']} {e['name']} starts {ts(t)}", f"{ts(t, 'F')}" + (f"\n{e['note']}" if e["note"] else "")),
                        allowed_mentions=discord.AllowedMentions(roles=True))
            S["pinged"] = {k: v for k, v in S["pinged"].items() if v > now - 86400 * 2}
            if changed: save()
            if changed or now - last_board > 120:
                await refresh_board(); last_board = now
            await periodic(now)
        except Exception as ex:
            print("tick error:", repr(ex))
        try: open(os.path.join(HERE, "heartbeat"), "w").write(str(int(time.time())))  # watched by cron
        except OSError: pass
        await asyncio.sleep(20)

# ---------- commands ----------
async def boss_ac(inter, current):
    cur = current.lower()
    return [app_commands.Choice(name=f"{b['name']} ({b['iv'] // 3600}h{(b['iv'] % 3600) // 60:02d})", value=bid)
            for bid, b in BOSS.items() if cur in b["name"].lower()][:25]

def resolve_boss(s):
    """Accept the autocomplete id, or a typed name/part of it when it matches exactly one boss."""
    s = (s or "").strip().lower()
    if s in BOSS: return s
    hits = [bid for bid, b in BOSS.items() if s and (s == b["name"].lower() or s in b["name"].lower())]
    return hits[0] if len(hits) == 1 else None

UNKNOWN = "Couldn't tell which boss that is. Start typing the name and pick it from the list."

def recent_report(bid):
    """(who, when) if this boss was reported in the last 2 minutes, else None."""
    t = S["spawn"].get(bid); at = S.get("reported_at", {}).get(bid, 0)
    return (S["by"].get(bid), at) if t and time.time() - at < 120 else None

def set_spawn(bid, t, uid):
    S.setdefault("reported_at", {})[bid] = time.time()
    S["spawn"][bid] = t; S["by"][bid] = str(uid)
    S["reports"][str(uid)] = S["reports"].get(str(uid), 0) + 1
    save()

def ok_card(bid, t, how):
    b = BOSS[bid]
    return card(GREEN, f"### ✅ {b['name']}", f"{how}\nNext spawn {ts(t)} ({ts(t, 't')}). I'll ping 5 minutes before.")

@tree.command(name="killed", description="Report a field boss kill; starts its respawn timer", guild=GUILD)
@app_commands.describe(boss="Which boss", minutes_ago="How many minutes ago it died (default: just now)")
@app_commands.autocomplete(boss=boss_ac)
async def killed(inter: discord.Interaction, boss: str, minutes_ago: app_commands.Range[int, 0, 720] = 0):
    boss = resolve_boss(boss)
    if not boss: return await inter.response.send_message(UNKNOWN, ephemeral=True)
    r = recent_report(boss)
    if r: return await inter.response.send_message(f"Already reported by <@{r[0]}> {ts(r[1])}. Timer: {ts(S['spawn'][boss])}.", ephemeral=True, allowed_mentions=discord.AllowedMentions.none())
    t = time.time() - minutes_ago * 60 + BOSS[boss]["iv"]
    set_spawn(boss, t, inter.user.id)
    await inter.response.send_message(view=ok_card(boss, t, f"Killed {'just now' if not minutes_ago else f'{minutes_ago} min ago'}, reported by {inter.user.mention}."),
                                      allowed_mentions=discord.AllowedMentions.none())
    await refresh_board()

@tree.command(name="timer", description="Set a boss timer from the in-game countdown (Exploration > Field Boss)", guild=GUILD)
@app_commands.describe(boss="Which boss", time_left="Time left, e.g. 1h23m, 1:23 or 83")
@app_commands.autocomplete(boss=boss_ac)
async def timer(inter: discord.Interaction, boss: str, time_left: str):
    boss = resolve_boss(boss)
    if not boss: return await inter.response.send_message(UNKNOWN, ephemeral=True)
    try: secs = parse_dur(time_left)
    except ValueError: return await inter.response.send_message("Couldn't read that. Try `1h23m`, `1:23` or `83`.", ephemeral=True)
    t = time.time() + secs
    set_spawn(boss, t, inter.user.id)
    await inter.response.send_message(view=ok_card(boss, t, f"Timer set from the in-game countdown by {inter.user.mention}."),
                                      allowed_mentions=discord.AllowedMentions.none())
    await refresh_board()

@tree.command(name="cleartimer", description="Remove a wrong boss timer", guild=GUILD)
@app_commands.autocomplete(boss=boss_ac)
async def cleartimer(inter: discord.Interaction, boss: str):
    boss = resolve_boss(boss) or boss
    S["spawn"].pop(boss, None); save()
    await inter.response.send_message(view=card(GOLD, f"Cleared the timer for **{BOSS.get(boss, {'name': boss})['name']}**."), ephemeral=True)
    await refresh_board()

@tree.command(name="bosses", description="Show upcoming field bosses (only you see it)", guild=GUILD)
async def bosses(inter: discord.Interaction):
    await inter.response.send_message(view=board_view(), ephemeral=True)

# ---------- expedition LFG ----------
def lfg_view(tid):
    g = S["lfg"][tid]
    need = g["size"] - len(g["members"])
    roster = "\n".join(f"{i + 1}. <@{m}>" for i, m in enumerate(g["members"])) or "-"
    status = "✅ **Full**" if need <= 0 else f"Looking for **{need}** more" + (f": {g['needs']}" if g["needs"] else "")
    when = ts(g["when"], "F") + f" ({ts(g['when'])})" if g.get("when") else "**Now**"
    return pcard(g.get("ping") or None, TEAL, f"## 🗺️ {g['title']}", f"🕒 {when}\n👑 Leader <@{g['leader']}>\n{status}" + (f"\n📝 {g['notes']}" if g["notes"] else ""), None,
                f"### Party ({len(g['members'])}/{g['size']})\n{roster}",
                buttons=[ui.Button(label="Join", emoji="✋", style=discord.ButtonStyle.success, custom_id=f"lfg:join:{tid}", disabled=need <= 0),
                         ui.Button(label="Leave", style=discord.ButtonStyle.secondary, custom_id=f"lfg:leave:{tid}"),
                         ui.Button(label="Close", emoji="🔒", style=discord.ButtonStyle.danger, custom_id=f"lfg:close:{tid}")])

@tree.command(name="lfg", description="Post an expedition / dungeon group in Expedition-LFG", guild=GUILD)
@app_commands.describe(title="e.g. 'Fire Temple normal' or 'Transcendence 3'", size="Party size", needs="e.g. 'healer + tank'",
                       starts_in="When: blank = now, or e.g. 30m, 1h30m", notes="Gear score, voice, anything else", ping="Ping Expedition LFG Pings")
async def lfg(inter: discord.Interaction, title: str, size: app_commands.Range[int, 2, 8] = 4, needs: str = "",
              starts_in: str = "", notes: str = "", ping: bool = True):
    when = None
    if starts_in:
        try: when = time.time() + parse_dur(starts_in)
        except ValueError: return await inter.response.send_message("Couldn't read `starts_in`. Try `30m` or `1h30m`.", ephemeral=True)
    await inter.response.defer(ephemeral=True)
    forum = client.get_channel(int(CH["exp_lfg"]))
    tags = [t for t in forum.available_tags if t.name in ("Expedition",)]
    lowered = needs.lower()
    for word, tag in (("tank", "Need Tank"), ("heal", "Need Healer"), ("dps", "Need DPS")):
        if word in lowered: tags += [t for t in forum.available_tags if t.name == tag]
    tmp = {"ping": f"<@&{RO['p_exp']}>" if ping else "", "title": title[:90], "size": size, "needs": needs[:120], "notes": notes[:300], "when": when, "leader": str(inter.user.id), "members": [str(inter.user.id)], "created": time.time()}
    S["lfg"]["_new"] = tmp
    thread, msg = await forum.create_thread(name=f"{title[:80]} ({size}p)", applied_tags=tags[:5], view=lfg_view("_new"),
                                            allowed_mentions=discord.AllowedMentions(roles=ping))
    tid = str(thread.id)
    S["lfg"][tid] = S["lfg"].pop("_new"); save()
    await msg.edit(view=lfg_view(tid))
    await inter.followup.send(view=card(TEAL, f"Group posted: {thread.mention}"), ephemeral=True)


# =====================================================================
#  helpers shared by the systems below
# =====================================================================
from style import cname
def guild(): return client.get_guild(int(CFG["guild"]))
def humans(g):
    """Member count without bots (needs the member cache; falls back to the raw count until it's chunked)."""
    return sum(1 for m in g.members if not m.bot) if g.chunked else g.member_count
def chan(key): return client.get_channel(int(CH[key]))
def role(key): g = guild(); return g.get_role(int(RO[key])) if g else None
def is_staff(m):
    return isinstance(m, discord.Member) and (m.guild_permissions.manage_roles or any(r.id in (int(RO["mod"]), int(RO["admin"])) for r in m.roles))
NONE = discord.AllowedMentions.none()
async def eph(inter, colour, *parts):
    if inter.response.is_done(): await inter.followup.send(view=card(colour, *parts), ephemeral=True)
    else: await inter.response.send_message(view=card(colour, *parts), ephemeral=True)
def section(text_, thumb):
    return ui.Section(ui.TextDisplay(text_), accessory=ui.Thumbnail(thumb))

# =====================================================================
#  weekly schedule post: every time is a Discord timestamp, so each
#  reader sees it in their own timezone. Rebuilt every hour.
# =====================================================================
def upcoming(e, now, n):
    out, t = [], now
    for _ in range(n):
        t = next_event(e, t + 1)
        if not t: break
        out.append(t)
    return out

def schedule_view(now):
    E = {e["id"]: e for e in EVENTS}
    def weekly(eid):
        e = E[eid]
        return f"{e['emoji']} **{e['name']}**\n" + "\n".join(f"└ {ts(t, 'F')} ({ts(t)})" for t in upcoming(e, now, 3))
    def three_hourly(eid):
        e = E[eid]; times = upcoming(e, now, 8)
        return f"{e['emoji']} **{e['name']}**: next {ts(times[0])}\n└ " + " · ".join(ts(t, "t") for t in times)
    d, w = upcoming(E["daily"], now, 1)[0], upcoming(E["weekly"], now, 1)[0]
    b = upcoming(E["beritra"], now, 1)[0]; mg = upcoming(E["minigames"], now, 1)[0]
    return card(BROWN,
        "# 📅 Weekly Schedule\n-# Every time below is shown in **your own timezone**. The bot rebuilds this post every hour. "
        "(In-game server clock: GMT+9, no daylight saving.)",
        None, f"### 🔄 Resets\n🔄 **Daily reset**: {ts(d, 't')} ({ts(d)})\n📆 **Weekly reset** (Wednesday): {ts(w, 'F')} ({ts(w)})",
        None, "### 🏰 Abyss and siege\n" + "\n".join(weekly(i) for i in SIEGE_EVENTS),
        None, "### 🌌 Every 3 hours\n" + three_hourly("rift") + "\n-# Rift portals are open for the first 10 minutes.\n" + three_hourly("kaira"),
        None, f"### ⏰ Every hour\n🐉 **Beritra Air Raid**: every hour at half past, next {ts(b)}\n"
              f"🎪 **Field minigames**: every hour on the hour, next {ts(mg)}\n-# " + " · ".join(MINIGAMES),
        None, f"-# Field bosses are kill-based, see <#{CH['timers']}>. If a time is off after a patch, tell staff. Updated {ts(now)}\n" + CREDIT)

async def refresh_schedule(now):
    ch = chan("schedule")
    mid = S.get("schedule_msg")
    if mid:
        try: await ch.get_partial_message(int(mid)).edit(view=schedule_view(now)); return
        except discord.NotFound: pass
    async for m in ch.history(limit=20):
        if m.author.id == client.user.id:
            try: await m.delete()
            except discord.HTTPException: pass
    msg = await ch.send(view=schedule_view(now), allowed_mentions=NONE)
    S["schedule_msg"] = str(msg.id); save()

# =====================================================================
#  periodic jobs (called from ticker every ~20 s)
# =====================================================================
_busy = {}
async def sync_events(g, now):
    _busy["events"] = True
    try:
        vc = chan("v_siege")
        evs = await g.fetch_scheduled_events()
        names = {f"{e['emoji']} {e['name']}" for e in EVENTS if e["id"] in SIEGE_EVENTS}
        for ev in evs:  # drop our own events that no longer match the schedule (e.g. the old Berlin-time ones)
            if ev.creator_id == client.user.id and ev.name not in names:
                try: await ev.delete()
                except discord.HTTPException: pass
        have = {(ev.name, int(ev.start_time.timestamp())) for ev in evs}
        for e in EVENTS:
            if e["id"] not in SIEGE_EVENTS: continue
            for t in upcoming(e, now, 4):
                if t > now + 7 * 86400: break
                key = f"{e['id']}:{int(t)}"
                if key in S["sched_events"] or (f"{e['emoji']} {e['name']}", int(t)) in have: continue
                try:
                    ev = await g.create_scheduled_event(name=f"{e['emoji']} {e['name']}", start_time=datetime.fromtimestamp(t, TZ),
                        entity_type=discord.EntityType.voice, channel=vc, privacy_level=discord.PrivacyLevel.guild_only,
                        description=(e["note"] or "Faction event.") + " Comms in Siege-Comms; leaders and officers speak.")
                    S["sched_events"][key] = str(ev.id); save()
                except discord.HTTPException as ex:
                    print("sched event:", ex, flush=True); return
        S["sched_events"] = {k: v for k, v in S["sched_events"].items() if int(k.split(":")[1]) > now - 86400}
        save()
    finally:
        _busy["events"] = False

_last = {"stats": 0, "events": 0, "sweep": 0, "sched": 0}
async def periodic(now):
    g = guild()
    if not g: return
    # --- LFG reminders and auto-close ---
    for tid, grp in list(S["lfg"].items()):
        if tid.startswith("_"): continue
        th = g.get_thread(int(tid)) or client.get_channel(int(tid))
        if grp.get("when") and not grp.get("reminded") and now >= grp["when"]:
            grp["reminded"] = True; save()
            if th: await th.send(view=pcard(" ".join(f"<@{m}>" for m in grp["members"]), TEAL, "## ⏰ Starting now", "Get to the entrance, the leader will invite."))
        if now > (grp.get("when") or grp.get("created", now)) + 3 * 3600:
            S["lfg"].pop(tid, None); save()
            try:
                if th: await th.edit(archived=True, locked=True)
            except discord.HTTPException: pass
    # --- schedule post ---
    if now - _last["sched"] > 3600:
        _last["sched"] = now
        try: await refresh_schedule(now)
        except discord.HTTPException as ex: print("schedule:", ex)
    # --- member counter (channel renames are rate limited: 2 per 10 min) ---
    if now - _last["stats"] > 600:
        _last["stats"] = now
        n = humans(g)
        if n and (S.get("stat_count") != n or S.get("stat_label") != "Asmodians"):
            try:
                await chan("stat_members").edit(name=cname("👥", f"Asmodians: {n:,}")); S["stat_count"] = n; S["stat_label"] = "Asmodians"; save()
            except discord.HTTPException as ex: print("stats:", ex)
    # --- Discord scheduled events: own task, Discord rate-limits creation hard and it must never stall pings ---
    if now - _last["events"] > 1800 and not _busy.get("events"):
        _last["events"] = now
        asyncio.create_task(sync_events(g, now))
    # --- sweep empty temp voice channels (in case we missed a leave while offline) ---
    if now - _last["sweep"] > 300:
        _last["sweep"] = now
        for cid in list(S["temp_vc"]):
            c = g.get_channel(int(cid))
            if c is None: S["temp_vc"].pop(cid, None); save()
            elif not c.members:
                try: await c.delete()
                except discord.HTTPException: pass
                S["temp_vc"].pop(cid, None); save()

# =====================================================================
#  joins / leaves: queued and posted in batches every 20 s, so a join
#  wave produces a handful of messages, not hundreds
# =====================================================================
JOINS, LEAVES = [], []

@client.event
async def on_member_join(m: discord.Member):
    if m.guild.id != int(CFG["guild"]) or m.bot: return
    JOINS.append(m)

@client.event
async def on_member_remove(m: discord.Member):
    if m.guild.id != int(CFG["guild"]): return
    LEAVES.append(m)
    for key, l in S["legions"].items():
        if l["leader"] == str(m.id):
            try: await chan("legionreq").send(view=card(RED, f"### ⚠️ Leader of **{l['name']}** left the server", "Use `/legion transfer` as staff, or disband it."))
            except discord.HTTPException: pass

async def flush_members():
    await client.wait_until_ready()
    c = lambda k: f"<#{CH[k]}>"
    while not client.is_closed():
        await asyncio.sleep(20)
        try:
            now = time.time()
            if JOINS:
                batch = JOINS[:]; del JOINS[:]
                n = humans(batch[0].guild)
                if len(batch) == 1:
                    m = batch[0]
                    v = ui.LayoutView(timeout=None)
                    v.add_item(ui.Container(section(f"## 🪽 Welcome, {m.mention}!\nYou're Asmodian **#{n:,}** on Atiel.\n"
                        f"Read {c('rules')}, check {c('timers')}, and find a group in {c('exp_lfg')} or a legion in {c('legion_rec')}.",
                        m.display_avatar.url), accent_colour=GOLD))
                else:
                    shown = " ".join(m.mention for m in batch[:20]) + (f" and **{len(batch) - 20}** more" if len(batch) > 20 else "")
                    v = card(GOLD, f"## 🪽 Welcome to Atiel, {len(batch)} new Asmodians!", shown,
                             f"We're **{n:,}** strong. Read {c('rules')}, check {c('timers')}, find a group in {c('exp_lfg')} or a legion in {c('legion_rec')}.")
                await chan("general").send(view=v, allowed_mentions=discord.AllowedMentions(users=len(batch) <= 20))
                lines = []
                for m in batch[:25]:
                    young = now - m.created_at.timestamp() < 7 * 86400
                    lines.append(f"{'⚠️' if young else '📥'} {m.mention} `{m}` · created {ts(m.created_at.timestamp())}")
                if len(batch) > 25: lines.append(f"…and {len(batch) - 25} more")
                young_n = sum(1 for m in batch if now - m.created_at.timestamp() < 7 * 86400)
                await chan("joinlog").send(view=card(RED if young_n else GREEN, f"### 📥 {len(batch)} joined" + (f" · ⚠️ {young_n} new accounts (<7 days)" if young_n else ""),
                                                     "\n".join(lines)), allowed_mentions=NONE)
            if LEAVES:
                batch = LEAVES[:]; del LEAVES[:]
                lines = [f"📤 `{m}` `{m.id}` · joined {ts(m.joined_at.timestamp()) if m.joined_at else '?'}" for m in batch[:25]]
                if len(batch) > 25: lines.append(f"…and {len(batch) - 25} more")
                await chan("joinlog").send(view=card(0x757575, f"### 📤 {len(batch)} left", "\n".join(lines)), allowed_mentions=NONE)
        except Exception as ex:
            print("flush error:", repr(ex), flush=True)

# =====================================================================
#  suggestions: auto vote
# =====================================================================
@client.event
async def on_thread_create(th: discord.Thread):
    if th.parent_id != int(CH["suggest"]): return
    await asyncio.sleep(2)
    try:
        msg = await th.fetch_message(th.id)
        await msg.add_reaction("👍"); await msg.add_reaction("👎")
    except discord.HTTPException: pass

# =====================================================================
#  join-to-create party voice
# =====================================================================
@client.event
async def on_voice_state_update(m: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
    if after.channel and after.channel.id == int(CH["v_create"]):
        src = after.channel
        if len(S["temp_vc"]) >= 40 or len(m.guild.channels) > 450 or not rate_ok(m.id, "vc", 2, 60):
            try: await m.move_to(None)  # disconnect; they can join a fixed room instead
            except discord.HTTPException: pass
            return
        try:
            vc = await m.guild.create_voice_channel(cname("🎧", f"{m.display_name[:20]}'s Party"), category=src.category,
                     position=src.position + 1, overwrites={**src.category.overwrites, m: discord.PermissionOverwrite(manage_channels=True, move_members=True, connect=True)})
            S["temp_vc"][str(vc.id)] = str(m.id); save()
            await m.move_to(vc)
        except discord.HTTPException as ex: print("temp vc:", ex)
    if before.channel and str(before.channel.id) in S["temp_vc"] and not before.channel.members:
        try: await before.channel.delete()
        except discord.HTTPException: pass
        S["temp_vc"].pop(str(before.channel.id), None); save()

party = app_commands.Group(name="party", description="Manage your Create-Party voice channel", guild_ids=[int(CFG["guild"])])
def _own_vc(inter):
    vc = inter.user.voice.channel if isinstance(inter.user, discord.Member) and inter.user.voice else None
    if not vc or S["temp_vc"].get(str(vc.id)) != str(inter.user.id): return None
    return vc
@party.command(name="name", description="Rename your party channel")
async def party_name(inter: discord.Interaction, name: app_commands.Range[str, 1, 30]):
    vc = _own_vc(inter)
    if not vc: return await eph(inter, RED, "You need to be in a party channel you created.")
    await vc.edit(name=cname("🎧", name)); await eph(inter, GREEN, f"Renamed to **{name}**.")
@party.command(name="limit", description="Set the user cap of your party channel (0 = no cap)")
async def party_limit(inter: discord.Interaction, limit: app_commands.Range[int, 0, 99]):
    vc = _own_vc(inter)
    if not vc: return await eph(inter, RED, "You need to be in a party channel you created.")
    await vc.edit(user_limit=limit); await eph(inter, GREEN, f"Limit set to **{limit or 'none'}**.")
tree.add_command(party)

# =====================================================================
#  tickets (private threads in Support)
# =====================================================================
async def ticket_open(inter):
    uid = str(inter.user.id)
    old = S["tickets"].get(uid)
    if old:
        th = inter.guild.get_thread(int(old))
        if th and not th.archived: return await eph(inter, PURPLE, f"You already have an open ticket: {th.mention}")
    await inter.response.defer(ephemeral=True)
    th = await chan("support").create_thread(name=f"ticket-{inter.user.name}"[:90], type=discord.ChannelType.private_thread, invitable=False)
    await th.add_user(inter.user)
    S["tickets"][uid] = str(th.id); save()
    await th.send(view=pcard(f"{inter.user.mention} <@&{RO['mod']}>", PURPLE, "## 🎫 Ticket opened",
        "Tell us what's going on. Screenshots help. A Centurion will reply here.\nOnly you and the staff can see this thread.",
        buttons=[ui.Button(label="Close ticket", emoji="🔒", style=discord.ButtonStyle.danger, custom_id=f"ticket:close:{uid}")]),
        allowed_mentions=discord.AllowedMentions(users=True, roles=True))
    await inter.followup.send(view=card(PURPLE, f"Ticket opened: {th.mention}"), ephemeral=True)

async def ticket_close(inter, uid):
    if str(inter.user.id) != uid and not is_staff(inter.user): return await eph(inter, RED, "Only the ticket owner or staff can close it.")
    await inter.response.send_message(view=card(0x757575, f"🔒 Ticket closed by {inter.user.mention}."), allowed_mentions=NONE)
    S["tickets"].pop(uid, None); save()
    try: await chan("modlogs").send(view=card(0x757575, f"🎫 Ticket {inter.channel.mention} (<@{uid}>) closed by {inter.user.mention}"), allowed_mentions=NONE)
    except discord.HTTPException: pass
    if isinstance(inter.channel, discord.Thread): await inter.channel.edit(archived=True, locked=True)

# =====================================================================
#  boss reporter leaderboard
# =====================================================================
@tree.command(name="topreporters", description="Who keeps the boss timers alive", guild=GUILD)
async def topreporters(inter: discord.Interaction):
    top = sorted(S["reports"].items(), key=lambda x: -x[1])[:15]
    medals = ["🥇", "🥈", "🥉"]
    lines = [f"{medals[i] if i < 3 else f'`{i + 1}.`'} <@{u}>: **{n}**" for i, (u, n) in enumerate(top)] or ["Nobody yet. Be the first with `/killed`!"]
    await inter.response.send_message(view=card(GOLD, "# 🏆 Top Boss Reporters", "\n".join(lines)), allowed_mentions=NONE)

# =====================================================================
#  legions
# =====================================================================
PALETTE = [0xE57373, 0xF06292, 0xBA68C8, 0x9575CD, 0x7986CB, 0x64B5F6, 0x4FC3F7, 0x4DD0E1, 0x4DB6AC, 0x81C784, 0xAED581, 0xFFD54F, 0xFFB74D, 0xFF8A65, 0xA1887F]
def legion_of(m):
    ids = {r.id for r in getattr(m, "roles", [])}
    for k, l in S["legions"].items():
        if int(l["role"]) in ids: return k, l
    return None, None
def rank(l, uid):
    uid = str(uid)
    return "leader" if l["leader"] == uid else "officer" if uid in l["officers"] else "member"
async def safe_roles(m, add=(), remove=()):
    try:
        if add: await m.add_roles(*[r for r in add if r])
        if remove: await m.remove_roles(*[r for r in remove if r])
        return True
    except discord.Forbidden:
        return False
ROLE_HINT = "\n-# ⚠️ I couldn't change a role. Drag the bot's role to the top in Server Settings → Roles."

legion = app_commands.Group(name="legion", description="Legion tools", guild_ids=[int(CFG["guild"])])

async def legion_ac(inter, current):
    return [app_commands.Choice(name=l["name"], value=k) for k, l in S["legions"].items() if current.lower() in k][:25]

@legion.command(name="register", description="Apply to register your legion (staff approve it)")
async def l_register(inter: discord.Interaction, name: app_commands.Range[str, 2, 24]):
    name = name.strip()
    k, _ = legion_of(inter.user)
    if k: return await eph(inter, RED, "You're already in a legion. Leave it first.")
    if name.lower() in S["legions"]: return await eph(inter, RED, "A legion with that name already exists.")
    if any(r["user"] == str(inter.user.id) for r in S["legion_req"].values()): return await eph(inter, RED, "You already have a pending request.")
    rid = str(int(time.time() * 1000))
    S["legion_req"][rid] = {"name": name, "user": str(inter.user.id)}; save()
    await chan("legionreq").send(view=card(GOLD, f"## 📥 Legion request: {name}", f"Leader: {inter.user.mention} (`{inter.user}`)",
        buttons=[ui.Button(label="Approve", style=discord.ButtonStyle.success, custom_id=f"lreq:ok:{rid}"),
                 ui.Button(label="Deny", style=discord.ButtonStyle.danger, custom_id=f"lreq:no:{rid}")]), allowed_mentions=NONE)
    await eph(inter, GOLD, f"Request for **{name}** sent to staff. You'll get your role and hall when it's approved.")

async def legion_request(inter, act, rid):
    if not is_staff(inter.user): return await eph(inter, RED, "Staff only.")
    req = S["legion_req"].pop(rid, None); save()
    if not req: return await eph(inter, RED, "This request was already handled.")
    g = inter.guild; leader = g.get_member(int(req["user"]))
    if act == "no" or not leader:
        why = "denied" if act == "no" else "cancelled (the leader left)"
        await inter.response.edit_message(view=card(0x757575, f"### ❌ {req['name']}: {why} by {inter.user.mention}"))
        if leader:
            try: await leader.send(view=card(RED, f"Your legion **{req['name']}** was not approved. Open a ticket if you have questions."))
            except discord.HTTPException: pass
        return
    await inter.response.defer()
    name = req["name"]
    colour = PALETTE[len(S["legions"]) % len(PALETTE)]
    r = await g.create_role(name=f"🏛️ {name}", colour=discord.Colour(colour), mentionable=True, reason=f"Legion approved by {inter.user}")
    halls = g.get_channel(int(CH["cat_halls"]))
    ow = {g.default_role: discord.PermissionOverwrite(view_channel=False),
          r: discord.PermissionOverwrite(view_channel=True, send_messages=True, connect=True, speak=True, read_message_history=True),
          role("mod"): discord.PermissionOverwrite(view_channel=True),
          g.me: discord.PermissionOverwrite(view_channel=True, manage_channels=True, send_messages=True)}
    text_ = await g.create_text_channel(cname("🏛️", name.replace(" ", "-")), category=halls, overwrites=ow, topic=f"Private hall of {name}.")
    voice = await g.create_voice_channel(cname("🔊", name), category=halls, overwrites=ow)
    key = name.lower()
    S["legions"][key] = {"name": name, "role": str(r.id), "text": str(text_.id), "voice": str(voice.id), "leader": str(leader.id), "officers": [], "created": time.time()}
    save()
    ok = await safe_roles(leader, add=[r, role("leader")])
    await inter.edit_original_response(view=card(GREEN, f"### ✅ {name}: approved by {inter.user.mention}", f"Role {r.mention}, hall {text_.mention}" + ("" if ok else ROLE_HINT)))
    await text_.send(view=pcard(leader.mention, colour, f"# 🏛️ Welcome to the {name} hall",
        "Only members of the legion (and staff) can see this channel and its voice room.\n"
        "`/legion invite @user` to add people · `/legion promote @user` for officers · `/legion info` for your roster.\n"
        f"Recruit in <#{CH['legion_rec']}>."), allowed_mentions=discord.AllowedMentions(users=True))
    try: await chan("alliance").send(view=card(colour, f"### 🏛️ New legion: **{name}**", f"Led by {leader.mention}. Welcome to the alliance!"), allowed_mentions=NONE)
    except discord.HTTPException: pass

def need_rank(inter, *ranks):
    k, l = legion_of(inter.user)
    if not l or rank(l, inter.user.id) not in ranks: return None, None
    return k, l

@legion.command(name="invite", description="Invite someone to your legion (leader/officer)")
async def l_invite(inter: discord.Interaction, user: discord.Member):
    k, l = need_rank(inter, "leader", "officer")
    if not l: return await eph(inter, RED, "Only a legion leader or officer can invite.")
    if user.bot: return await eph(inter, RED, "Bots can't join legions.")
    if legion_of(user)[0]: return await eph(inter, RED, f"{user.mention} is already in a legion.")
    await inter.response.send_message(view=pcard(user.mention, 0xFFB300, f"## 🏛️ Legion invite: **{l['name']}**",
        f"{inter.user.mention} invites {user.mention} to join **{l['name']}**.",
        buttons=[ui.Button(label="Accept", style=discord.ButtonStyle.success, custom_id=f"linv:ok:{k}:{user.id}"),
                 ui.Button(label="Decline", style=discord.ButtonStyle.secondary, custom_id=f"linv:no:{k}:{user.id}")]),
        allowed_mentions=discord.AllowedMentions(users=True))

async def legion_invite_answer(inter, act, key, uid):
    if str(inter.user.id) != uid: return await eph(inter, RED, "This invite isn't for you.")
    l = S["legions"].get(key)
    if not l: return await inter.response.edit_message(view=card(0x757575, "That legion no longer exists."))
    if act == "no": return await inter.response.edit_message(view=card(0x757575, f"{inter.user.mention} declined the invite to **{l['name']}**."))
    if legion_of(inter.user)[0]: return await eph(inter, RED, "You're already in a legion.")
    ok = await safe_roles(inter.user, add=[inter.guild.get_role(int(l["role"]))])
    await inter.response.edit_message(view=card(GREEN, f"✅ {inter.user.mention} joined **{l['name']}**!" + ("" if ok else ROLE_HINT)))
    hall = inter.guild.get_channel(int(l["text"]))
    if hall and ok: await hall.send(view=card(GREEN, f"👋 {inter.user.mention} joined the legion."), allowed_mentions=NONE)

@legion.command(name="kick", description="Remove a member from your legion (leader/officer)")
async def l_kick(inter: discord.Interaction, user: discord.Member):
    k, l = need_rank(inter, "leader", "officer")
    if not l and not is_staff(inter.user): return await eph(inter, RED, "Only a legion leader or officer can kick.")
    tk, tl = legion_of(user)
    if not tl or (l and tk != k): return await eph(inter, RED, f"{user.mention} isn't in your legion.")
    tr = rank(tl, user.id)
    if tr == "leader" or (l and tr == "officer" and rank(l, inter.user.id) != "leader"):
        return await eph(inter, RED, "You can't kick someone of equal or higher rank.")
    if str(user.id) in tl["officers"]: tl["officers"].remove(str(user.id))
    save()
    ok = await safe_roles(user, remove=[inter.guild.get_role(int(tl["role"])), role("officer")])
    await eph(inter, GOLD, f"Removed {user.mention} from **{tl['name']}**." + ("" if ok else ROLE_HINT))

@legion.command(name="leave", description="Leave your legion")
async def l_leave(inter: discord.Interaction):
    k, l = legion_of(inter.user)
    if not l: return await eph(inter, RED, "You're not in a legion.")
    if rank(l, inter.user.id) == "leader": return await eph(inter, RED, "Leaders must `/legion transfer` or `/legion disband` first.")
    if str(inter.user.id) in l["officers"]: l["officers"].remove(str(inter.user.id)); save()
    ok = await safe_roles(inter.user, remove=[inter.guild.get_role(int(l["role"])), role("officer")])
    await eph(inter, GOLD, f"You left **{l['name']}**." + ("" if ok else ROLE_HINT))

@legion.command(name="promote", description="Make a member an officer (leader only)")
async def l_promote(inter: discord.Interaction, user: discord.Member):
    k, l = need_rank(inter, "leader")
    if not l: return await eph(inter, RED, "Only the legion leader can promote.")
    if legion_of(user)[0] != k or rank(l, user.id) != "member": return await eph(inter, RED, f"{user.mention} must be a regular member of your legion.")
    l["officers"].append(str(user.id)); save()
    ok = await safe_roles(user, add=[role("officer")])
    await eph(inter, GREEN, f"{user.mention} is now an officer of **{l['name']}**." + ("" if ok else ROLE_HINT))

@legion.command(name="demote", description="Remove officer rank (leader only)")
async def l_demote(inter: discord.Interaction, user: discord.Member):
    k, l = need_rank(inter, "leader")
    if not l or str(user.id) not in l["officers"]: return await eph(inter, RED, "Only the leader can demote one of their officers.")
    l["officers"].remove(str(user.id)); save()
    ok = await safe_roles(user, remove=[role("officer")])
    await eph(inter, GOLD, f"{user.mention} is no longer an officer." + ("" if ok else ROLE_HINT))

@legion.command(name="transfer", description="Hand leadership to another member (leader or staff)")
@app_commands.autocomplete(legion_name=legion_ac)
async def l_transfer(inter: discord.Interaction, user: discord.Member, legion_name: str = ""):
    k, l = need_rank(inter, "leader")
    if not l and is_staff(inter.user) and legion_name in S["legions"]: k, l = legion_name, S["legions"][legion_name]
    if not l: return await eph(inter, RED, "Only the leader (or staff, naming the legion) can transfer leadership.")
    if legion_of(user)[0] != k: return await eph(inter, RED, f"{user.mention} must be in **{l['name']}** first.")
    old = inter.guild.get_member(int(l["leader"]))
    l["leader"] = str(user.id)
    if str(user.id) in l["officers"]: l["officers"].remove(str(user.id))
    save()
    ok = await safe_roles(user, add=[role("leader")], remove=[role("officer")])
    if old: ok = await safe_roles(old, remove=[role("leader")]) and ok
    await inter.response.send_message(view=card(0xFFB300, f"👑 {user.mention} now leads **{l['name']}**." + ("" if ok else ROLE_HINT)), allowed_mentions=NONE)

@legion.command(name="disband", description="Disband your legion: deletes its role and hall (leader or staff)")
@app_commands.describe(confirm_name="Type the legion name to confirm")
@app_commands.autocomplete(confirm_name=legion_ac)
async def l_disband(inter: discord.Interaction, confirm_name: str):
    k, l = need_rank(inter, "leader")
    if not l and is_staff(inter.user): k, l = confirm_name.lower(), S["legions"].get(confirm_name.lower())
    if not l or confirm_name.lower() != k: return await eph(inter, RED, "Type your legion's exact name to confirm (leader or staff only).")
    await inter.response.defer(ephemeral=True)
    g = inter.guild
    r = g.get_role(int(l["role"]))
    for uid in [l["leader"], *l["officers"]]:
        m = g.get_member(int(uid))
        if m: await safe_roles(m, remove=[role("leader"), role("officer")])
    for cid in (l["text"], l["voice"]):
        c = g.get_channel(int(cid))
        if c:
            try: await c.delete()
            except discord.HTTPException: pass
    if r:
        try: await r.delete()
        except discord.HTTPException: pass
    S["legions"].pop(k, None); save()
    await inter.followup.send(view=card(0x757575, f"🏚️ **{l['name']}** has been disbanded."), ephemeral=True)
    try: await chan("alliance").send(view=card(0x757575, f"🏚️ **{l['name']}** has been disbanded."), allowed_mentions=NONE)
    except discord.HTTPException: pass

@legion.command(name="info", description="Show a legion's roster")
@app_commands.autocomplete(name=legion_ac)
async def l_info(inter: discord.Interaction, name: str = ""):
    k, l = (name.lower(), S["legions"].get(name.lower())) if name else legion_of(inter.user)
    if not l: return await eph(inter, RED, "No such legion." if name else "You're not in a legion. Try `/legion list`.")
    r = inter.guild.get_role(int(l["role"]))
    members = r.members if r else []
    offs = " ".join(f"<@{o}>" for o in l["officers"]) or "-"
    plain = [m.mention for m in members if str(m.id) != l["leader"] and str(m.id) not in l["officers"]]
    await inter.response.send_message(view=card(r.colour.value if r else GOLD, f"# 🏛️ {l['name']}",
        f"👑 Leader <@{l['leader']}>\n🎖️ Officers {offs}\n👥 **{len(members)}** members · founded {ts(l['created'], 'D')}",
        None, "### Members\n" + (" ".join(plain[:80]) or "-")), allowed_mentions=NONE)

@legion.command(name="list", description="All registered legions")
async def l_list(inter: discord.Interaction):
    g = inter.guild
    rows = []
    for k, l in S["legions"].items():
        r = g.get_role(int(l["role"]))
        rows.append((len(r.members) if r else 0, l))
    rows.sort(key=lambda x: -x[0])
    lines = [f"**{l['name']}**: {n} members · 👑 <@{l['leader']}>" for n, l in rows] or ["No legions yet. Leaders: `/legion register`."]
    await inter.response.send_message(view=card(GOLD, f"# 🏛️ Legions of Atiel ({len(rows)})", "\n".join(lines[:40])), allowed_mentions=NONE)
tree.add_command(legion)

# =====================================================================
#  staff: announcements as V2 cards (modal for multi-line text)
# =====================================================================
class AnnounceModal(ui.Modal, title="Announcement"):
    head = ui.TextInput(label="Title", max_length=120)
    body = ui.TextInput(label="Message (markdown ok)", style=discord.TextStyle.paragraph, max_length=3500)
    image = ui.TextInput(label="Image URL (optional)", required=False)
    def __init__(self, channel, ping, colour):
        super().__init__(); self.channel, self.ping, self.colour = channel, ping, colour
    async def on_submit(self, inter: discord.Interaction):
        items = [ui.TextDisplay(f"# {self.head.value}"), ui.Separator(), ui.TextDisplay(self.body.value)]
        if self.ping: items.insert(0, ui.TextDisplay("@everyone" if self.ping.is_default() else self.ping.mention))
        if self.image.value.strip().startswith("http"):
            items.append(ui.MediaGallery(discord.MediaGalleryItem(self.image.value.strip())))
        items.append(ui.TextDisplay(f"-# Posted by {inter.user.mention} · {ts(time.time(), 'f')}"))
        v = ui.LayoutView(timeout=None); v.add_item(ui.Container(*items, accent_colour=self.colour))
        await self.channel.send(view=v, allowed_mentions=discord.AllowedMentions(everyone=True, roles=True))
        await inter.response.send_message(view=card(GREEN, f"Posted in {self.channel.mention}."), ephemeral=True)

@tree.command(name="announce", description="Staff: post a styled announcement", guild=GUILD)
@app_commands.default_permissions(manage_messages=True)
@app_commands.describe(channel="Where (default: Announcements)", ping="Role to ping (optional)", colour="Accent colour")
@app_commands.choices(colour=[app_commands.Choice(name=n, value=v) for n, v in
    [("Gold", GOLD), ("Red", RED), ("Purple", PURPLE), ("Green", GREEN), ("Blue", 0x0277BD), ("Brown", BROWN)]])
async def announce(inter: discord.Interaction, channel: discord.TextChannel = None, ping: discord.Role = None, colour: int = GOLD):
    if not is_staff(inter.user): return await eph(inter, RED, "Staff only.")
    await inter.response.send_modal(AnnounceModal(channel or chan("news"), ping, colour))

@tree.command(name="when", description="Convert an in-game server time (GMT+9) to everyone's local time", guild=GUILD)
@app_commands.describe(time_="Server time (GMT+9), e.g. 21:00", day="Days from today (0 = today)")
@app_commands.rename(time_="time")
async def when(inter: discord.Interaction, time_: str, day: app_commands.Range[int, 0, 14] = 0):
    m = re.fullmatch(r"(\d{1,2})[:.](\d{2})", time_.strip())
    if not m: return await eph(inter, RED, "Use HH:MM, e.g. `21:00`.")
    d = (datetime.now(TZ) + timedelta(days=day)).date()
    t = datetime(d.year, d.month, d.day, int(m[1]), int(m[2]), tzinfo=TZ).timestamp()
    await inter.response.send_message(view=card(GOLD, f"🕒 Server **{time_}** = {ts(t, 'F')} ({ts(t)})",
        f"-# Copy this to share it in anyone's local time: `<t:{int(t)}:F>`"), allowed_mentions=NONE)

# =====================================================================
#  component router
# =====================================================================
@client.event
async def on_interaction(inter: discord.Interaction):
    if inter.type != discord.InteractionType.component: return
    cid = (inter.data or {}).get("custom_id", "")
    if not rate_ok(inter.user.id, "btn", 20, 20):
        try: return await inter.response.send_message("Slow down a little.", ephemeral=True)
        except discord.HTTPException: return
    try:
        if cid.startswith("killed:"): await boss_button(inter, cid.split(":", 1)[1])
        elif cid.startswith("lfg:"): await lfg_button(inter, *cid.split(":", 2)[1:])
        elif cid == "ticket:open": await ticket_open(inter)
        elif cid.startswith("ticket:close:"): await ticket_close(inter, cid.split(":", 2)[2])
        elif cid.startswith("lreq:"): await legion_request(inter, *cid.split(":", 2)[1:])
        elif cid.startswith("linv:"): await legion_invite_answer(inter, *cid.split(":", 3)[1:])
    except Exception as ex:
        print("interaction error:", cid, repr(ex), flush=True)
        try: await eph(inter, RED, "Something went wrong. Staff have been told.")
        except Exception: pass

async def boss_button(inter, bid):
    if bid not in BOSS: return
    r = recent_report(bid)
    if r: return await eph(inter, GREEN, f"Already confirmed by <@{r[0]}> {ts(r[1])}. Next spawn {ts(S['spawn'][bid])}.")
    t = time.time() + BOSS[bid]["iv"]
    set_spawn(bid, t, inter.user.id)
    await inter.response.send_message(view=ok_card(bid, t, f"Kill confirmed by {inter.user.mention}."), allowed_mentions=NONE)
    await refresh_board()

async def lfg_button(inter, act, tid):
    g = S["lfg"].get(tid)
    if not g: return await eph(inter, 0x757575, "This group is closed.")
    uid = str(inter.user.id)
    if act == "join":
        if uid in g["members"]: return await eph(inter, TEAL, "You're already in.")
        if len(g["members"]) >= g["size"]: return await eph(inter, RED, "Group is full.")
        g["members"].append(uid)
    elif act == "leave":
        if uid == g["leader"]: return await eph(inter, RED, "You're the leader. Use Close instead.")
        if uid in g["members"]: g["members"].remove(uid)
    elif act == "close":
        if uid != g["leader"] and not is_staff(inter.user): return await eph(inter, RED, "Only the leader can close this.")
        g["closed"] = True
    save()
    await inter.response.edit_message(view=lfg_view(tid))
    if act == "join" and len(g["members"]) >= g["size"]:
        await inter.channel.send(view=pcard(" ".join(f"<@{m}>" for m in g["members"]), GREEN, "## ✅ Group full", "Everyone's in. Have fun!"))
    if g.get("closed"):
        S["lfg"].pop(tid, None); save()
        if isinstance(inter.channel, discord.Thread): await inter.channel.edit(archived=True, locked=True)

@client.event
async def on_ready():
    # background jobs first: a rate-limited command sync must never delay pings
    if not getattr(client, "_ticker", None):
        client._ticker = asyncio.create_task(ticker())
        client._flush = asyncio.create_task(flush_members())
    print("ready as", client.user, flush=True)
    # on_ready also fires on reconnects; only push commands when their definitions changed
    import hashlib
    sig = hashlib.sha1(json.dumps([c.to_dict(tree) for c in tree.get_commands(guild=GUILD)], sort_keys=True, default=str).encode()).hexdigest()
    if S.get("cmd_sig") != sig:
        try:
            await tree.sync(guild=GUILD); S["cmd_sig"] = sig; save(); print("commands synced", flush=True)
        except discord.HTTPException as ex:
            print("command sync failed:", ex, flush=True)

if __name__ == "__main__":
    client.run(os.environ["DISCORD_TOKEN"])
