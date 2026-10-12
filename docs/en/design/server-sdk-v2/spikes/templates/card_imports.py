"""The reference card (09 section 3) is executable: every imported name and preset exists, lines <= 100 columns."""
import pathlib, re
from _t import *
import ebxp.api as api

doc = (pathlib.Path(__file__).resolve().parents[2] / "09-ai-codegen-usability.md").read_text()
card = doc[doc.index("```text\nEASY SANDBOX SERVER"):]
card = card[: card.index("\n```\n")]
lines = card.splitlines()

m = re.search(r"from easy_sandbox\.server import \(([^)]*)\)", card)
names = [n.strip() for n in m.group(1).replace("\n", " ").split(",") if n.strip()]
check("card import block parsed", len(names) >= 15, names)
missing = [n for n in names if not hasattr(api, n)]
check("every name the card imports exists in the facade", not missing, missing)

pm = re.search(r"presets \(one keyword root=.*?\n((?:    .*\n)+)", card)
preset_text = pm.group(1) if pm else ""
preset_names = sorted(set(re.findall(r"\b([a-z_]+)\(", preset_text)) - {"deny", "allow"})
bad = [n for n in preset_names if n not in ("deny",) and not hasattr(api.presets, n) and n != "legacy_diff"]
check("every preset named in the card exists", not bad, bad)
check("legacy_diff exists", hasattr(api, "legacy_diff"))
check("card lines are <= 100 columns", all(len(l) <= 100 for l in lines), [len(l) for l in lines if len(l) > 100])
check("card is under 200 lines", len(lines) < 200, len(lines))

for needle in ("EXPLICIT-ONLY", "SCOPES ARE REQUIRED", "conflicting_credentials", "agents.adapter_required",
               "X-EBX-Adapter", "E3100-E3111", "mode: build"):
    check(f"card mentions {needle}", needle in card)
check("card has no E9xxx", "E9" not in card)
done("card_imports")
