# S4: codex + claude_code host. devs: codex only. admins: everything. observers: read sessions only.
from h import *
from ebxp.api import SandboxServer, Policy, ops, Principal, AgentScope, PathScope
os.makedirs("/tmp/s4ws", exist_ok=True)
dev_scope = AgentScope(workdir=PathScope("/tmp/s4ws"), permissions="workspace-write")
policy = (Policy()
          .allow("agents.codex.**", principals=["role:dev"], agents=dev_scope)
          .allow("agents.**", principals=["role:admin"], agents=AgentScope(workdir=PathScope("/tmp/s4ws"), permissions="read-only"))
          .allow(ops.agents.sessions.get, ops.agents.sessions.list_items, ops.agents.sessions.stream_events,
                 principals=["role:observer"]))
srv = SandboxServer(policy, tokens={"t" * 20: Principal("a", ("admin", "dev", "observer"))})
dev, adm, obs = Principal("d", ("dev",)), Principal("a", ("admin",)), Principal("o", ("observer",))
check("dev codex.run", srv.call("agents.codex.run", principal=dev)[0] == 200)
check("dev claude_code.run 404", srv.call("agents.claude_code.run", principal=dev)[0] == 404)
check("admin claude_code.run", srv.call("agents.claude_code.run", principal=adm)[0] == 200)
check("observer cannot run", srv.call("agents.codex.run", principal=obs)[0] == 404)
check("observer cannot send", srv.call("agents.codex.sessions.send_event", principal=obs)[0] == 404)
check("agents.** never mounts install or adapter sessions.create (explicit-only)",
      srv.call("agents.codex.install", principal=adm)[0] == 404 and srv.call("agents.codex.sessions.create", principal=adm)[0] == 404)
check("config check clean", srv.check() == [], srv.check())
bare = SandboxServer(Policy().allow("agents.codex.run", principals=["role:dev"]), tokens={"t" * 20: Principal("a", ("admin",))})
check("agent run without AgentScope refused (exec-effect op)", bare.call("agents.codex.run", principal=dev)[1].get("code") == "policy.scope_required")
check("bare agent allow is a lint error", any("scope_required" in m for m in bare.check()), bare.check())
typo = SandboxServer(Policy().allow("agents.codex.session.get"), strict=False, tokens={"t" * 20: Principal("a", ("admin",))})
check("typo'd selector flagged with suggestion", any("did you mean" in m or "matches no operation" in m for m in typo.check()), typo.check())
done("S4")
