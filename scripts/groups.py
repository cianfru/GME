# The watched groups, built the same way by watch.py and entities.py (so both see the same members).
#   base_groups()   — focus wallet's cluster, Coinbase group, every quiet accumulator (stealth.json), every
#                     buy-and-forward holding wallet (vaults90.json) and the wallets of the 24–25 Sep 2025 reshuffle.
#   with_attached() — adds the wallets entities.py attached by following the coins (data/entities.json), so a split
#                     into a fresh wallet that a linking rule ties to the group is not read as the group shrinking.
import json, os, re
from txlib import D, FOCUS

RESHUFFLE = {"0xfa070156a411ef524e2b598ae892b707975594f4": "0xfa07…94f4", "0xd8cb407bb1aad1713d5056fcf333c185c1b3d493": "0xd8cb…d493",
             "0x1df28f138f6f10a23a5c474a79619d0c634d6356": "0x1df2…6356", "0xcc9a1e80fc7a6986d66a208d9ea58e8a100091e3": "0xcc9a…91e3",
             "0xff5811780f6cf89ac61019b1fc8cee604c2a9d50": "0xff58…9d50"}
COLLECTOR = "0xe1fc21df6bbe9caa933f93896866501375669717"
short = lambda a: a[:6] + "…" + a[-4:]

# Display names. Each group is called by the last four characters of the wallet it is named after, so the same short
# handle shows up everywhere (cards, tables, the flow map, alerts). The focus wallet's group is "fbb4": its owner's X
# name, which is also how its main wallet 0xe147…fbb4 ends. The watch files keep their original keys ("Your wallet's
# cluster", "Accumulator 0x53ee…efdb"); display() turns any text that carries them into the display names.
FOCUS_NAME = FOCUS[-4:]
KINDWORDS = ("Accumulator", "Holding wallet", "Sep-2025 wallet", "Linked group")
_FOC = re.compile(r"(?i)\b(?:your|focus) wallet's cluster")
_TAIL = re.compile(r"\b(" + "|".join(KINDWORDS) + r") 0x[0-9a-fA-F]{4}…([0-9a-fA-F]{4,})")
def display(t):
    return _TAIL.sub(r"\1 \2", _FOC.sub(FOCUS_NAME, t)) if isinstance(t, str) else t


def namer():
    """Watch key → display name, taken from the entity registry when it has the group (so a handle that had to grow
    to five characters reads the same everywhere), else display()."""
    p = os.path.join(D, "entities.json")
    reg = {e["wname"]: e["name"] for e in json.load(open(p)).get("entities", []) if e.get("wname")} if os.path.exists(p) else {}
    return lambda g: reg.get(g) or display(g)


def base_groups():
    FOC = {m["a"] for m in json.load(open(os.path.join(D, "focus_cluster.json")))["members"]}
    CBG = {r["a"] for r in json.load(open(os.path.join(D, "coinbase_group.json")))} | {COLLECTOR}
    ST = json.load(open(os.path.join(D, "stealth.json")))["rows"]
    V = json.load(open(os.path.join(D, "vaults90.json")))
    groups = {"Your wallet's cluster": set(FOC), "Coinbase group": set(CBG)}
    for r in ST:
        ws = set(r["wallets"])
        if ws & FOC or ws & CBG: continue
        groups[f"Accumulator {short(r['wallets'][0])}"] = ws
    for v, x in V.items():
        if not any(v in g for g in groups.values()): groups[f"Holding wallet {short(v)}"] = {v} | set(x["feeders"])
    for a, n in RESHUFFLE.items():
        if not any(a in g for g in groups.values()): groups[f"Sep-2025 wallet {n}"] = {a}
    return groups, FOC, CBG, ST, V


def with_attached(groups):
    p = os.path.join(D, "entities.json")
    if not os.path.exists(p): return groups
    claimed = {a for ws in groups.values() for a in ws}
    for e in json.load(open(p)).get("entities", []):
        g = e.get("wname")
        if g not in groups: continue
        for x in e.get("attached", []):
            if x["a"] not in claimed: groups[g].add(x["a"]); claimed.add(x["a"])
    return groups
