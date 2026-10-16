# Repository Layout Review: `python-sdk` and `cli`

> Status: **recommendation** (architecture review, 2026-10-12) - written read-only against the
> staging tree `/workspace` and the pristine original (`b15b88f`, v0.2.0). Maintainer-facing, English only.
> The CLI-side copy of the parts that concern the Node.js repository lives in the `cli` repository
> (`docs/design/repository-layout.md`). Each repository carries its own copy; they are not kept byte-identical.
>
> **Status on 2026-10-13.** Proposals that were carried out: the two distributions with the shared namespace and the
> hard `agent-sandbox-server==0.3.0` pin, one docs tree, one `.agents/`, `check-repo-health.sh`, benchmarks under
> `client-sdk/benchmarks/`, no cloud E2E scripts under `scripts/e2e/` (the pytest suite in `e2e/` replaces them).
> Proposals that were **not** carried out, so the tables below describe a target rather than the tree: there is no
> `scripts/release.py` (the two `_version.py` files and the pin are bumped by hand; `scripts/check_dists.py` checks the
> built wheels); `ci.yml` has the jobs `hygiene`, `client-sdk`, `server-sdk` and `build` only (no `upgrade-from-0.2`
> or `repo-health` job); `server-sdk/tests/test_server/` is not flattened and the `tests/__init__.py` files remain.
> The client has since lost its build pipeline (`api/docker_builder.py`, deploy helpers), the built-in agents and
> `Sandbox.custom()`; the server has one `ENDPOINTS` table and no `server/core/` or `/ops`. The measurements are
> from 2026-10-12 and are left as they were.
>
> Evidence below is measured, not assumed. Experiments were run in throw-away virtualenvs under
> `/tmp/layout-exp` (wheel builds of the original and of both new distributions, real `pip` resolver).

## 0. Verdict in ten lines

1. **Keep two PyPI distributions in one repo, keep the shared `agent_sandbox` namespace** (client owns
   `agent_sandbox/__init__.py` with `extend_path`, server ships only `agent_sandbox/server/`). It is the only
   option that keeps both `from agent_sandbox import ProviderSandbox as Sandbox` and `from agent_sandbox.server import ...` working
   with zero shims. Rejected: `agent_sandbox_server` + compat shim (permanent shim, double module identity or
   finder hacks), single dist with extras (image bloat).
2. **Make `agent-sandbox` hard-depend on `agent-sandbox-server==<same version>`** (today it is only the optional
   `[server]` extra). Otherwise `pip install agent-sandbox` stops providing `agent_sandbox.server`, which every
   template Dockerfile written for 0.2.x relies on. Cost: +53 KB wheel, zero new third-party dependencies.
3. **Release the split as 0.3.0, never 0.2.x**: `agent-sandbox` 0.1.0 and 0.2.0 already exist on PyPI as a single
   distribution containing the server. The new wheels currently also say 0.2.0 (name collision on upload).
4. **An in-place `pip install -U agent-sandbox` from 0.2.0 silently breaks `agent_sandbox.server`** (verified,
   section 2.1). Ship the mitigation (actionable error, upgrade note, CI job) with 0.3.0.
5. **python-sdk keeps ONE docs tree at the repo root** (`docs/{en,zh}`), one root README, per-package READMEs
   (they are the PyPI long descriptions), one CHANGELOG, one `.agents/`, one CI, one release script.
6. **No page exists in two repositories.** Each page has exactly one owning repo; the other links to it with an
   absolute URL. Contract pages (template.yaml spec, error codes, server HTTP API) are owned by python-sdk.
7. **`.agents/` is split by code ownership, not duplicated**, `.agents/README.md` is added to both repos, ADR
   cross-references become absolute URLs, evidence/research stop being git-ignored, personal paths are scrubbed.
8. **CLI repo (see its copy of this doc)**: keep the Python-mirroring `src/` tree only until the parity gate;
   then one mechanical commit re-homes it to `src/{bin,cli,core,agent,providers,pyparity}`. No npm workspace yet.
9. **Publish as two repos without an umbrella monorepo**: the CLI keeps the existing `agent-sandbox/agent-sandbox`
   repository (stars/issues/tags `v0.1.0`/`v0.2.0` stay; the Node rewrite lands as one commit), and the SDK is a new
   repository `agent-sandbox/python-sdk` created from a `git filter-repo` of the SDK-owned history. `/workspace` is a
   disposable staging area.
10. `scripts/check-repo-health.sh` (added to both repos) encodes the definition of done; run it in CI.

## 1. What exists today (measured)

| Fact | Evidence |
|------|----------|
| Original: one package `agent_sandbox` incl. `cli/` and `server/`, 622 tracked files, 18 commits, tags `v0.1.0`, `v0.2.0` | `/tmp/agent-sandbox` |
| `agent-sandbox` 0.1.0 and 0.2.0 are on PyPI (single dist, server inside); `agent-sandbox-server` is **404 (free)** | `https://pypi.org/pypi/<name>/json` |
| npm: `@agent-sandbox/cli` unpublished; unscoped `abx` is **taken** by a third party; scope `agent-sandbox` ownership unverified | npm registry |
| GitHub org `alibaba-agent-sandbox` has `agent-sandbox` (1 star, 5 open issues, homepage agent-sandbox.com), `awesome-templates`, `.github` (profile README only; it still links to the stale `serverless-sandbox` org) | GitHub API |
| New wheels still carry version **0.2.0** (client `_version.py`, server `_version.py`) | both files |
| Both new wheels build; client wheel has 0 files under `agent_sandbox/server`, server wheel has no `agent_sandbox/__init__.py` | built under `/tmp/layout-exp` |
| Editable install of both (`pip install -e server-sdk -e client-sdk`) works; `agent_sandbox.__path__` lists both `src/agent_sandbox` dirs; `mypy src/agent_sandbox/server` is clean; `mypy src/agent_sandbox` (client) reports only missing optional extras (starlette), no namespace errors | experiment e6 |
| Server-only environment: 1 third-party package (`websockets`), 14 MB site-packages; client-only: 18 packages, 31 MB | experiments e5/e7 |
| Wheels: client 172 KB, server 53 KB | experiment |
| 13 doc pages (26 files, en+zh) were **byte-identical** in both repos when this review started (getting-started, authentication, authoring-templates, environment-variables, mcp-integration, troubleshooting, configuration, error-codes, template-yaml-spec, template-system, mcp-server, DESIGN, README); builders have reduced this, the checker tracks the remainder | `cmp` |
| `.agents`: python-sdk 36 ADRs + 4 research + 10 evidence files; cli 52 ADRs + 1 design + 1 research + 24 evidence files | file counts |
| Cross-repo dangling ADR slugs: python-sdk references 12 ADRs that now live in `cli` (23 files); cli references 16 ADR/evidence slugs that live in python-sdk (15 files). `.agents/evidence/README.md` in python-sdk lists CLI evidence files that are not there; the two `research/README.md` files are identical but each links to the other repo's files | link scan |
| Machine-local paths shipped in text: `/Users/anycodes/...Qoder...` in cli scripts, benchmark, SKILL, READMEs, evidence; `/tmp/agent-sandbox`, `/tmp/venv-orig`, "this VM" in `cli/docs/PORTING.md` | grep |
| `python-sdk/.gitignore` ignores `/.agents/evidence/` and `/.agents/research/` although the original force-tracked them: a fresh `git add` of the published repo silently drops 14 files | `git ls-files` in the original |
| `cli/` has **no `.gitignore`**, `node_modules` is a symlink to `/tmp/parity/node_modules`, no `package-lock.json`, `package.json` lacks `typescript`/`vitest`/`@types/node` devDependencies and (at review time) `yaml`/`smol-toml`/`ws`/`@inquirer/prompts`, `repository.url` is the old repo, no `.github/workflows/`, `dependabot.yml` still lists `pip`, `benchmarks/bench_cli_startup.py` and three `scripts/*.sh` still call the Python CLI with a hard-coded `/Users/anycodes` path | `cli/` |

## 2. Decision A - Python packaging layout

### 2.1 Options

| | A. Shared namespace, two dists (current) | B. Distinct import packages (`agent_sandbox` + `agent_sandbox_server`) + compat shim | C. One dist with extras | D. Two dists, other repo layout (flat / `packages/`) |
|---|---|---|---|---|
| Import compat (`agent_sandbox.server`) | native, no shim | needs a permanent shim (alias finder or re-export of ~12 submodules) | native | same as A |
| Template image size | server-only: 1 dep, 53 KB wheel | same as A | full client stack (httpx, pydantic, dotenv...) in every image unless client deps move to extras, which breaks `pip install agent-sandbox` | same as A |
| editable / hatch / uv | works (verified: two `.pth` entries, `extend_path`) | trivial | trivial | same as A |
| mypy / IDE | works with both dists installed; client-only checkout lacks `agent_sandbox.server` stubs unless server is installed | needs a stub package for the shim path | trivial | same as A |
| In-place upgrade from PyPI 0.2.0 | **breaks** (see below) | safe (real code moves to a new path) | safe | same as A |
| "src has `agent-sandbox` and `server`?" confusion (owner concern) | two `src/` trees both containing `agent_sandbox/` - needs one explanatory README paragraph | self-explanatory tree | one tree | n/a |
| Ongoing cost | none, one hazard at 0.3.0 | shim forever, double-identity risk (`registry` singletons) | none | none |
| Migration cost | ~0 (done) + hazard mitigation | high: rewrite templates/docs/tests, shim, stubs | medium: merge back, drop 0.2.x split work | low (git mv) |

**Experiment (real pip resolver)**: `agent-sandbox==0.2.0` (PyPI single dist) installed, then
`pip install -U agent-sandbox` with a 0.3.0 client that depends on `agent-sandbox-server==0.3.0`:

```text
Uninstalling agent-sandbox-0.2.0 ... Successfully installed agent-sandbox-0.3.0 agent-sandbox-server-0.3.0
>>> from agent_sandbox.server import start
ImportError: cannot import name 'start' from 'agent_sandbox.server' (unknown location)
```

pip installs the dependency (server) first and only then uninstalls old `agent-sandbox`, whose RECORD still lists
`agent_sandbox/server/*`; the freshly installed server files are deleted and `agent_sandbox.server` degrades to an
empty implicit namespace (import "succeeds", attributes are missing). Remedy verified:
`pip install --force-reinstall --no-deps agent-sandbox-server` restores it. A fresh environment is fine.

### 2.2 Recommendation: **A**, with these amendments

1. `client-sdk/pyproject.toml`: add `"agent-sandbox-server==<version>"` to `dependencies` (release script keeps
   it equal to the version); keep the `server` extra as an empty-compatible alias (`server = []`).
2. Bump both to **0.3.0** (`0.2.0` is immutable on PyPI). The split is a breaking release (CLI extra removed too).
3. Mitigate the upgrade hazard: (a) the lazy `@sandbox` server proxy and `agent_sandbox.server` consumers turn the
   empty-namespace `ImportError` into an actionable message naming the `--force-reinstall` remedy; (b) an
   "Upgrading from 0.2.x" box in README, CHANGELOG, troubleshooting; (c) CI job `upgrade-from-0.2`: venv, install
   released `agent-sandbox==0.2.0`, install the freshly built wheels, assert `from agent_sandbox.server import start`
   (the job documents/pins the behaviour; flip it to "must pass without remedy" only if a fix is ever found).
4. Template Dockerfiles install `agent-sandbox-server` (already changed in `examples/templates/python-hello`);
   `pip install agent-sandbox` stays valid for old templates because of amendment 1.
5. Two hand-synced copies exist (`client-sdk/.../utils/coerce.py` and `server-sdk/.../server/_coerce.py`):
   add a CI test that fails if their bodies drift.
6. Why not "A without the `__init__`" (pure PEP 420)? `from agent_sandbox import ProviderSandbox as Sandbox` is public API, so the
   client must own an `__init__.py`; the hybrid (regular package + `extend_path`) is forced, and tested above.
7. Re-evaluate B only if a second family of server-side libraries appears (e.g. `agent_sandbox.server.*` plugins
   published by third parties), where a real distinct top-level name pays off. Not now.

### 2.3 src-layout and tooling alternatives (decided)

* Keep per-package `src/` layout (prevents accidentally importing un-installed source; matches hatch defaults).
  Rejected: flat layout (tests would import the source tree, hiding packaging bugs such as a missing `py.typed`).
* Keep `client-sdk/` and `server-sdk/` as directory names (alternatives `packages/client`, `packages/server`
  add a level without adding meaning).
* Add a **tooling-only root `pyproject.toml`** with `[tool.uv.workspace] members = ["client-sdk", "server-sdk"]`
  and shared ruff settings. `pip install -e ./server-sdk -e ./client-sdk[dev]` (`make dev`) keeps working; uv gets
  one-command sync and a committed `uv.lock` for reproducible CI. The root file has no `[project]`, so it can never
  be published by accident.
* Tests: per package (`<pkg>/tests`). Flatten `server-sdk/tests/test_server/` to `server-sdk/tests/`. Remove
  `tests/__init__.py` from both packages (two packages named `tests` collide under one pytest run) and use
  `--import-mode=importlib`. Root `make test` still runs the packages separately, like CI.

## 3. Decision B - python-sdk repo content

| Area | Decision | Reason |
|------|----------|--------|
| README | one root `README.md` + `README.zh-CN.md` (what, two-package table, install, quick start, docs map, link to CLI repo) **and** `client-sdk/README.md`, `server-sdk/README.md` (PyPI long descriptions, install + minimal example + link to docs) | PyPI renders the package README; GitHub renders the root one |
| Docs | one tree `docs/{en,zh}/{guide,reference,explanation,design}`; add `guide/server-sdk.md` (authoring `commands.py`), `guide/release.md` (maintainers); docs index drops "coming soon" for pages that exist | owner asked for complete docs in python-sdk; one tree avoids per-package drift |
| Examples | root `examples/` (they span both packages: quickstart, agents, compat-demos, templates) | an example imports client and builds a server image |
| Tests | per package; `integration/` behind the `integration` marker | independent test runs, per-dist coverage |
| Scripts | `scripts/{check_dists.py,check-repo-health.sh,check-no-local-paths.sh,e2e-cleanup.py}` (the build-and-deploy E2E scripts were removed with the client-side build pipeline; `release.py` was proposed and not written) | maintainer tooling only |
| Benchmarks | move to `client-sdk/benchmarks/`, drop `__init__.py` | they only measure the client (`bench_create`, `bench_import`) |
| ADR/`.agents` | one `.agents/` at the repo root (decisions concern both packages) | see Decision D |
| CI | one `ci.yml`: `hygiene`, `client-sdk` and `server-sdk` matrix jobs (3.10-3.12), `build` job, and a scheduled `docs-links.yml` (lychee); `upgrade-from-0.2` and a required `repo-health` job are still proposals | root orchestration without hiding per-package failures |
| Shared tooling | root `Makefile`, `.pre-commit-config.yaml`, `.githooks/`, `.secrets.baseline`, `.editorconfig`, shared `ruff.toml` extended by both packages | one place to change |
| Version lockstep | **`scripts/release.py`** (proposed, not written; bumped by hand today): `bump X.Y.Z` rewrites both `_version.py`, the `agent-sandbox-server==` pin and the CHANGELOG heading; `check` is used by CI and `publish.yml` (replaces the inline Python there). Not a single `VERSION` file: building the sdist of one package alone could not see `../VERSION`. | one command, verifiable, sdist-safe |
| Release | PR `chore(release): X.Y.Z` -> tag `vX.Y.Z` -> GitHub Release -> `publish.yml` (PyPI trusted publishing via OIDC, `pypa/gh-action-pypi-publish`, server first, then client; no PyPI token) -> post-publish smoke install from PyPI | single tag for both lockstep dists |
| Community files | `.github/{CODE_OF_CONDUCT,CONTRIBUTING,SECURITY,PULL_REQUEST_TEMPLATE,dependabot,CODEOWNERS}`, issue forms, discussion templates stay in each repo (self-contained); the org `.github` repo only provides fallbacks | independent repos must be complete on their own |

### 3.1 Shared documentation: one owner per page

Rule: **a page lives where the code it documents lives; contract pages live in python-sdk; the other repo
links with an absolute URL; byte-identical copies are forbidden (checked by the health script).**

| Page (en + zh) | Owner | Other repo |
|----------------|-------|------------|
| `reference/template-yaml-spec`, `reference/error-codes` (E1xxx-E6xxx taxonomy), `reference/server-http-api`, `design/server-api`, `design/template-system` (schema half) | **python-sdk** | CLI links (CLI keeps only CLI-specific codes such as `E2007` and the exit-code map) |
| `guide/getting-started`, `guide/authentication`, `guide/environment-variables`, `guide/troubleshooting`, `reference/configuration`, `guide/mcp-integration` | **each repo owns its own, trimmed version** (SDK: Python API, `api_key=`, `Sandbox`; CLI: `abx config`, flags, exit codes). The shared credential precedence table is authored once in python-sdk `reference/configuration` and linked from the CLI page | no duplicated sections |
| `guide/authoring-templates` | **cli** (workflow: `abx template scaffold/deploy`) with a link to python-sdk `guide/server-sdk` for the `commands.py` API | link |
| `design/mcp-server` | **python-sdk** (`agent_sandbox.agent.mcp`) | CLI documents `abx mcp install` and links |
| `DESIGN.md`, `README.md` indexes | each repo, listing only its own pages plus a "Related documentation" section | link |

## 4. Decision C - CLI repository (summary; full detail in the `cli` copy)

* Today `src/` mirrors the Python tree (`models/utils/transport/protocol/api/session/agent/cli/commands`) plus
  `framework/` and seven underscore-prefixed Python-emulation helpers scattered over modules (`_py`, `_pycompat`,
  `_pyerrors`, `_shlex`, `_pyformat`, `_pypath`, `_pydantic`, ...). That is right **for the port** (traceability,
  parity ledger of 1351 tests keyed by `tests/<python path>`), wrong as a public layout.
* **Now**: do not move anything; only add what the repo lacks (`.gitignore`, lockfile, devDependencies, CI/release
  workflows, lint config, entry `src/bin/abx.ts`). New non-ported code (providers, plugin host) goes into new
  directories (`src/providers/`, `src/core/provider/`), never into the mirrored ones.
* **After the parity gate** (ledger 100% matched and no skips, differential harness clean, adversarial review
  signed, tag `parity-v1`): one mechanical commit (pure `git mv` + codemod, no logic edits, tests green before
  and after) to `src/{bin,cli,core,agent,providers,pyparity}` (tree in section 6). No npm workspace until a second
  package exists (planned: `@agent-sandbox/provider-api`, the types a third-party provider plugin imports).

## 5. Decision D - `.agents/`

Current split (from `/tmp/parity/agents-split.txt`): CLI got `design/`, `evidence/cli/**`, 2 research audits, 1 verify
note, 1 research note, 52 ADRs; SDK got 6 research audits, 4 verify runs, 4 research notes, 36 ADRs.
The split is directionally right (ADRs follow the code), but:

1. **Add `.agents/README.md` to both repos** (missing): what `notes/`, `evidence/`, `research/`, `design/` are,
   that ADRs are English, dated, `Status` equals directory, and that a file lives where the code that the decision
   changed lives. The three README files are currently byte-identical copies in both repos
   (`notes/README.md` is fine to share; `evidence/README.md` and `research/README.md` describe the wrong repo).
2. **Fix indices**: python-sdk `evidence/README.md` documents the CLI evidence suite (belongs to the CLI repo, and
   even there it is a generator header for a script that no longer exists); python-sdk `research/README.md`
   links `mcp-and-agent-integration.md` (CLI); cli `research/README.md` links four SDK files.
3. **ADR numbering**: ADRs are date-slugged, not numbered. Keep it: two repos cannot collide on numbers, and a slug
   is a stable key across repos. Add a generated `notes/INDEX.md` per repo (table: date, slug, state, category).
4. **Re-home ADRs to the repo that owns the contract** (history-preserving: both repos descend from the original):
   * cli -> python-sdk: `2026-09-02-transport-config` (documents `transport/config.py`),
     `2026-09-09-server-command-registry` (server module), `2026-09-03-custom-commands-schema` (template.yaml schema
     owned by `models/template.py`), `2026-09-09-docker-builder-acr-push` (origin of `DockerBuilder`).
   * python-sdk -> status fix: `2026-09-04-pypi-packaging-decisions` and `2026-09-03-release-publish-flow` are
     `proposed` but describe a single-dist world; mark superseded by the new ADR below.
   * cli -> mark superseded: `2026-09-04-single-distribution-cli-extra` (the `[cli]` extra no longer exists).
   * Extend the lifecycle with a `superseded/` state (`Superseded-by:` line) in both `notes/README.md` files.
5. **Cross-repo references become absolute URLs** (`https://github.com/alibaba-agent-sandbox/<repo>/blob/main/.agents/notes/...`),
   never `../`, never a bare slug. The health script fails on dangling slugs.
6. **Stop ignoring `evidence/` and `research/`** (remove the two lines from `.gitignore`); scrub `/Users/anycodes`,
   `file:///`, `Qoder` paths from them (replace by `<repo>/...`).
7. **New ADR in each repo** recording this decision: `2026-10-12-repository-split-and-layout` (python-sdk),
   `2026-10-12-cli-repository-layout` (cli), each linking this document.

## 6. Recommended layouts

### 6.1 `python-sdk` (GitHub `agent-sandbox/python-sdk`, a new repository split out of `agent-sandbox/agent-sandbox`)

```text
python-sdk/
├── README.md  README.zh-CN.md          # product + two-package table + docs map + link to agent-sandbox/agent-sandbox
├── LICENSE  NOTICE  CHANGELOG.md       # one Keep-a-Changelog file, entries tagged [client] / [server]
├── AGENTS.md  llms.txt
├── agent-sandbox-sdk/                  # Agent Skill (folder name matches frontmatter name)
│   ├── SKILL.md
│   └── references/templates.md
├── pyproject.toml                      # tooling-only: uv workspace + shared ruff; no [project]
├── ruff.toml  Makefile  .python-version  .editorconfig  .env.example
├── .pre-commit-config.yaml  .githooks/  .secrets.baseline  .gitignore
├── client-sdk/                         # PyPI `agent-sandbox`   (import agent_sandbox)
│   ├── pyproject.toml  README.md  LICENSE  NOTICE
│   ├── src/agent_sandbox/               # __init__.py (extend_path), _version.py, py.typed
│   │   └── models transport protocol api session declarative extensions compat providers agent utils   # agent/ = MCP + tools only
│   ├── tests/                          # conftest.py, test_<pkg>/..., integration/
│   └── benchmarks/
├── server-sdk/                         # PyPI `agent-sandbox-server` (import agent_sandbox.server)
│   ├── pyproject.toml  README.md  LICENSE  NOTICE
│   ├── src/agent_sandbox/server/        # NO agent_sandbox/__init__.py ; py.typed, _version.py
│   └── tests/                          # test_server/ (not flattened yet), test_packaging.py ...
├── docs/
│   ├── README.md                       # language chooser
│   ├── en/  guide/ reference/ explanation/ design/      # incl. design/repository-layout.md (en only)
│   └── zh/  guide/ reference/ explanation/ design/
├── e2e/                                # pytest suites against a real platform and a local server
├── examples/                           # quickstart/ agents/ compat-demos/ providers/ scenarios/ templates/
├── scripts/                            # check_dists.py  check-repo-health.sh  check-no-local-paths.sh  e2e-cleanup.py
├── .agents/                            # README.md  notes/{proposed,implemented,rejected,superseded}/  research/  evidence/
└── .github/                            # workflows/{ci,publish,docs-links}.yml  ISSUE_TEMPLATE/  CODEOWNERS  SECURITY.md  ...
```

### 6.2 `cli` (GitHub `agent-sandbox/agent-sandbox`, npm `@agent-sandbox/cli`)

Target after the parity gate (the "now" tree is the same minus the `src/` re-home; see the CLI copy):

```text
cli/
├── README.md  README.zh-CN.md  LICENSE  NOTICE  CHANGELOG.md  AGENTS.md  llms.txt  SKILL.md
├── package.json  package-lock.json  tsconfig.json  tsconfig.build.json  vitest.config.ts
├── eslint.config.js  .editorconfig  .nvmrc  .gitignore  .env.example  .githooks/  .secrets.baseline
├── src/
│   ├── bin/abx.ts                      # entry (built to dist/bin/abx.js)
│   ├── cli/                            # main.ts output.ts commands/  framework/
│   ├── core/                           # models transport protocol api session utils provider/   (never imports cli/ or agent/)
│   ├── agent/                          # MCP server, coding-agent integration, template authoring
│   ├── providers/                      # builtin alicloud provider + plugin host
│   └── pyparity/                       # Python-emulation shims, deleted when no longer needed
├── tests/{unit,integration,golden,e2e}/   # unit mirrors the new src tree
├── parity/                             # ledger + ledger-map.json (frozen, archived into docs/porting after the gate)
├── docs/{README.md, en/{guide,reference,design}, zh/..., design/repository-layout.md}
├── examples/  scripts/  benchmarks/  .agents/  .github/
```

## 7. Decision E - publishing two repositories

* **No umbrella monorepo.** `/workspace` becomes a disposable staging area; it contains only `cli/`, `python-sdk/`
  and a one-paragraph `README.md` ("staging; do not publish"). It must hold no shared docs, no shared CI.
* **cli** keeps the existing repository `agent-sandbox/agent-sandbox` (decided by the maintainer): its stars, issues,
  tags `v0.1.0`/`v0.2.0` and the PyPI 0.1/0.2 project metadata stay there. Create `split/abx-node`, replace the
  working tree with `/workspace/cli` (`rsync -a --delete --exclude .git`), `git add -A` in ONE commit, open a PR,
  tag `v0.3.0` after the release PR. The README names `v0.2.0` as the last Python `abx`. Python-only history
  (`src/agent_sandbox/...`) remains reachable in the same repository's earlier commits. First npm release `0.3.0`,
  versioned independently from the SDK (only the wire protocol couples them; list compatible ranges in the README).
* **python-sdk** is a NEW repository `agent-sandbox/python-sdk`: `git clone --no-local <original> python-sdk-export
  && git filter-repo` keeping SDK-owned paths (so `git log --follow` for `src/agent_sandbox/...` survives), then one
  commit overlaying `/workspace/python-sdk` (client-sdk, server-sdk, docs, examples, scripts, `.github`). Do not
  carry tags `v0.1.0`/`v0.2.0` (they stay in the CLI repo). Tag `v0.3.0` after the release PR. PyPI project URLs for
  `agent-sandbox` move to this repository from 0.3.0 on. Rejected: `git subtree split` of `/workspace` (it only has
  few commits; it would discard the real history).
* **Before the first push**: add `cli/.gitignore` (a `git add cli` today would commit the `node_modules` symlink),
  remove personal paths, run both health scripts to green, update the org `.github` profile README (it links the
  stale `serverless-sandbox` org), register `agent-sandbox-server` on PyPI via a pending Trusted Publisher, create
  the npm org `agent-sandbox`, enable branch protection (required checks: `ci`, `repo-health`), secret scanning,
  Discussions.

## 8. Decision F - naming and link policy

| Item | Decision | Reason |
|------|----------|--------|
| GitHub repos | `agent-sandbox/python-sdk`, `agent-sandbox/agent-sandbox` (existing docs, issue configs and CONTRIBUTING already use these) | org-scoped names; alternative `abx` for the CLI is also fine but would touch every cross-link |
| PyPI | `agent-sandbox-client` (client), `agent-sandbox-server` | `agent-sandbox` on PyPI is an unrelated project, so the client distribution was renamed on 2026-10-15. Import `agent_sandbox` is unchanged. |
| npm | `@agent-sandbox/cli`, bin `abx`; later `@agent-sandbox/provider-api` | unscoped `abx` is taken |
| Import names | `agent_sandbox`, `agent_sandbox.server` (unchanged) | compat with existing templates |
| Directories | `client-sdk/`, `server-sdk/` | self-describing, match dist roles |
| Cross-repo links | absolute `https://github.com/alibaba-agent-sandbox/<repo>/blob/main/<path>`; CHANGELOG (immutable history) uses tag-pinned URLs; never `../cli`, never a bare ADR slug | `../` links die the day the repos are separate (87 such links exist today in python-sdk) |
| Link hygiene | scheduled `lychee` job per repo; the health script blocks relative links that leave the repo | catches rot before users do |

## 9. Ordered move plan

Legend: **NOW** = safe, touches only new files or files no builder owns; **COORD** = small edit to a shared
file, do it when the owner is idle; **LATER** = must wait until builders finish (they are active in
`cli/src`, `cli/tests`, `python-sdk/*/src`, `python-sdk/*/tests`, docs and `.github`).

### python-sdk

| # | Step | When |
|---|------|------|
| P1 | add `scripts/check-repo-health.sh` (done), `.agents/README.md`, `.editorconfig`, `.github/CODEOWNERS`, `.github/workflows/docs-links.yml`, root `pyproject.toml`, `ruff.toml`, `scripts/release.py` | NOW (new files) |
| P2 | superseded: the cloud E2E scripts under `scripts/e2e/` were deleted; the pytest suite in `e2e/` replaces them | DONE |
| P3 | `git mv benchmarks client-sdk/benchmarks`; `git rm client-sdk/benchmarks/__init__.py`; update Makefile/docs | NOW |
| P4 | `.gitignore`: delete the `/.agents/evidence/` and `/.agents/research/` lines; scrub personal paths in `.agents/**`; rewrite `.agents/evidence/README.md` (research/verify only) and `.agents/research/README.md` | NOW (no builder writes `.agents`) |
| P5 | ADR moves: receive 4 ADRs from cli (section 5.4), mark 3 superseded, add `superseded/`, add `notes/INDEX.md`, add ADR `2026-10-12-repository-split-and-layout`; convert cross-repo ADR refs to absolute URLs | NOW, coordinate with C-steps (same commit window) |
| P6 | `client-sdk/pyproject.toml`: hard dependency `agent-sandbox-server==X`, `server = []`, `[project.urls]` -> `agent-sandbox/python-sdk` (both packages); bump 0.3.0 via `scripts/release.py bump 0.3.0` | COORD (touches `_version.py` under `src/`) |
| P7 | `git mv server-sdk/tests/test_server/* server-sdk/tests/`; delete `tests/__init__.py` in both packages; add `--import-mode=importlib` to both pytest configs | LATER |
| P8 | `ci.yml`: add `upgrade-from-0.2`, `repo-health`; `publish.yml`: Trusted Publishing + `scripts/release.py check`; `dependabot.yml` already per package | LATER (builders edit `.github`) |
| P9 | docs: assign page owners (section 3.1), trim shared pages, add `guide/server-sdk.md`, `guide/release.md`, drop "coming soon" rows, replace every `../cli` link with absolute URLs; rewrite `AGENTS.md` tree (still shows the single-package layout), README links | LATER (builders edit docs) |
| P10 | coerce-drift test between `client-sdk/.../utils/coerce.py` and `server-sdk/.../server/_coerce.py`; error message for the empty-namespace upgrade case | LATER (`src`/`tests`) |
| P11 | run the health script until green; publish (section 7) | LATER (final) |

### cli

| # | Step | When |
|---|------|------|
| C1 | add `.gitignore` (`node_modules`, `dist`, `coverage`, `parity/.vitest-report.json`), `.editorconfig`, `.nvmrc`, `eslint.config.js`, `.agents/README.md`, `.github/workflows/{ci,release,docs-links}.yml`, `.github/CODEOWNERS`, `scripts/check-repo-health.sh` (done) | NOW (new files) |
| C2 | `dependabot.yml`: replace `pip` by `npm` | COORD (`.github`) |
| C3 | delete or rewrite leftovers: `benchmarks/bench_cli_startup.py` -> `benchmarks/startup.mjs`; `scripts/{build_hermes,deploy_all_templates,deploy_remaining}.sh` -> maintainer-only `.agents/ops/` with `$REPO_ROOT` instead of `/Users/anycodes` (or delete) | NOW |
| C4 | `docs/PORTING.md`: remove `/tmp/...` and "this VM" paths (point at the pinned commit `b15b88f` instead); plan to archive it after the gate | NOW |
| C5 | `.agents`: send 4 ADRs to python-sdk (5.4), mark `single-distribution-cli-extra` superseded, fix READMEs, scrub `/Users/...`, absolute cross-repo URLs, ADR `2026-10-12-cli-repository-layout` | NOW |
| C6 | `package.json`: devDependencies (`typescript`, `vitest`, `@types/node`, `tsx`, `@types/ws`), runtime deps (`yaml`, `smol-toml`, `ws`, `@inquirer/prompts`), `repository`/`homepage`/`bugs` -> `agent-sandbox/agent-sandbox`, `publishConfig.access=public`, `prepublishOnly`, `lint`; generate `package-lock.json`; replace the `node_modules` symlink by a real install | COORD (builders edit `package.json`) |
| C7 | docs: assign owners (section 3.1), replace links to SDK-only pages (`sdk-usage.md`, `declarative-usage.md`, `design/architecture.md`, ...) by absolute python-sdk URLs, add `guide/providers.md` and `guide/contributing-code.md`, add `examples/` | LATER |
| C8 | `src/` tree: until the gate keep the mirror; **do not** pre-move | WAIT for parity gate |
| C9 | after the gate: single mechanical commit to the target tree (section 6.2): `git mv src/{models,transport,protocol,api,session,utils} src/core/`, `git mv src/framework src/cli/framework`, collect `_py*.ts`/`_pyerrors`/`_pyformat`/`_pypath`/`_pydantic`/`_shlex` into `src/pyparity/`, kebab-case file names (`session_manager.ts` -> `session-manager.ts`), codemod imports, enforce `core` never imports `cli`/`agent` (ESLint `no-restricted-imports`), re-home tests to `tests/{unit,integration,golden,e2e}`, write `parity/ledger-map.json` (python test id -> node file::title), archive `parity/` + `PORTING.md` | LATER (post-gate, builders frozen) |
| C10 | run the health script until green; publish (section 7) | LATER (final) |

## 10. Definition of done (per repository)

Everything marked **[auto]** is enforced by `scripts/check-repo-health.sh`; the rest is a manual release gate.

### python-sdk

* [auto] `README.md` + `README.zh-CN.md` with Install / Quick start / Documentation / Contributing / License; one
  README per package; `LICENSE` + `NOTICE` identical in root and both packages; `CHANGELOG.md` with `[Unreleased]`.
* [auto] `.github`: CoC, CONTRIBUTING, SECURITY, PR template, issue forms + `config.yml`, dependabot for
  `/client-sdk`, `/server-sdk`, actions; `ci.yml`, `publish.yml` (lockstep check); warn: CODEOWNERS, docs-links, OIDC.
* [auto] client has `agent_sandbox/__init__.py`; server has none; both `py.typed`; versions equal; client hard-depends
  on the server; project URLs point at `python-sdk`.
* [auto] docs en/zh page parity, no relative link outside the repo, no broken link, no leaked local path, no stale
  "coming soon", no page byte-identical with `../cli`; `.agents/README.md`, ADR names/status valid, no dangling slugs.
* Manual: PyPI trusted publisher for both names; first `0.3.0` released and smoke-installed from PyPI; branch
  protection with required checks; Discussions on; repo topics/description/homepage; `SECURITY.md` contact works;
  `upgrade-from-0.2` job green; org profile README updated.

### cli

* [auto] README (en/zh) with Install (`npm install -g @agent-sandbox/cli`) / CLI usage / Documentation /
  Contributing / License; `LICENSE`, `NOTICE`, `CHANGELOG`, `AGENTS.md`, `llms.txt`, `SKILL.md`.
* [auto] `package.json`: name, bin, ESM, engines, license, `repository`/`homepage`/`bugs` -> `agent-sandbox/agent-sandbox`,
  `publishConfig.access=public`, `files` whitelist, scripts `build|typecheck|test`; `package-lock.json`; every import
  declared; `node_modules` real and git-ignored; `src/bin/abx.ts` exists; no scratch tests; no Python leftovers.
* [auto] `.github`: community files, `ci.yml` (`npm ci`, typecheck, test, Node matrix), `release.yml` (`npm publish
  --provenance`), dependabot `npm` (no `pip`); warn: binary release workflow, CODEOWNERS, docs-links.
* [auto] docs en/zh parity, `docs/design/repository-layout.md`, link/leak/ADR checks as above; warn: providers and
  contributor guides, `examples/`.
* Manual: npm org `agent-sandbox` created, 2FA + provenance; first `0.3.0` published and `npx @agent-sandbox/cli --version`
  smoke-tested on Linux/macOS/Windows; parity gate evidence archived; branch protection; Discussions.

## 11. `scripts/check-repo-health.sh` - what it does and the current result

Both repos ship `scripts/check-repo-health.sh` (read-only; `--strict` turns WARN into failure; `--quiet` prints only
problems). python-sdk's uses `bash` + `python3`; cli's uses `bash` + `node`. Sections: top-level files, README /
CHANGELOG headings, `.github` + CI semantics, package metadata (Python: lockstep, namespace rules, hard dependency,
URLs; npm: manifest, undeclared imports, symlinked `node_modules`, ignores), docs, `.agents`, content hygiene
(relative links, links leaving the repo, leaked local paths, ADR name/status, dangling ADR slugs, en/zh parity,
stale "coming soon", duplicate pages across the sibling repo). Run it in CI as the required `repo-health` check.

Results (the builders kept writing during the review, so the numbers moved; re-run for the live state):

| Repo | First run (review start) | Latest run | Remaining failures in the latest run |
|------|--------------------------|------------|--------------------------------------|
| python-sdk | PASS 88 / WARN 9 / FAIL 11 | PASS 90 / WARN 9 / FAIL 9 | missing `.agents/README.md`; client does not hard-depend on server; project URLs of both packages still point at the legacy repo; 88 relative links leave the repo (`../cli`); 41 broken links (mostly `.agents`); 12 dangling ADR slugs in 23 files; new `docs/en` pages without a `docs/zh` twin (`design/agents-api`, `design/base-image-and-server-sdk`, ...); `template-yaml-spec` still byte-identical with `cli` |
| cli | PASS 67 / WARN 13 / FAIL 25 | PASS 83 / WARN 13 / FAIL 12 | no `release.yml`; `package.json` metadata (`repository`, `homepage`, `bugs`, `publishConfig.access`); no `src/bin/abx.ts` yet; no `examples/`; no `.agents/README.md`; 14 broken links; leaked `/Users/...` paths in 2 `.agents` evidence files; 16 dangling ADR slugs; `template-yaml-spec` byte-identical with python-sdk (the first run also failed on missing `.gitignore`/`ci.yml`, symlinked `node_modules`, Python leftovers and undeclared dependencies, which the builders have since fixed) |

Expected end state: both scripts exit 0 with `--strict` (the WARN items are the polish backlog).
