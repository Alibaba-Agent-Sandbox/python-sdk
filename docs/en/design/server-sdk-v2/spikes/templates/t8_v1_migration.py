"""T8: migrating a v1 server: legacy_compat mounts what v1 exposed; the diff tells what a narrow policy drops."""
from _t import *
from ebxp.api import SandboxServer, presets, legacy_diff, Policy, ops, op

@op("custom.my_old_command", effects="exec")
def old(ctx) -> dict:
    return {"ok": True}

ws = workspace()
narrow = SandboxServer(presets.download_only(root=ws), strict=False)
dropped = legacy_diff(narrow)
check("diff names the legacy routes a narrow policy silently drops (B-6)", "commands.run" in dropped and "files.download" not in dropped, dropped[:5])
legacy = SandboxServer(presets.legacy_compat(), strict=False)
check("legacy_compat reproduces v1 exposure except system.env.set", legacy_diff(legacy) == ["system.env.set"])
check("legacy_compat is loud: lint errors for unsafe scopes", sum(m.startswith("error") for m in legacy.check()) >= 2)
check("a registered custom op is reported as unmounted until a rule mounts it", any("custom.my_old_command" in m for m in narrow.check()), narrow.check())
done("T8")
