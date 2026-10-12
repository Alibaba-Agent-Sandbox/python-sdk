"""Client/server parity ledger (design v2.1, 07-client-mirror.md section 6; finding IF-27).

Every op of the default registry must have a row.  `kind`:
  typed    generated method with typed result            stream   generated iterator/async-iterator helper
  raw      bytes / raw HTTP result                        admin    generated, guarded (explicit-only op)
  dynamic  reached through the dynamic tree / srv.call    reserved reserved id, no client method yet
  refused  server answers 404 not_found_error; client method raises NotSupportedError locally
`envd` names the envd-plane twin (sandbox.<module>) or None.  `asym` is the written reason when the two planes differ.
Run: python3 parity_ledger.py  (prints the markdown table; tests_parity.py asserts coverage against the registry).
"""
from __future__ import annotations

FILES = {
    "files.list": ("srv.files.list(path)", "files.list", "typed", ""),
    "files.stat": ("srv.files.stat(path), exists()", "files.get_info/exists", "typed", ""),
    "files.mkdir": ("srv.files.mkdir(path)", "files.make_dir", "typed", ""),
    "files.delete": ("srv.files.delete(path)", "files.remove", "typed", ""),
    "files.move": ("srv.files.move(source, destination)", "files.rename", "typed", ""),
    "files.search": ("srv.files.search(root, pattern)", None, "typed", "server-only convenience; envd has no search"),
    "files.upload": ("srv.files.upload(path, data)", "files.write", "typed", "base64-JSON; large files are better on envd"),
    "files.upload_stream": ("srv.files.upload_file(local, remote)", "files.upload_url (signed)", "stream", "chunked body; envd uses signed URLs"),
    "files.download": ("srv.files.download(path)", "files.read_bytes", "typed", ""),
    "files.download_stream": ("srv.files.download_file(remote, local)", "files.download_url (signed)", "stream", "chunked body"),
    "files.archive": ("srv.files.archive(paths)", None, "typed", "server-only"),
    "files.watch": ("srv.files.watch(path)", "files.watch", "stream", "SSE"),
}
BASE = {
    "core.health": ("srv.core.health()", None, "typed", "anonymous; used by readiness"),
    "core.capabilities": ("srv.discover() / srv.capabilities()", None, "typed", "never implicit (07 section 3)"),
    "core.describe": ("srv.describe(), srv.ops", None, "typed", ""),
    "core.check": ("caps.check(op, **args)", None, "typed", "dry-run; `explain` is the offline CLI twin"),
    "core.openapi": ("srv.core.openapi()", None, "raw", "documentation asset; no typed result (asymmetry A1)"),
    "core.reload": ("srv.core.reload()", None, "admin", "explicit-only admin op; exposed but never in a convenience group (asymmetry A2)"),
    "commands.run": ("srv.commands.run(command|argv)", "commands.run", "typed", "in-flight alias srv.process.shell is a deprecated alias"),
    "commands.stream": ("srv.commands.stream(command|argv)", "commands.stream", "stream", "in-flight alias srv.process.shell_stream"),
    "process.start": ("srv.process.start(...)", "commands.start", "typed", ""),
    "process.list": ("srv.process.list()", "commands.list", "typed", ""),
    "process.get": ("srv.process.get(pid)", None, "typed", "server-only; envd uses a handle"),
    "process.signal": ("srv.process.signal(pid, sig)", "commands.kill", "typed", "explicit-only op"),
    "process.stdin": ("srv.process.stdin(pid, data)", "commands.send_stdin", "typed", ""),
    "process.output": ("srv.process.output(pid, since)", None, "stream", "long-poll; follow() helper"),
    "terminal.create": ("srv.terminal.create()", "get_terminal", "typed", "explicit-only op"),
    "terminal.list": ("srv.terminal.list()", None, "typed", "server-only"),
    "terminal.get": ("srv.terminal.get(id)", None, "typed", "server-only"),
    "terminal.resize": ("srv.terminal.resize(id, cols, rows)", "terminal handle", "typed", ""),
    "terminal.delete": ("srv.terminal.delete(id)", "terminal handle", "typed", ""),
    "terminal.connect": ("srv.terminal.connect(id) -> PtyConnection", "terminal handle", "stream", "WebSocket on 9001; policed on upgrade"),
    "system.info": ("srv.system.info()", None, "typed", "envd metrics are platform plane (asymmetry A3)"),
    "system.metrics": ("srv.system.metrics()", "metrics (platform)", "typed", ""),
    "system.env.get": ("srv.system.env.get(names)", None, "typed", ""),
    "system.env.set": ("srv.system.env.set(vars)", None, "admin", "explicit-only; writes the server overlay only"),
    "system.ports": ("srv.system.ports()", None, "typed", ""),
    "system.packages": ("srv.system.packages(manager)", None, "typed", ""),
    "devtools.code.run": ("srv.devtools.code.run(language, code)", "code.run", "typed", "different engine than port 49999 (asymmetry A4)"),
    "devtools.git.status": ("srv.devtools.git.status(path)", None, "typed", ""),
    "devtools.git.diff": ("srv.devtools.git.diff(path)", None, "typed", ""),
    "browser.navigate": ("srv.browser.navigate(url)", None, "typed", "UrlScope-checked"),
    "browser.screenshot": ("srv.browser.screenshot()", None, "raw", "bytes"),
    "browser.content": ("srv.browser.content(type)", None, "typed", ""),
    "browser.click": ("srv.browser.click(selector)", None, "typed", ""),
    "browser.type": ("srv.browser.type(selector, text)", None, "typed", ""),
    "browser.evaluate": ("srv.browser.evaluate(script)", None, "typed", ""),
    "browser.pdf": ("srv.browser.pdf()", None, "raw", "bytes"),
    "browser.console": ("srv.browser.console()", None, "typed", ""),
    "custom.list": ("srv.custom.list()", "list_commands()", "typed", ""),
}
AGENTS = {
    "agents.runtimes.list": ("srv.agents.runtimes.list()", None, "typed", "was `agents.list` (N-1); flags experimental adapters"),
    "agents.runtimes.doctor": ("srv.agents.runtimes.doctor()", None, "typed", ""),
    "agents.models.list": ("srv.agents.models.list()", None, "typed", ""),
    "agents.definitions.create": ("srv.agents.definitions.create(...)", None, "typed", "official `agents.create`"),
    "agents.definitions.get": ("srv.agents.definitions.get(id)", None, "typed", ""),
    "agents.definitions.update": ("srv.agents.definitions.update(id, ...)", None, "typed", ""),
    "agents.definitions.list": ("srv.agents.definitions.list(**page)", None, "typed", "list envelope; auto-paging iterator"),
    "agents.definitions.delete": ("srv.agents.definitions.delete(id)", None, "typed", ""),
    "agents.environments.create": ("srv.agents.environments.create(...)", None, "typed", ""),
    "agents.environments.get": ("srv.agents.environments.get(id)", None, "typed", ""),
    "agents.environments.list": ("srv.agents.environments.list(**page)", None, "typed", ""),
    "agents.environments.files.create": ("-", None, "reserved", "reserved id (T-4); not implemented in 0.3.0 (asymmetry A5)"),
    "agents.environments.files.list": ("-", None, "reserved", "reserved id (T-4); not implemented in 0.3.0 (asymmetry A5)"),
    "agents.sessions.create": ("srv.agents.sessions.create(...)", None, "typed", "two-level gate with agents.<a>.sessions.create"),
    "agents.sessions.get": ("srv.agents.sessions.get(id)", None, "typed", ""),
    "agents.sessions.update": ("srv.agents.sessions.update(id, ...)", None, "typed", ""),
    "agents.sessions.list": ("srv.agents.sessions.list(**page)", None, "typed", ""),
    "agents.sessions.delete": ("srv.agents.sessions.delete(id)", None, "typed", ""),
    "agents.sessions.send_event": ("srv.agents.sessions.send_event(id, event)", None, "typed", "official `events.create` (202, N-2)"),
    "agents.sessions.stream_events": ("srv.agents.sessions.stream_events(id)", None, "stream", "SSE; idle-open"),
    "agents.sessions.list_items": ("srv.agents.sessions.list_items(id, **page)", None, "typed", ""),
    "agents.sessions.turns.list": ("srv.agents.sessions.turns.list(id)", None, "typed", ""),
    "agents.sessions.turns.get": ("srv.agents.sessions.turns.get(id, turn_id)", None, "typed", ""),
    "agents.sessions.turns.list_items": ("srv.agents.sessions.turns.list_items(id, turn_id)", None, "typed", ""),
    "agents.sessions.artifacts.list": ("srv.agents.sessions.artifacts.list(id)", None, "typed", ""),
    "agents.sessions.artifacts.get": ("srv.agents.sessions.artifacts.get(id, aid)", None, "typed", ""),
    "agents.sessions.artifacts.content": ("srv.agents.sessions.artifacts.content(id, aid)", None, "raw", "bytes"),
    "agents.sessions.artifacts.delete": ("srv.agents.sessions.artifacts.delete(id, aid)", None, "typed", ""),
    "agents.sessions.traces.list": ("srv.agents.sessions.traces.list(id)", None, "typed", "empty list envelope in 0.3.0"),
    "agents.sessions.subagents.list": ("srv.agents.sessions.subagents.list(id)", None, "typed", "empty list envelope"),
    "agents.sessions.subagents.get": ("raises NotSupportedError", None, "refused", "server 404 not_found_error (asymmetry A6)"),
    "agents.sessions.subagents.list_items": ("raises NotSupportedError", None, "refused", "asymmetry A6"),
    "agents.sessions.subagents.turns.list": ("raises NotSupportedError", None, "refused", "asymmetry A6"),
    "agents.sessions.subagents.turns.get": ("raises NotSupportedError", None, "refused", "asymmetry A6"),
    "agents.sessions.subagents.turns.list_items": ("raises NotSupportedError", None, "refused", "asymmetry A6"),
}
ADAPTER_OPS = {
    "run": ("srv.agents.<a>.run(prompt, ...)", "typed", "AgentScope required"),
    "install": ("srv.agents.<a>.install()", "admin", "explicit-only; 202 + job"),
    "sessions.create": ("srv.agents.<a>.sessions.create(...)", "typed", "exec-effect op; AgentScope required"),
    "sessions.send_event": ("srv.agents.<a>.sessions.send_event(id, event)", "typed", "exec-effect op"),
}
ADAPTERS = ("codex", "claude_code", "qwen_code", "cursor", "qoder")
DYNAMIC = {
    "custom.<name>": ("srv.custom.<name>(**kw) / srv.call('custom.<name>')", "Sandbox.custom(name)", "dynamic", "tree built from GET /ops (asymmetry A7)"),
    "ext.<handler>": ("srv.call('ext.<handler>')", None, "dynamic", "arbitrary legacy RouteTable routes; dynamic tree only (asymmetry A7)"),
}


def ledger() -> dict[str, tuple]:
    rows = {}
    rows.update(FILES); rows.update(BASE); rows.update(AGENTS)
    for a in ADAPTERS:
        for v, (call, kind, note) in ADAPTER_OPS.items():
            rows[f"agents.{a}.{v}"] = (call.replace("<a>", a), None, kind, note)
    return rows


def markdown() -> str:
    out = ["| Op id | Client call (generated, same tree) | envd twin | Kind | Note / asymmetry |", "|---|---|---|---|---|"]
    r = ledger()
    for k in sorted(r):
        if k.startswith("agents.") and any(k.startswith(f"agents.{a}.") for a in ADAPTERS[1:]):
            continue
        c, e, kind, n = r[k]
        out.append(f"| `{k}` | `{c}` | {e or '-'} | {kind} | {n} |")
    for k, (c, e, kind, n) in DYNAMIC.items():
        out.append(f"| `{k}` | `{c}` | {e or '-'} | {kind} | {n} |")
    return "\n".join(out)


if __name__ == "__main__":
    print(markdown())
