"""Naming style for the Dragon Breath server: 「emoji」𝐁𝐨𝐥𝐝 for every channel, voice included."""
def bold(s):
    out = []
    for ch in s:
        if "A" <= ch <= "Z": out.append(chr(0x1D400 + ord(ch) - 65))
        elif "a" <= ch <= "z": out.append(chr(0x1D41A + ord(ch) - 97))
        elif "0" <= ch <= "9": out.append(chr(0x1D7CE + ord(ch) - 48))
        else: out.append(ch)
    return "".join(out)
def cname(emoji, name): return f"「{emoji}」{bold(name)}"
def catname(emoji, name): return f"━━━〚{emoji} {bold(name)}〛━━━"
