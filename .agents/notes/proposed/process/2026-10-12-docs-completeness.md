# Decision: Documentation completeness for CLI and Python SDK user guides

Status: proposed

## Problem

The maintainer asked for best-practice guides, an operations page, provider authoring (including the `[template]` table and install-from-git), and SDK docs for the Agents API and fine-grained file/command controls, in English and Chinese, plus one runnable local example. Several of those pages were missing; provider authoring and the Agents API pages existed but were thin or had no best-practices section.

## Decision

Add only the missing user-facing pages. Extend pages that already existed when a requested section was thin. Link the new pages from the docs indexes and the repository READMEs. Do not rewrite accurate references.

| Requested doc | Existed? | Path added or extended |
|---|---|---|
| CLI best practices (`--provider`, `--model`, `llm_model`, credentials, standalone binary) | No | Added `cli/docs/en/guide/best-practices.md`, `cli/docs/zh/guide/best-practices.md` |
| CLI provider authoring, `[template]` table and install-from-git | Yes, both sections were thin | Extended `cli/docs/en/guide/authoring-providers.md`, `cli/docs/zh/guide/authoring-providers.md` (sections 4 and 5) |
| CLI operations (every command group, one command per job, links to the reference) | No | Added `cli/docs/en/guide/operations.md`, `cli/docs/zh/guide/operations.md` |
| SDK best practices (provider-free server, capability groups, agents opt-in, secrets not echoed) | No | Added `python-sdk/docs/en/guide/best-practices.md`, `python-sdk/docs/zh/guide/best-practices.md` |
| SDK fine-grained file and command control | Design doc only (`docs/en/design/fine-grained-capabilities.md` and the zh mirror). No user guide. | Added `python-sdk/docs/en/guide/file-and-command-controls.md`, `python-sdk/docs/zh/guide/file-and-command-controls.md`. States that `guards/paths.py` and `guards/commands.py` are not called from `routes.py` or `routes_files.py`. |
| Agents API | Yes: `docs/{en,zh}/guide/hosted-agents.md` and `docs/{en,zh}/guide/template-server-api.md` | Added a Best practices section to both `hosted-agents.md` files (Codex and Qwen only, `X-Easy-Sandbox-Local`, 404 for Claude/Cursor/Qoder and for `input_tokens`). One-line link from both `template-server-api.md` files. |
| Runnable example: local server, files, one agent session, fake CLI, no API key | `examples/agents/hosted_codex.py` and `hosted_qwen.py` talk to a server you start; they do not upload a file or install a fake CLI. The fake-CLI pattern was not in the README. | Added `python-sdk/examples/agents/local_files_and_session.py`. Extended `python-sdk/examples/agents/README.md` with the fake-CLI pattern. Linked from `examples/README.md` and `examples/README.zh-CN.md`. |
| Indexes and READMEs | Yes | Short links added in `cli/docs/{en,zh}/README.md`, `cli/README.md`, `cli/README.zh-CN.md`, `python-sdk/docs/{en,zh}/README.md`, `python-sdk/README.md`, `python-sdk/README.zh-CN.md`. Also corrected one sentence in `python-sdk/docs/{en,zh}/guide/authoring-templates.md` that said the agents group has no routes. |

## API Design

N/A — documentation and one example client. No server, CLI, or e2e test change.

## Alternatives considered

- A new API reference that repeats `cli-reference.md`, `api-reference.md`, and `template-server-api.md`. Rejected: those pages are already the method and route references. The operations page links to them.
- Document `path_guard()` and `CommandGuard` as template flags. Rejected: `routes.py` still uses `_check_command` (fnmatch on `argv[0]`) and `routes_files.py` uses `EndpointContext.guard()` / `PathGuard`. The v2 constructors are not wired in.

## Dependencies

Read-only: `cli/src/cli/_shortcut_table.ts`, `cli/src/providers/template_profile.ts`, `python-sdk/server-sdk/src/easy_sandbox/server/routes.py`, `routes_files.py`, `policy.py`, `guard.py`, `guards/`, `router.py`.

## Test Strategy

`python examples/agents/local_files_and_session.py` against a server the script starts. Documentation links are relative paths that exist in the tree. No unit test asserts prose.

## Acceptance criteria

- English and Chinese copies of each new guide.
- Provider authoring states required `[template]` fields and the git install flags (`--ref`, `--subdir`, `--yes`, `--allow-unpinned`, `--sha256`).
- The file/command guide matches the route code and says which guards are not wired.
- The example uploads a file, reads it back, and completes one Codex turn with the fake CLI and no API key.
