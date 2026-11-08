# Builds the alert message for the GitHub issue the workflow comments on (data/alerts/notify.md).
# Posts only what needs a look: HIGH watch alerts, and entity tripwires rated HIGH or MEDIUM
# (first exchange deposit or DEX sale in 90 days, coins moved outside a group, provisional wallets, forming groups,
# wallets joined by following the coins). Nothing to post → no file, and the workflow skips the comment.
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from txlib import D
from groups import display
out = os.path.join(D, "alerts", "notify.md")
if os.path.exists(out): os.remove(out)
W = json.load(open(os.path.join(D, "alerts", "latest.json"))) if os.path.exists(os.path.join(D, "alerts", "latest.json")) else {"alerts": [], "summary": {}}
E = json.load(open(os.path.join(D, "entities.json"))) if os.path.exists(os.path.join(D, "entities.json")) else {"alerts": []}
rows = [("HIGH", display(a["text"])) for a in W.get("alerts", []) if a["severity"] == "high"]
rows += [(a["severity"].upper(), display(a["text"])) for a in E.get("alerts", []) if a["severity"] in ("high", "medium")]
if not rows: print("nothing to notify"); sys.exit(0)
s = W.get("summary", {})
lines = [f"**GME terminal · {s.get('asOf', E.get('asOf', ''))[:16].replace('T', ' ')} UTC** · since {s.get('since', E.get('since', ''))[:16].replace('T', ' ')} UTC", ""]
lines += [f"- **{sev}** {t}" for sev, t in rows]
lines += ["", "Positions, not signals. Wallet links are evidence of shared control, not proof of ownership. https://gme-terminal.vercel.app/#entities", "",
          "_Posted by the terminal's scheduled job._"]
open(out, "w").write("\n".join(lines) + "\n")
print("\n".join(lines))
