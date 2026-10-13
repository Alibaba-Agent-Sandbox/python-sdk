#!/usr/bin/env bash
# Regression guard: fail if developer-machine specifics or credential-like strings
# are committed (user-home absolute paths, Windows user paths, personal scratch
# directories, `.venv/bin` assumptions, personal ACR namespaces / fixed e2e tags,
# AK / API-key / token shaped strings).
#
# Scope: every tracked or untracked-but-not-ignored text file of this repository
# (`git ls-files -co --exclude-standard`; plain `find` when not inside a git work
# tree). Needs only bash, grep and (optionally) git, so it runs unchanged in CI.
#
# Usage:  bash scripts/check-no-local-paths.sh
# Exit:   0 = clean, 1 = findings, 2 = usage / environment error
#
# Legitimate matches go into scripts/local-paths.allowlist (format documented
# there). Matches of secret-shaped patterns are reported WITHOUT their value.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ALLOWLIST="${LOCAL_PATHS_ALLOWLIST:-$ROOT/scripts/local-paths.allowlist}"
SELF_REL="scripts/check-no-local-paths.sh"
ALLOWLIST_REL="scripts/local-paths.allowlist"

case "${1:-}" in
  "" ) ;;
  -h|--help) sed -n '2,15p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
  *) echo "usage: $0 [-h]" >&2; exit 2 ;;
esac

# Each rule: "label::extended-regex::exempt-regex". An exempt-regex (optional) is matched
# against each matched substring; fully matching substrings are ignored. A label
# starting with "secret:" suppresses the offending text in the report.
RULES=(
  'macOS user-home path::/Users/[A-Za-z0-9._-]+::'
  'Linux user-home path::/home/[A-Za-z0-9._-]+::/home/user'
  'Windows user path::[A-Za-z]:[\\/]+Users[\\/]::'
  'personal scratch / project directory::Documents/Qoder|Qoder/20[0-9][0-9]|/chat-[0-9]+([^0-9]|$)::'
  'virtualenv interpreter assumption::[.]venv/(bin|Scripts)/::'
  'agent scratch location::/tmp/(agent-sandbox|parity|venv)[A-Za-z0-9_-]*::'
  'dated e2e artifact name::e2e-20[0-9]{6}::'
  'secret: Alibaba Cloud AccessKey id::LTAI[A-Za-z0-9]{12,}::'
  'secret: AWS-style access key id::AKIA[0-9A-Z]{16}::'
  'secret: e2b API key::e2b_[A-Za-z0-9]{20,}::'
  'secret: OpenAI/DashScope-style API key::(^|[^A-Za-z0-9_-])sk-[A-Za-z0-9_-]{20,}::'
  'secret: GitHub token::gh[pousr]_[A-Za-z0-9]{30,}::'
  'secret: Slack token::xox[abprs]-[A-Za-z0-9-]{10,}::'
  'secret: private key block::-----BEGIN [A-Z ]*PRIVATE KEY-----::'
)

# Maintainer-private literals (account ids, handles) live in a gitignored file, one
# extended regex per line, so they never appear in a published script.
PRIVATE_RULES_FILE="${ABX_HYGIENE_PRIVATE_RULES:-$ROOT/scripts/local-paths.private}"
if [ -f "$PRIVATE_RULES_FILE" ]; then
  while IFS= read -r line || [ -n "$line" ]; do
    line="${line%$'\r'}"
    case "$line" in ''|'#'*) continue ;; esac
    RULES+=("secret: maintainer-private literal::${line}::")
  done < "$PRIVATE_RULES_FILE"
fi

al_globs=()
al_regexes=()
if [ -f "$ALLOWLIST" ]; then
  while IFS= read -r line || [ -n "$line" ]; do
    line="${line%$'\r'}"
    case "$line" in ''|'#'*) continue ;; esac
    if [[ "$line" == *'|'* ]]; then
      al_globs+=("${line%%|*}")
      al_regexes+=("${line#*|}")
    else
      al_globs+=("$line")
      al_regexes+=("")
    fi
  done < "$ALLOWLIST"
fi

is_allowed() {
  local file="$1" text="$2" i
  for ((i = 0; i < ${#al_globs[@]}; i++)); do
    # shellcheck disable=SC2053
    if [[ "$file" == ${al_globs[$i]} ]]; then
      if [ -z "${al_regexes[$i]}" ] || printf '%s\n' "$text" | grep -Eq -- "${al_regexes[$i]}"; then
        return 0
      fi
    fi
  done
  return 1
}

list_files() {
  if git -C "$ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git -C "$ROOT" ls-files -z --cached --others --exclude-standard
  else
    (cd "$ROOT" && find . \( -name .git -o -name node_modules -o -name .venv -o -name dist \
      -o -name __pycache__ -o -name .mypy_cache -o -name .ruff_cache \) -prune \
      -o -type f -print0)
  fi
}

cd "$ROOT"
tmp_list="$(mktemp "${TMPDIR:-/tmp}/local-paths-files.XXXXXX")"
trap 'rm -f "$tmp_list"' EXIT
while IFS= read -r -d '' f; do
  f="${f#./}"
  case "$f" in
    "$SELF_REL"|"$ALLOWLIST_REL"|node_modules/*|*/node_modules/*|.git/*) continue ;;
  esac
  [ -f "$f" ] || continue
  printf '%s\0' "$f"
done < <(list_files) > "$tmp_list"

if [ ! -s "$tmp_list" ]; then
  echo "check-no-local-paths: no files to scan under $ROOT" >&2
  exit 2
fi

findings=0
for rule in "${RULES[@]}"; do
  label="${rule%%::*}"
  rest="${rule#*::}"
  regex="${rest%::*}"
  exempt="${rest##*::}"
  secret=0
  case "$label" in secret:*) secret=1; label="${label#secret: }" ;; esac

  while IFS= read -r hit; do
    [ -n "$hit" ] || continue
    file="${hit%%:*}"
    rem="${hit#*:}"
    lineno="${rem%%:*}"
    text="${rem#*:}"

    if [ -n "$exempt" ]; then
      real=0
      while IFS= read -r m; do
        [ -n "$m" ] || continue
        printf '%s\n' "$m" | grep -Eqx -- "$exempt" || real=1
      done < <(printf '%s\n' "$text" | grep -oE -- "$regex" || true)
      [ "$real" -eq 1 ] || continue
    fi

    if is_allowed "$file" "$text"; then continue; fi

    findings=$((findings + 1))
    if [ "$secret" -eq 1 ]; then
      printf '%s:%s: %s (value hidden)\n' "$file" "$lineno" "$label"
    else
      printf '%s:%s: %s: %.160s\n' "$file" "$lineno" "$label" "$text"
    fi
  done < <(xargs -0 grep -HInE -- "$regex" < "$tmp_list" 2>/dev/null || true)
done

if [ "$findings" -gt 0 ]; then
  {
    echo
    echo "check-no-local-paths: $findings finding(s)."
    echo "Fix them (use paths relative to the script, environment variables, or"
    echo "placeholders such as <your-namespace>), or - for a legitimate match - add an"
    echo "entry to $ALLOWLIST_REL with a justification."
  } >&2
  exit 1
fi

echo "check-no-local-paths: OK (no local paths or credential-like strings found)"
