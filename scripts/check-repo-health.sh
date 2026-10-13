#!/usr/bin/env bash
# Repository health gate for the python-sdk repository.
#
# Fails (exit 1) when a file, section or invariant required of a complete
# open-source repository is missing.  It only reads files; run it from anywhere:
#
#   scripts/check-repo-health.sh            # FAIL lines make the exit code 1
#   scripts/check-repo-health.sh --strict   # WARN lines fail too
#   scripts/check-repo-health.sh --quiet    # print only FAIL/WARN lines and the summary
#
# Requires: bash, python3 (3.10+).  See docs/en/design/repository-layout.md
# ("Definition of done") for the rationale behind every check.
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 2

STRICT=0
QUIET=0
for arg in "$@"; do
  case "$arg" in
    --strict) STRICT=1 ;;
    --quiet) QUIET=1 ;;
    -h|--help) sed -n '2,12p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "unknown option: $arg" >&2; exit 2 ;;
  esac
done

FAILS=0
WARNS=0
PASSES=0

pass() { PASSES=$((PASSES + 1)); [ "$QUIET" -eq 1 ] || printf '[PASS] %s\n' "$1"; }
fail() { FAILS=$((FAILS + 1)); printf '[FAIL] %s\n' "$1"; }
warn() { WARNS=$((WARNS + 1)); printf '[WARN] %s\n' "$1"; }

need_file() { # need_file <path> [<description>]
  if [ -f "$1" ]; then pass "file: $1"; else fail "missing file: $1${2:+ ($2)}"; fi
}
need_dir() {
  if [ -d "$1" ]; then pass "dir: $1"; else fail "missing dir: $1${2:+ ($2)}"; fi
}
need_grep() { # need_grep <file> <regex> <description>
  if [ -f "$1" ] && grep -Eiq -- "$2" "$1"; then pass "$3"; else fail "$3 [$1]"; fi
}
warn_file() {
  if [ -f "$1" ]; then pass "file: $1"; else warn "recommended file missing: $1${2:+ ($2)}"; fi
}

tally() {
  local line
  while IFS= read -r line; do
    case "$line" in
      "[PASS]"*) PASSES=$((PASSES + 1)); [ "$QUIET" -eq 1 ] || printf '%s\n' "$line" ;;
      "[WARN]"*) WARNS=$((WARNS + 1)); printf '%s\n' "$line" ;;
      "[FAIL]"*) FAILS=$((FAILS + 1)); printf '%s\n' "$line" ;;
      *) printf '%s\n' "$line" ;;
    esac
  done
}
shopt -s lastpipe

section() { [ "$QUIET" -eq 1 ] || printf '\n== %s ==\n' "$1"; }

section "Top-level project files"
for f in README.md README.zh-CN.md LICENSE NOTICE CHANGELOG.md AGENTS.md llms.txt \
         .gitignore .env.example Makefile .pre-commit-config.yaml .python-version \
         .secrets.baseline; do
  need_file "$f"
done
warn_file pyproject.toml "tooling-only root (uv workspace + shared ruff config); never published"
warn_file .editorconfig
need_dir .githooks
need_file .githooks/pre-commit

section "README / CHANGELOG sections"
for h in "Install" "Quick ?start|Usage" "Documentation|Docs" "Contributing" "License"; do
  need_grep README.md "^#{1,3} .*(${h})" "README.md has a '${h}' heading"
done
need_grep README.md 'client-sdk' "README.md describes the client-sdk package"
need_grep README.md 'server-sdk' "README.md describes the server-sdk package"
need_grep CHANGELOG.md '^## \[Unreleased\]' "CHANGELOG.md has an [Unreleased] section"
need_grep CHANGELOG.md 'keepachangelog' "CHANGELOG.md declares the Keep a Changelog format"

section "Community health + CI (.github)"
for f in CODE_OF_CONDUCT.md CONTRIBUTING.md SECURITY.md PULL_REQUEST_TEMPLATE.md dependabot.yml \
         ISSUE_TEMPLATE/bug_report.yml ISSUE_TEMPLATE/feature_request.yml ISSUE_TEMPLATE/config.yml \
         workflows/ci.yml workflows/publish.yml; do
  need_file ".github/$f"
done
warn_file .github/CODEOWNERS
warn_file .github/workflows/docs-links.yml "scheduled markdown link check (lychee)"
need_grep .github/dependabot.yml '/client-sdk' "dependabot watches /client-sdk"
need_grep .github/dependabot.yml '/server-sdk' "dependabot watches /server-sdk"
need_grep .github/dependabot.yml 'github-actions' "dependabot watches github-actions"
if [ -f .github/workflows/publish.yml ]; then
  if grep -Eq 'pypa/gh-action-pypi-publish|trusted' .github/workflows/publish.yml; then
    pass "publish.yml uses PyPI Trusted Publishing"
  else
    warn "publish.yml uploads with a long-lived PYPI_API_TOKEN (use Trusted Publishing / OIDC)"
  fi
  need_grep .github/workflows/publish.yml 'lock-?step|same version|versions must' "publish.yml enforces version lockstep"
fi

section "Python packages (client-sdk, server-sdk)"
for pkg in client-sdk server-sdk; do
  for f in pyproject.toml README.md LICENSE NOTICE; do need_file "$pkg/$f"; done
  need_dir "$pkg/src" ; need_dir "$pkg/tests"
  need_file "$pkg/tests/conftest.py"
done
need_file client-sdk/src/easy_sandbox/__init__.py "client owns the namespace root"
need_file client-sdk/src/easy_sandbox/py.typed
need_file client-sdk/src/easy_sandbox/_version.py
need_file server-sdk/src/easy_sandbox/server/__init__.py
need_file server-sdk/src/easy_sandbox/server/py.typed
need_file server-sdk/src/easy_sandbox/server/_version.py
if [ -e server-sdk/src/easy_sandbox/__init__.py ]; then
  fail "server-sdk must not ship easy_sandbox/__init__.py (it would shadow the client)"
else
  pass "server-sdk ships no easy_sandbox/__init__.py"
fi
for d in src tests; do
  if [ -e "$d" ]; then fail "stale top-level '$d/' from the single-package era (move into client-sdk/ or server-sdk/)"; else pass "no stale top-level $d/"; fi
done
for f in LICENSE NOTICE; do
  if cmp -s "$f" "client-sdk/$f" && cmp -s "$f" "server-sdk/$f"; then
    pass "$f is identical in root, client-sdk and server-sdk"
  else
    fail "$f differs between root / client-sdk / server-sdk"
  fi
done

python3 - <<'PY' | tally
import re, sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    tomllib = None

ok = True
def result(kind, msg):
    global ok
    print(f"[{kind}] {msg}")
    if kind == "FAIL":
        ok = False

def read_version(path):
    m = re.search(r'__version__\s*=\s*"([^"]+)"', Path(path).read_text(encoding="utf-8"))
    return m.group(1) if m else None

try:
    cv = read_version("client-sdk/src/easy_sandbox/_version.py")
    sv = read_version("server-sdk/src/easy_sandbox/server/_version.py")
except FileNotFoundError:
    cv = sv = None
if cv and cv == sv:
    result("PASS", f"client and server versions are in lockstep ({cv})")
else:
    result("FAIL", f"client/server versions differ or are unreadable: {cv!r} vs {sv!r}")

if tomllib is None:
    result("WARN", "python < 3.11: skipping pyproject.toml semantic checks")
else:
    def load(p):
        with open(p, "rb") as fh:
            return tomllib.load(fh)
    try:
        client = load("client-sdk/pyproject.toml")["project"]
        server = load("server-sdk/pyproject.toml")["project"]
    except FileNotFoundError:
        client = server = None
    if client and server:
        deps = [d.replace(" ", "") for d in client.get("dependencies", [])]
        if any(d.startswith("easy-sandbox-server") for d in deps):
            result("PASS", "easy-sandbox hard-depends on easy-sandbox-server (keeps `from easy_sandbox.server import` working after `pip install easy-sandbox`)")
        else:
            result("FAIL", "easy-sandbox does not hard-depend on easy-sandbox-server: `pip install easy-sandbox` no longer provides easy_sandbox.server (0.2.0 behaviour)")
        for name, proj in (("client-sdk", client), ("server-sdk", server)):
            urls = " ".join(proj.get("urls", {}).values())
            if "Easy-Sandbox/python-sdk" in urls and "Easy-Sandbox/easy-sandbox" not in urls:
                result("PASS", f"{name} project URLs point at the python-sdk repository")
            else:
                result("FAIL", f"{name} project URLs still point at the legacy single repo (expected github.com/Easy-Sandbox/python-sdk)")
            if "docs/en" in proj.get("urls", {}).get("Documentation", "") or "/docs" in proj.get("urls", {}).get("Documentation", ""):
                result("PASS", f"{name} Documentation URL is set")
            else:
                result("WARN", f"{name} Documentation URL is not a docs path")
sys.exit(0 if ok else 1)
PY

section "Docs (docs/en, docs/zh)"
need_file docs/README.md
need_file docs/en/README.md
need_file docs/zh/README.md
for f in guide/getting-started.md guide/sdk-usage.md guide/authentication.md guide/environment-variables.md \
         guide/troubleshooting.md reference/api-reference.md reference/error-codes.md reference/configuration.md \
         reference/server-http-api.md design/server-api.md design/architecture.md \
         design/repository-layout.md; do
  need_file "docs/en/$f"
done
warn_file docs/en/guide/server-sdk.md "how to author commands.py with easy_sandbox.server"
warn_file docs/en/guide/release.md "maintainer release runbook (or CONTRIBUTING section)"
need_file examples/README.md
need_dir examples/quickstart
need_dir examples/templates

section "Agent records (.agents)"
need_file .agents/README.md "explains notes/evidence/research scope and ADR rules for this repo"
need_file .agents/notes/README.md
need_dir .agents/notes/implemented
need_dir .agents/notes/proposed
need_dir .agents/notes/rejected
if grep -Eq '^/?\.agents/(evidence|research)/?$' .gitignore 2>/dev/null; then
  warn ".gitignore ignores .agents/evidence + .agents/research: a fresh 'git add' of the published repo silently drops them (force-add or stop ignoring)"
else
  pass ".gitignore does not hide .agents/evidence or .agents/research"
fi

section "Content hygiene (links, ADRs, leaked paths)"
python3 - <<'PY' | tally
import os, re, sys
from pathlib import Path

SKIP_DIRS = {".git", "node_modules", ".mypy_cache", ".ruff_cache", "__pycache__", "dist", "build",
             ".venv", "venv", ".pytest_cache", ".scratch"}
root = Path(".").resolve()
files = []
for dp, dn, fn in os.walk(root):
    dn[:] = [d for d in dn if d not in SKIP_DIRS and not d.endswith(".egg-info")]
    for f in fn:
        files.append(Path(dp) / f)

fails = 0
def report(kind, msg):
    global fails
    print(f"[{kind}] {msg}")
    if kind == "FAIL":
        fails += 1

TEXT_EXT = {".md", ".txt", ".yml", ".yaml", ".toml", ".py", ".sh", ".json", ".cfg"}
def strip_code(text):
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    return re.sub(r"`[^`\n]*`", "", text)

# 1. relative markdown links must resolve inside this repository
broken, escaping = [], []
for p in files:
    if p.suffix != ".md":
        continue
    text = strip_code(p.read_text(encoding="utf-8", errors="ignore"))
    for m in re.finditer(r"\]\(([^)\s]+?)(?:#[^)]*)?\)", text):
        link = m.group(1)
        if re.match(r"^(https?:|mailto:|#|tel:|data:)", link) or not link:
            continue
        if link.startswith("file://"):
            broken.append((p, link)); continue
        target = (p.parent / link).resolve()
        try:
            target.relative_to(root)
        except ValueError:
            escaping.append((p, link)); continue
        if not target.exists():
            broken.append((p, link))
rel = lambda p: str(p.relative_to(root))
if escaping:
    report("FAIL", f"{len(escaping)} relative links leave the repository (cross-repo links must be absolute https URLs); e.g. " +
           "; ".join(f"{rel(p)} -> {l}" for p, l in escaping[:4]))
else:
    report("PASS", "no relative link escapes the repository")
if broken:
    byfile = {}
    for p, l in broken: byfile.setdefault(rel(p), []).append(l)
    report("FAIL", f"{len(broken)} broken relative markdown links in {len(byfile)} files; first: " +
           "; ".join(f"{f} -> {ls[0]}" for f, ls in list(sorted(byfile.items()))[:5]))
else:
    report("PASS", "all relative markdown links resolve")

# 2. leaked local paths
LEAK = re.compile(r"(/Users/[A-Za-z0-9_.-]+/|file:///|/home/ubuntu/|/tmp/(?:easy-sandbox|parity|venv)[A-Za-z0-9_-]*|Qoder/20\d\d|\bthis VM\b)")
leaks = {}
for p in files:
    if p.suffix not in TEXT_EXT or p.name == "check-repo-health.sh":
        continue
    if rel(p).startswith(("docs/en/design/repository-layout.md",)):
        continue
    t = p.read_text(encoding="utf-8", errors="ignore")
    n = len(LEAK.findall(t))
    if n: leaks[rel(p)] = n
if leaks:
    report("FAIL", f"{len(leaks)} files leak machine-local paths (/Users/..., file:///, /tmp/..., 'this VM'): " +
           ", ".join(list(sorted(leaks))[:6]) + (" ..." if len(leaks) > 6 else ""))
else:
    report("PASS", "no machine-local paths in tracked text files")

# 3. ADR hygiene
adr_re = re.compile(r"^\d{4}-\d{2}-\d{2}-[a-z0-9][a-z0-9-]*\.md$")
bad = []
for p in files:
    r = rel(p)
    if not r.startswith(".agents/notes/") or p.suffix != ".md" or p.name in ("README.md", "DEFINITION-OF-DONE.md"):
        continue
    parts = r.split("/")
    state = parts[2] if len(parts) > 3 else ""
    if not adr_re.match(p.name):
        bad.append(f"{r}: file name is not YYYY-MM-DD-slug.md"); continue
    head = p.read_text(encoding="utf-8", errors="ignore").splitlines()[:6]
    if not head or not head[0].startswith("# Decision:"):
        bad.append(f"{r}: first line is not '# Decision: <Title>'"); continue
    st = next((l.split(":", 1)[1].strip().lower() for l in head if l.lower().startswith("status:")), None)
    if st is None or (state in {"proposed", "implemented", "rejected"} and not st.startswith(state)):
        bad.append(f"{r}: Status {st!r} does not match directory '{state}'")
if bad:
    report("FAIL", f"{len(bad)} ADR(s) violate .agents/notes/README.md rules; first: " + "; ".join(bad[:3]))
else:
    report("PASS", "every ADR has a dated name, '# Decision:' title and Status matching its directory")

# 4. ADR slugs referenced but absent from this repository
stems = {p.stem for p in files if adr_re.match(p.name)}
ref_re = re.compile(r"(?<![0-9A-Za-z-])(\d{4}-\d{2}-\d{2}-[a-z][a-z0-9-]*[a-z0-9])(?![0-9A-Za-z-])")
dangling = {}
for p in files:
    if p.suffix not in {".md", ".txt"} or rel(p) == "docs/en/design/repository-layout.md":
        continue
    text = re.sub(r"\[[^\]]*\]\(https?://[^)]*\)|https?://\S+", "", p.read_text(encoding="utf-8", errors="ignore"))
    for s in set(ref_re.findall(text)):
        if s not in stems:
            dangling.setdefault(s, []).append(rel(p))
if dangling:
    nfiles = len({f for v in dangling.values() for f in v})
    report("FAIL", f"{len(dangling)} ADR/evidence slugs are referenced in {nfiles} files but absent from this repo (cross-repo refs must be absolute URLs): " +
           ", ".join(sorted(dangling)[:4]) + (" ..." if len(dangling) > 4 else ""))
else:
    report("PASS", "no dangling ADR references")

# 5. docs: en/zh parity + stale 'coming soon'
MAINTAINER_ONLY = {"design/repository-layout.md"}
en = {rel(p)[len("docs/en/"):] for p in files if rel(p).startswith("docs/en/") and p.suffix == ".md"} - MAINTAINER_ONLY
zh = {rel(p)[len("docs/zh/"):] for p in files if rel(p).startswith("docs/zh/") and p.suffix == ".md"}
only_en, only_zh = sorted(en - zh), sorted(zh - en)
if only_en or only_zh:
    report("FAIL", f"docs en/zh mismatch: only en={only_en[:4]} only zh={only_zh[:4]}")
else:
    report("PASS", "docs/en and docs/zh have the same page set")
stale = 0
for lang in ("en", "zh"):
    idx = root / "docs" / lang / "README.md"
    if idx.exists():
        for line in idx.read_text(encoding="utf-8").splitlines():
            m = re.search(r"\]\(([^)#]+)\)", line)
            if m and re.search(r"coming soon|即将推出|翻译中", line, re.I) and (idx.parent / m.group(1)).exists():
                stale += 1
if stale:
    report("WARN", f"{stale} docs index rows still say 'coming soon' although the page exists")
else:
    report("PASS", "docs index has no stale 'coming soon' rows")

# 6. sibling-repo duplication (only when the staging layout is present)
sib = root.parent / "cli" / "docs"
if sib.is_dir():
    dup = []
    for lang in ("en", "zh"):
        for p in files:
            r = rel(p)
            if r.startswith(f"docs/{lang}/") and p.suffix == ".md":
                q = sib / r[len("docs/"):]
                if q.is_file() and q.read_bytes() == p.read_bytes():
                    dup.append(r)
    if dup:
        report("FAIL", f"{len(dup)} doc pages are byte-identical in ../cli/docs (one repo must own each page; the other links to it): " + ", ".join(dup[:4]) + " ...")
    else:
        report("PASS", "no byte-identical doc pages shared with ../cli")
sys.exit(1 if fails else 0)
PY

printf '\n== Summary ==\n'
printf 'PASS=%d  WARN=%d  FAIL=%d\n' "$PASSES" "$WARNS" "$FAILS"
if [ "$FAILS" -gt 0 ] || { [ "$STRICT" -eq 1 ] && [ "$WARNS" -gt 0 ]; }; then
  exit 1
fi
exit 0
