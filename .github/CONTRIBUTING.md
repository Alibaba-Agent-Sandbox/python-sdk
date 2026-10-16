# Contributing to Agent Sandbox

Thank you for your interest in contributing! This guide will help you get started.

## Repository Layout

This repository (`python-sdk`) holds the **Python SDK**, which is released as two PyPI
distributions that share the `agent_sandbox` namespace and are versioned in lockstep:

| Folder | PyPI distribution | Import path | Purpose |
|--------|-------------------|-------------|---------|
| `client-sdk/` | `agent-sandbox-client` | `agent_sandbox` | Async client SDK (`Sandbox`, `ServerClient`, `@sandbox`, MCP server, E2B migration helper, ...) |
| `server-sdk/` | `agent-sandbox-server` | `agent_sandbox.server` | Container-side runtime that runs inside sandbox images |

The `abx` command-line tool is a separate Node.js/TypeScript project that lives in the
`cli` repository. CLI issues and pull requests belong there, not here.

## Development Setup

### Prerequisites

- Python 3.10+
- Git

### Getting Started

```bash
# 1. Fork and clone the repository
git clone https://github.com/<your-username>/python-sdk.git
cd python-sdk

# 2. Install both packages in development mode (includes all extras + test/lint tooling)
pip install -e ./server-sdk -e "./client-sdk[dev]"   # or: make dev
# With uv, in an activated virtual environment:
uv pip install -e ./server-sdk -e "./client-sdk[dev]"

# 3. Install pre-commit — its checks are invoked automatically by .githooks/pre-commit
pip install pre-commit   # or: make hooks

# 4. Verify your setup
make test
```

The root uv workspace maps `agent-sandbox-server` to `server-sdk/`, so the
client uses the matching local runtime during development. No `--no-sources`
workaround is needed. Published client metadata keeps the lockstep version pin.

> **Note on Git hooks:** This repository ships `.githooks/` and uses it as the
> hook entry point via `core.hooksPath=.githooks` (a local Git config).
> `.githooks/pre-commit` first runs the custom secret scan
> (`.githooks/check-secrets.sh`), then — if the `pre-commit` command is
> installed — invokes the full `.pre-commit-config.yaml` suite (ruff,
> ruff-format, detect-secrets, bandit, …). Installing the package
> (`pip install pre-commit`, or `make hooks`) is all that is needed:
> `pre-commit install` is not used here because it writes to `.git/hooks/`,
> which Git bypasses while `core.hooksPath=.githooks` is set. On a fresh clone
> (where `core.hooksPath` is unset), run `git config core.hooksPath .githooks`
> — or `pre-commit install` — to activate the hooks.

## Development Workflow

1. **Fork** the repository on GitHub
2. **Create a branch** from `main`:
   ```bash
   git checkout -b feat/my-feature
   ```
3. **Make your changes** — write code, tests, and docs
4. **Run checks** before committing:
   ```bash
   make lint      # Lint with ruff (client-sdk and server-sdk)
   make format    # Format with ruff
   make typecheck # Type-check with mypy
   make test      # Run tests with pytest
   ```

   Every `make` target runs on both packages. To work on a single package, run the
   tools from inside its folder instead, for example:
   ```bash
   cd client-sdk && ruff check src tests && mypy src/agent_sandbox && pytest -m "not integration"
   cd server-sdk && ruff check src tests && mypy src/agent_sandbox/server && pytest
   ```

   Or run the full local CI equivalent in one command:
   ```bash
   make ci        # ruff check + ruff format --check + mypy + pytest (not integration) + build both packages + twine check + py.typed check + combined-install import check
   ```

   > **Note:** `make ci` runs on your single local Python interpreter. It does **not** replace the Python 3.10 / 3.11 / 3.12 test matrix enforced by GitHub Actions CI — the matrix can only be fully covered by CI itself.
5. **Commit** using [Conventional Commits](https://www.conventionalcommits.org/):
   ```
   feat: add sandbox snapshot support
   fix: resolve timeout issue in pool manager
   docs: update CLI usage examples
   chore: bump ruff to 0.5.0
   ```
6. **Push** and open a **Pull Request** against `main`

## Code Style

We use [**Ruff**](https://docs.astral.sh/ruff/) for **both linting and formatting** (replacing the former black / isort / flake8 setup). The configuration lives in each package's `pyproject.toml` (`client-sdk/pyproject.toml`, `server-sdk/pyproject.toml`) under `[tool.ruff]`.

- **Type Hints**: All public APIs must have type annotations; we enforce this with [mypy](https://mypy-lang.org/).
- **Docstrings**: Use Google-style docstrings for public functions and classes.

```python
async def create_sandbox(template: str, timeout: int = 300) -> Sandbox:
    """Create a new sandbox instance.

    Args:
        template: Name of the sandbox template.
        timeout: Maximum creation time in seconds.

    Returns:
        A configured Sandbox instance.

    Raises:
        SandboxError: If sandbox creation fails.
    """
```

## Secret Scanning

A custom hook (`.githooks/check-secrets.sh`) scans every commit for hardcoded secrets — API keys, tokens, passwords, and cloud credentials. Commit-time checks flow through a single entry point:

| Component | Role |
|-----------|------|
| `.githooks/pre-commit` | **Primary hook entry point.** Git calls it because this repository is configured with `core.hooksPath=.githooks`. |
| `check-secrets.sh` | Runs first: scans staged files for hardcoded secrets and blocks the commit if any are found. |
| pre-commit framework | Runs second (when the `pre-commit` command is installed): executes every hook in `.pre-commit-config.yaml` — ruff, ruff-format, detect-secrets, bandit, plus the `check-secrets` local hook — via `pre-commit run --hook-stage pre-commit`. |

To enable the full suite locally, install the package once:

```bash
pip install pre-commit
# or:
make hooks
```

If `pre-commit` is not installed, `.githooks/pre-commit` still runs the secret
scan and prints an install hint; the framework step is skipped without blocking
the commit.

If the hook detects a secret, the commit is blocked and the offending file + line is printed. False positives can be suppressed by adding `placeholder`, `example`, or `REPLACE_ME` to the line.

## Testing

- We use [pytest](https://docs.pytest.org/) for testing.
- Write tests for all new features and bug fixes.
- Place tests in the `tests/` directory of the package you are changing (`client-sdk/tests/` or `server-sdk/tests/`), mirroring that package's `src/` structure.

```bash
# Run all tests (both packages)
make test

# Run a specific test file
pytest client-sdk/tests/test_api/test_sandbox.py

# Run with verbose output
pytest -v
```

## Definition of Done

A change is done only when it is verified end to end against real components and recorded under
`.agents/`. Every PR must provide: unit tests, an E2E run against the real cloud (`make e2e`, see
[`e2e/README.md`](../e2e/README.md)) recorded in `.agents/evidence/verify/<date>-<topic>.md` (never
containing credentials), an ADR/note under `.agents/notes/`, English and Chinese docs, and a
`CHANGELOG.md` entry. Real credentials live only in gitignored `.env` files and must never be printed,
logged or committed. The full rule, the evidence-file and ADR templates are in
[`.agents/notes/DEFINITION-OF-DONE.md`](../.agents/notes/DEFINITION-OF-DONE.md) (English and 中文:
**完成定义**——所有功能必须针对真实组件完成端到端验证,并在 `.agents/` 中记录,文档需中英文齐全并附 CHANGELOG 条目)。

## Template Contributions

Sandbox templates — content, the machine-readable index (`awesome-templates.yaml`), releases and CI — live in the dedicated repository **[alibaba-agent-sandbox/awesome-templates](https://github.com/alibaba-agent-sandbox/awesome-templates)**. It is the single source of truth for official & community templates; this repository no longer bundles a template collection (it keeps only a minimal `python-hello` offline fixture for tests).

### Contributing a Template

1. **Read** the catalog repository's [CONTRIBUTING.md](https://github.com/alibaba-agent-sandbox/awesome-templates/blob/main/CONTRIBUTING.md) — it defines the template anatomy, capability-group rules, and local dev workflow.
2. **Open a PR** against [alibaba-agent-sandbox/awesome-templates](https://github.com/alibaba-agent-sandbox/awesome-templates) that adds your template folder and updates `awesome-templates.yaml` (plus the README template table) in the same PR.
3. **Required index fields**: `name`, `description`, `repo`, `tags`, `author`, `capabilities`, `status` (optional: `path` for subdirectory templates, `ref` to pin a version).
4. **Status values**:
   - `official` — maintained by the alibaba-agent-sandbox team (do not use for community PRs)
   - `community` — community-contributed and maintained
   - `experimental` — early-stage or proof-of-concept
5. **Ensure** your repo contains a valid `template.yaml` at the specified path. The catalog CI validates every folder and the index offline.

### Template Repository Requirements

Your template repository should include:
- A `template.yaml` defining the sandbox configuration (base image, packages, capabilities, etc.)
- A `Dockerfile` and a `README.md` with usage instructions
- Example code or scripts that demonstrate the template's purpose

### Searching Templates

Use the CLI (`abx`, from the `cli` repository) to search the remote index:
```bash
abx template search python      # search by tag or keyword
abx template search ai-agent    # find AI agent templates
abx template search browser     # find browser automation templates
```

## Commit Message Convention

We follow [Conventional Commits](https://www.conventionalcommits.org/):

| Prefix | Purpose |
|--------|---------|
| `feat:` | New feature |
| `fix:` | Bug fix |
| `docs:` | Documentation only |
| `chore:` | Build, CI, or tooling changes |
| `test:` | Adding or updating tests |
| `refactor:` | Code change that neither fixes a bug nor adds a feature |
| `perf:` | Performance improvement |

## Reporting Issues

- Use [GitHub Issues](https://github.com/alibaba-agent-sandbox/python-sdk/issues/new/choose) with our templates
- For security vulnerabilities, see our [Security Policy](SECURITY.md)

## Questions?

- Open a [Discussion](https://github.com/alibaba-agent-sandbox/python-sdk/discussions) for general questions
- Check existing issues and discussions before creating new ones

## License

By contributing, you agree that your contributions will be licensed under the [Apache-2.0 License](../LICENSE).
