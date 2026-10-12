"""Catalog of built-in operations (ids, effects, group, bindings) = the data behind 04-builtin-modules.md.
Handlers for most of these are stubs in the spike; the catalog is what is validated."""
L, N = True, False   # legacy / new binding

CATALOG = [
    # id, effects, group, [(method, path, legacy)], path-params, command-param
    ("core.health", "read", "core", [("GET", "/health", L)], (), None),
    ("core.capabilities", "read", "core", [("GET", "/capabilities", L)], (), None),
    ("core.describe", "read", "core", [("GET", "/ops", N)], (), None),
    ("core.reload", "admin", "core", [("POST", "/admin/reload", N)], (), None),
    ("core.check", "read", "core", [("POST", "/capabilities/check", N)], (), None),
    ("core.openapi", "read", "core", [("GET", "/openapi.json", N)], (), None),
    ("files.list", "read", "file_ops", [("GET", "/files/list", L)], ("path",), None),
    ("files.stat", "read", "file_ops", [("GET", "/files/stat", L)], ("path",), None),
    ("files.mkdir", "write", "file_ops", [("POST", "/files/mkdir", L)], ("path",), None),
    ("files.delete", "delete", "file_ops", [("DELETE", "/files", L)], ("path",), None),
    ("files.move", "read+delete+write", "file_ops", [("POST", "/files/move", L)], ("src", "dst"), None),
    ("files.search", "read", "file_ops", [("POST", "/files/search", L)], ("path",), None),
    ("files.upload", "write", "file_ops", [("POST", "/upload", L)], ("path",), None),
    ("files.upload_stream", "write", "file_ops", [("POST", "/files/upload-stream", L)], ("path",), None),
    ("files.download", "read", "file_ops", [("GET", "/download", L)], ("path",), None),
    ("files.download_stream", "read", "file_ops", [("GET", "/files/download-stream", L)], ("path",), None),
    ("files.archive", "read+write", "file_ops", [("POST", "/files/archive", L)], ("paths", "dest"), None),
    ("files.watch", "read", "file_ops", [("GET", "/files/watch", N)], ("path",), None),
    ("commands.run", "exec", "process", [("POST", "/shell", L)], ("cwd",), "command"),
    ("commands.stream", "exec", "process", [("POST", "/shell/stream", L)], ("cwd",), "command"),
    ("process.start", "exec", "process", [("POST", "/process/start", L)], ("cwd",), "command"),
    ("process.list", "read", "process", [("GET", "/process/list", L)], (), None),
    ("process.get", "read", "process", [("GET", "/process/{pid}", L)], (), None),
    ("process.signal", "exec", "process", [("POST", "/process/{pid}/signal", L)], (), None),
    ("process.stdin", "exec", "process", [("POST", "/process/{pid}/stdin", N)], (), None),
    ("process.output", "read", "process", [("GET", "/process/{pid}/output", N)], (), None),
    ("terminal.create", "exec", "terminal", [("POST", "/pty/sessions", L)], ("cwd",), "command"),
    ("terminal.list", "read", "terminal", [("GET", "/pty/sessions", L)], (), None),
    ("terminal.get", "read", "terminal", [("GET", "/pty/sessions/{id}", N)], (), None),
    ("terminal.resize", "exec", "terminal", [("POST", "/pty/sessions/{id}/resize", N)], (), None),
    ("terminal.delete", "delete", "terminal", [("DELETE", "/pty/sessions/{id}", L)], (), None),
    ("terminal.connect", "exec", "terminal", [("WS", "/pty/{id}", N)], (), None),
    ("system.info", "read", "system", [("GET", "/system/info", L)], (), None),
    ("system.metrics", "read", "system", [("GET", "/system/metrics", L)], (), None),
    ("system.env.get", "read", "system", [("GET", "/env", L)], (), None),
    ("system.env.set", "admin+write", "system", [("POST", "/env", L)], (), None),
    ("system.ports", "read", "system", [("GET", "/ports", L)], (), None),
    ("system.packages", "read", "system", [("GET", "/packages", L)], (), None),
    ("devtools.code.run", "exec+write", "dev_tools", [("POST", "/code/run", L)], (), None),
    ("devtools.git.status", "read+exec", "dev_tools", [("GET", "/git/status", L)], ("path",), None),
    ("devtools.git.diff", "read+exec", "dev_tools", [("GET", "/git/diff", L)], ("path",), None),
    ("browser.navigate", "net", "browser", [("POST", "/browser/navigate", L)], (), None),
    ("browser.screenshot", "read", "browser", [("POST", "/browser/screenshot", L)], (), None),
    ("browser.content", "read", "browser", [("GET", "/browser/content", L)], (), None),
    ("browser.click", "exec", "browser", [("POST", "/browser/click", L)], (), None),
    ("browser.type", "exec", "browser", [("POST", "/browser/type", L)], (), None),
    ("browser.evaluate", "exec", "browser", [("POST", "/browser/evaluate", L)], (), None),
    ("browser.pdf", "read", "browser", [("POST", "/browser/pdf", L)], (), None),
    ("browser.console", "read", "browser", [("GET", "/browser/console", L)], (), None),
    ("custom.list", "read", "commands", [("GET", "/commands", L)], (), None),
]

ADAPTERS = ("codex", "claude_code", "qwen_code", "cursor", "qoder")
EXPERIMENTAL_ADAPTERS = ("qwen_code", "cursor", "qoder")
# Op IDs that are explicit-only on the ALLOW side (never reached by wildcard/group/effect selectors).
EXPLICIT_IDS = {"core.reload", "system.env.set", "terminal.create", "process.signal"}
URL_OPS = {"browser.navigate": ("url",)}

# Runtime/discovery ops (not part of the official OpenAI surface).
AGENT_GENERIC = [
    ("agents.runtimes.list", "read", [("GET", "/agents/runtimes", L)]),
    ("agents.runtimes.doctor", "read+exec", [("POST", "/agents/runtimes/{name}/doctor", N)]),
    ("agents.models.list", "read", [("GET", "/v1/models", N)]),
]
# Per-adapter family (policy-addressable backends).  suffix, effects, agent_scope, explicit
AGENT_FAMILY = [
    ("run", "exec+net", True, False),
    ("install", "net+exec+admin", False, True),
    ("sessions.create", "exec+net", True, True),
    ("sessions.send_event", "exec+net", True, False),
]
# The 47 official routes: sdk method -> (op id | None, tier).  Tier 1 = ships in 0.3.0; R = id reserved;
# X = answers 404 not_found_error (refused); N = not planned (no op id, 404 not_found_error).
OFFICIAL_47 = [
    ("agents.create", "agents.definitions.create", 1), ("agents.retrieve", "agents.definitions.get", 1),
    ("agents.update", "agents.definitions.update", 1), ("agents.list", "agents.definitions.list", 1),
    ("agents.delete", "agents.definitions.delete", 1),
    ("agents.environments.create", "agents.environments.create", 1),
    ("agents.environments.retrieve", "agents.environments.get", 1),
    ("agents.environments.list", "agents.environments.list", 1),
    ("agents.environments.files.create", "agents.environments.files.create", "R"),
    ("agents.environments.files.list", "agents.environments.files.list", "R"),
    ("agents.environments.templates.create", None, "N"), ("agents.environments.templates.retrieve", None, "N"),
    ("agents.environments.templates.update", None, "N"), ("agents.environments.templates.list", None, "N"),
    ("agents.environments.templates.delete", None, "N"),
    ("agents.sessions.create", "agents.sessions.create", 1), ("agents.sessions.retrieve", "agents.sessions.get", 1),
    ("agents.sessions.update", "agents.sessions.update", 1), ("agents.sessions.list", "agents.sessions.list", 1),
    ("agents.sessions.delete", "agents.sessions.delete", 1),
    ("agents.sessions.events.create", "agents.sessions.send_event", 1),
    ("agents.sessions.events.stream", "agents.sessions.stream_events", 1),
    ("agents.sessions.items.list", "agents.sessions.list_items", 1),
    ("agents.sessions.turns.list", "agents.sessions.turns.list", 1),
    ("agents.sessions.turns.retrieve", "agents.sessions.turns.get", 1),
    ("agents.sessions.turns.items.list", "agents.sessions.turns.list_items", 1),
    ("agents.sessions.artifacts.list", "agents.sessions.artifacts.list", 1),
    ("agents.sessions.artifacts.retrieve", "agents.sessions.artifacts.get", 1),
    ("agents.sessions.artifacts.content", "agents.sessions.artifacts.content", 1),
    ("agents.sessions.artifacts.delete", "agents.sessions.artifacts.delete", 1),
    ("agents.sessions.traces.list", "agents.sessions.traces.list", 1),
    ("agents.sessions.subagents.list", "agents.sessions.subagents.list", 1),
    ("agents.sessions.subagents.retrieve", "agents.sessions.subagents.get", "X"),
    ("agents.sessions.subagents.items.list", "agents.sessions.subagents.list_items", "X"),
    ("agents.sessions.subagents.turns.list", "agents.sessions.subagents.turns.list", "X"),
    ("agents.sessions.subagents.turns.retrieve", "agents.sessions.subagents.turns.get", "X"),
    ("agents.sessions.subagents.turns.items.list", "agents.sessions.subagents.turns.list_items", "X"),
    ("agents.vaults.create", None, "N"), ("agents.vaults.retrieve", None, "N"), ("agents.vaults.update", None, "N"),
    ("agents.vaults.list", None, "N"), ("agents.vaults.delete", None, "N"),
    ("agents.vaults.credentials.create", None, "N"), ("agents.vaults.credentials.retrieve", None, "N"),
    ("agents.vaults.credentials.update", None, "N"), ("agents.vaults.credentials.list", None, "N"),
    ("agents.vaults.credentials.delete", None, "N"),
]

GROUP_OF_NAMESPACE = {"core": "core", "files": "file_ops", "commands": "process", "process": "process",
                      "terminal": "terminal", "system": "system", "devtools": "dev_tools", "browser": "browser",
                      "custom": "commands", "ext": "commands", "agents": "agents"}
