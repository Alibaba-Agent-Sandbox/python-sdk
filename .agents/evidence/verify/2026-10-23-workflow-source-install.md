# Verification: immutable workflow source installation recipes

Date: 2026-10-23. Result: PASS.

Runtime source under test: https://github.com/alibaba-agent-sandbox/python-sdk/commit/c8882c29fd6a84fe10f9e6791aeacd1f5c0a5131. Python 3.11.15. No cloud calls or credentials were used.

Refresh all 16 active README/install/example references from the older immutable implementation to this exact tested runtime. Historical changelog and engineering evidence are unchanged. Remove the retired declarative extra from current recipes; the YAML parser is now a core dependency. This does not claim that the source is published on PyPI or is the newest main revision.

Executed two independent fresh virtual environments with the exact paired GitHub archive URLs shown in the docs, one base client and one client[all], each with the matching server source. Both pip installations and pip check passed with no broken requirements. The base environment confirmed matching 0.3.0 distribution versions, standard synchronous/asynchronous create shapes, ProviderSandbox and interpreter/server/workflow imports, actual YAML parsing and absence of the removed declarative extra. The all environment additionally imported MCP, orjson, filelock, Starlette and Uvicorn. Neither environment used editable development dependencies.

Both matched source references must be installed together because the required matching server distribution is part of the current local server/declarative API. No unrelated package is substituted, no compatibility alias is restored and no package release is requested. The independent real OpenSandbox workflow remains its own CI execution gate.
