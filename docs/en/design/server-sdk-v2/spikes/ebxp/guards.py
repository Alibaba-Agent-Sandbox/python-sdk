"""Prototype: path, command and URL guards (design v2.1; reference code, not the implementation)."""
from __future__ import annotations
import dataclasses, fnmatch, ipaddress, os, re, shlex, stat
from typing import Sequence
from urllib.parse import urlsplit


class Denied(Exception):
    def __init__(self, code: str, message: str = "", **details):
        super().__init__(message or code)
        self.code, self.message, self.details = code, message or code, details


# ---------------------------------------------------------------- linear-time globs (IS-P9)
MAX_PATH = 4096
MAX_SEGMENTS = 256
MAX_DOUBLESTAR = 3


def _seg_match(p: str, s: str) -> bool:
    """`*` and `?` inside ONE path segment; iterative, O(len(p)*len(s)) worst case, no regex."""
    pi = si = 0
    star, mark = -1, 0
    while si < len(s):
        if pi < len(p) and (p[pi] == "?" or p[pi] == s[si]):
            pi += 1
            si += 1
        elif pi < len(p) and p[pi] == "*":
            star, mark = pi, si
            pi += 1
        elif star != -1:
            pi = star + 1
            mark += 1
            si = mark
        else:
            return False
    while pi < len(p) and p[pi] == "*":
        pi += 1
    return pi == len(p)


def glob_match(pattern: str, path: str) -> bool:
    """Segment matcher: `**` = zero or more segments, `*`/`?` never cross `/`; a pattern without `/` matches at any depth."""
    if "/" not in pattern:
        pattern = "**/" + pattern
    ps, ss = pattern.split("/"), path.split("/")
    if len(ss) > MAX_SEGMENTS:
        raise Denied("policy.path_invalid", "path has too many segments")
    memo: dict = {}

    def m(i: int, j: int) -> bool:
        key = (i, j)
        if key in memo:
            return memo[key]
        if i == len(ps):
            r = j == len(ss)
        elif ps[i] == "**":
            r = m(i + 1, j) or (j < len(ss) and m(i, j + 1))
        elif j == len(ss):
            r = False
        else:
            r = _seg_match(ps[i], ss[j]) and m(i + 1, j + 1)
        memo[key] = r
        return r
    return m(0, 0)


def path_denied(patterns: Sequence[str], canonical: str) -> bool:
    """A deny pattern matches the path OR ANY ANCESTOR DIRECTORY of it (IS-P3): match `pattern/**`."""
    for pat in patterns:
        if glob_match(pat.rstrip("/") + "/**" if not pat.endswith("**") else pat, canonical):
            return True
    return False


def _glob_to_re(pat: str):          # kept for old callers; NOT used by the guards any more
    class _M:
        def match(self, s):
            return glob_match(pat, s)
    return _M()


# ---------------------------------------------------------------- sizes / durations
_SIZE = re.compile(r"^\s*([0-9]+(?:\.[0-9]+)?)\s*([a-zA-Z]*)\s*$")
_UNITS = {"": 1, "b": 1, "kb": 10**3, "mb": 10**6, "gb": 10**9, "kib": 2**10, "mib": 2**20, "gib": 2**30}
_DUR = {"": 1, "s": 1, "m": 60, "h": 3600}


def parse_size(v):
    if v is None or isinstance(v, (int, float)):
        return None if v is None else int(v)
    m = _SIZE.match(str(v))
    if not m or m.group(2).lower() not in _UNITS:
        raise ValueError(f"invalid size {v!r}; use e.g. 10MB, 1GiB or an integer number of bytes")
    return int(float(m.group(1)) * _UNITS[m.group(2).lower()])


def parse_duration(v):
    if v is None or isinstance(v, (int, float)):
        return v
    m = _SIZE.match(str(v))
    if not m or m.group(2).lower() not in _DUR:
        raise ValueError(f"invalid duration {v!r}; use e.g. 90s, 5m or a number of seconds")
    return float(m.group(1)) * _DUR[m.group(2).lower()]


# ---------------------------------------------------------------- system deny list (IS-F1, IS-L1)
SYSTEM_DENY = ("/proc", "/sys", "/dev")      # non-removable, prefix semantics
_PROTECTED: set = set()                       # state dir, tools dir, config dir, policy.d ... (registered at startup)


def protect_dir(path: str) -> None:
    _PROTECTED.add(os.path.realpath(path))


def system_denied(real: str) -> bool:
    return any(_within(real, d) for d in SYSTEM_DENY) or any(_within(real, d) for d in _PROTECTED)


# ---------------------------------------------------------------- PathScope
_PRINCIPAL_ID = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")


@dataclasses.dataclass(frozen=True, init=False)
class PathScope:
    roots: tuple = ()
    deny: tuple = ()
    readonly: bool = False
    symlinks: str = "within"      # within | deny
    max_bytes: int | None = None
    allow_hardlinks: bool = False
    anywhere_unsafe: bool = False

    def __init__(self, *roots, deny=(), readonly=False, symlinks="within", max_bytes=None, allow_hardlinks=False,
                 _anywhere=False, **kw):
        if "roots" in kw:
            roots = tuple(kw.pop("roots"))
        _anywhere = bool(kw.pop("anywhere_unsafe", False)) or _anywhere
        if kw:
            raise TypeError(f"PathScope got unexpected argument(s) {sorted(kw)}; valid: roots, deny, readonly, "
                            f"symlinks, max_bytes, allow_hardlinks")
        if len(roots) == 1 and isinstance(roots[0], (list, tuple)):
            roots = tuple(roots[0])
        if symlinks not in ("within", "deny"):
            raise ValueError(f"symlinks must be 'within' or 'deny', got {symlinks!r}")
        roots = tuple(str(r) for r in roots)
        if not _anywhere:
            for r in roots:
                if any(c in r for c in "*?["):
                    raise ValueError(f"allow roots are prefixes, not globs ({r!r}); use deny=(...) for patterns")
                if os.path.normpath(r) == "/":
                    raise ValueError("root '/' is refused: name a subtree, or use PathScope.anywhere(unsafe=True)")
        deny = (deny,) if isinstance(deny, str) else tuple(deny)
        for pat in deny:
            if str(pat).count("**") > MAX_DOUBLESTAR:
                raise ValueError(f"deny pattern {pat!r} has more than {MAX_DOUBLESTAR} '**'")
        object.__setattr__(self, "roots", roots)
        object.__setattr__(self, "deny", deny)
        object.__setattr__(self, "readonly", bool(readonly))
        object.__setattr__(self, "symlinks", symlinks)
        object.__setattr__(self, "max_bytes", parse_size(max_bytes))
        object.__setattr__(self, "allow_hardlinks", bool(allow_hardlinks))
        object.__setattr__(self, "anywhere_unsafe", bool(_anywhere))

    @classmethod
    def anywhere(cls, *, unsafe=False, **kw):
        """Whole filesystem (minus the system deny list). A lint error unless `unsafe=True` is spelled out."""
        if not unsafe:
            raise ValueError("PathScope.anywhere() disables jailing; pass unsafe=True to confirm")
        return cls("/", _anywhere=True, **kw)

    def with_roots(self, *roots):
        return dataclasses.replace(self, roots=tuple(os.path.realpath(r) for r in roots))

    def bind(self, principal) -> "PathScope":
        """Substitute `{principal.id}` in roots (multi-tenant jails); the id is validated as one safe path component."""
        if not any("{principal.id}" in r for r in self.roots):
            return self
        pid = getattr(principal, "id", "")
        if not _PRINCIPAL_ID.match(pid) or pid in (".", ".."):
            raise Denied("policy.scope_unbound", "principal id cannot be used in a path")
        return dataclasses.replace(self, roots=tuple(r.replace("{principal.id}", pid) for r in self.roots))


def _within(path: str, root: str) -> bool:
    return path == root or path.startswith(root.rstrip("/") + "/")


def resolve_path(scope: PathScope, raw: str, effect: str = "read", anchor: str | None = None) -> str:
    """Policy check, run ONCE. Returns the canonical path the handler MUST use (deny rules use the same string)."""
    if not isinstance(raw, str) or "\x00" in raw or len(raw) > MAX_PATH or len(raw.split("/")) > MAX_SEGMENTS:
        raise Denied("policy.path_invalid", "invalid path")
    if any("{" in r for r in scope.roots):
        raise Denied("policy.scope_unbound", "path scope has an unbound template")
    roots = tuple(os.path.realpath(r) for r in scope.roots)
    if not roots:
        raise Denied("policy.path_not_allowed", "no path roots configured")
    if os.path.isabs(raw):
        cand = raw
    else:
        if anchor is None and len(roots) > 1:
            raise Denied("policy.path_invalid", "relative path with several roots needs an explicit anchor")
        cand = os.path.join(anchor or roots[0], raw)
    cand = os.path.normpath(cand)               # lexical: collapses '..' only AFTER anchoring
    if cand.startswith("//"):
        cand = "/" + cand.lstrip("/")
    if system_denied(cand):
        raise Denied("policy.path_denied", "path is in the protected system area")
    if scope.symlinks == "deny":
        root = next((r for r in roots if _within(os.path.abspath(cand), r)), None)
        if root is None:
            raise Denied("policy.path_not_allowed", "path outside allowed roots")
        cur = root
        for part in [p for p in os.path.relpath(cand, root).split("/") if p and p != "."]:
            cur = os.path.join(cur, part)
            try:
                if stat.S_ISLNK(os.lstat(cur).st_mode):
                    raise Denied("policy.symlink_denied", "symlinks are not allowed")
            except FileNotFoundError:
                break
    real = os.path.realpath(cand)               # follows links; non-strict so new files resolve
    if system_denied(real):
        raise Denied("policy.path_denied", "path is in the protected system area")
    if not any(_within(real, r) for r in roots):
        raise Denied("policy.path_not_allowed", "path outside allowed roots")
    if path_denied(scope.deny, real) or path_denied(scope.deny, cand):
        raise Denied("policy.path_denied", "path matches a deny rule")
    if scope.readonly and effect in ("write", "delete"):
        raise Denied("policy.read_only", "scope is read-only")
    return real


def _walk_to_parent(scope: PathScope, real: str):
    roots = tuple(os.path.realpath(r) for r in scope.roots)
    root = next((r for r in roots if _within(real, r)), None)
    if root is None:
        raise Denied("policy.path_not_allowed", "path outside allowed roots")
    if system_denied(real):
        raise Denied("policy.path_denied", "path is in the protected system area")
    parts = [p for p in os.path.relpath(real, root).split("/") if p and p != "."]
    return root, parts


def _open_dir_nofollow(name, dir_fd=None):
    import errno
    try:
        return os.open(name, os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_NOFOLLOW", 0) | os.O_CLOEXEC,
                       dir_fd=dir_fd)
    except OSError as exc:
        if exc.errno in (errno.ELOOP, errno.ENOTDIR):
            raise Denied("policy.path_changed", "path changed after policy check") from exc
        raise


def open_beneath(scope: PathScope, real: str, flags: int, mode: int = 0o644, want_dir: bool = False) -> int:
    """Race-free open: walk `real` (already canonical) from a root dir fd, O_NOFOLLOW at EVERY component.

    Never passes O_TRUNC to open(); truncates with ftruncate() after fstat() proved a regular file.  Regular files
    only (FIFOs/devices/sockets: policy.not_regular_file, IS-F4); hard-linked files are refused when the scope has
    deny entries or is writable (IS-F5) unless allow_hardlinks.
    """
    import errno
    root, parts = _walk_to_parent(scope, real)
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for i, part in enumerate(parts):
            last = i == len(parts) - 1
            try:
                if last and not want_dir:
                    nfd = os.open(part, (flags & ~os.O_TRUNC) | nofollow | os.O_CLOEXEC | os.O_NONBLOCK, mode,
                                  dir_fd=fd)
                else:
                    nfd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | nofollow | os.O_CLOEXEC, dir_fd=fd)
            except OSError as exc:
                if exc.errno in (errno.ELOOP, errno.ENOTDIR):
                    raise Denied("policy.path_changed", "path changed after policy check") from exc
                if exc.errno == errno.ENXIO:
                    raise Denied("policy.not_regular_file", "not a regular file") from exc
                raise
            os.close(fd)
            fd = nfd
        st = os.fstat(fd)
        if want_dir:
            if not stat.S_ISDIR(st.st_mode):
                raise Denied("policy.not_regular_file", "not a directory")
            return fd
        if not parts or not stat.S_ISREG(st.st_mode):
            raise Denied("policy.not_regular_file", "not a regular file")
        if st.st_nlink > 1 and (scope.deny or not scope.readonly) and not scope.allow_hardlinks:
            raise Denied("policy.hardlink_denied", "hard-linked files are not served by this scope")
        os.set_blocking(fd, True)
        if flags & os.O_TRUNC:
            os.ftruncate(fd, 0)
        return fd
    except BaseException:
        os.close(fd)
        raise


def open_parent_beneath(scope: PathScope, real: str):
    """For delete/move/mkdir: returns (parent_dir_fd, final_name); the caller uses *at() calls only (IS-F2)."""
    root, parts = _walk_to_parent(scope, real)
    if not parts:
        raise Denied("policy.path_invalid", "cannot operate on a root directory")
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for part in parts[:-1]:
            nfd = _open_dir_nofollow(part, fd)
            os.close(fd)
            fd = nfd
        return fd, parts[-1]
    except BaseException:
        os.close(fd)
        raise


def unlink_beneath(scope: PathScope, real: str) -> None:
    dfd, name = open_parent_beneath(scope, real)
    try:
        if stat.S_ISDIR(os.stat(name, dir_fd=dfd, follow_symlinks=False).st_mode):
            os.rmdir(name, dir_fd=dfd)
        else:
            os.unlink(name, dir_fd=dfd)
    finally:
        os.close(dfd)


def open_verified(scope: PathScope, real: str, flags: int, mode: int = 0o644) -> int:
    return open_beneath(scope, real, flags, mode)


# ---------------------------------------------------------------- process hardening (IS-C6)
def harden_process() -> bool:
    """prctl(PR_SET_DUMPABLE, 0) + no core dumps: /proc/<pid>/{environ,mem,fd} become unreadable to same-uid children."""
    try:
        import ctypes, resource
        ok = ctypes.CDLL(None, use_errno=True).prctl(4, 0, 0, 0, 0) == 0     # PR_SET_DUMPABLE = 4
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        return ok
    except Exception:
        return False


# ---------------------------------------------------------------- URL scope (IS-U1, IS-U1b)
CGNAT = ipaddress.ip_network("100.64.0.0/10")


def block_private(host: str) -> bool:
    """True when `host` (a literal address) must not be fetched: anything that is not globally routable."""
    try:
        ip = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return False
    if getattr(ip, "ipv4_mapped", None):
        ip = ip.ipv4_mapped
    return (not ip.is_global) or ip.is_multicast or (ip.version == 4 and ip in CGNAT)


@dataclasses.dataclass(frozen=True)
class UrlScope:
    hosts: tuple = ()
    schemes: tuple = ("https",)
    ports: tuple = ()
    paths: tuple = ("/**",)
    block_private: bool = True

    def __post_init__(self):
        sv = object.__setattr__
        for f in ("hosts", "schemes", "ports", "paths"):
            v = getattr(self, f)
            sv(self, f, (v,) if isinstance(v, (str, int)) else tuple(v))


_NUMERIC_HOST = re.compile(r"^[0-9a-fx.]+$", re.I)


def check_url(scope: UrlScope, url: str) -> str:
    """Parse ONCE with a strict parser and compare the parsed host; return the canonical URL the handler must use."""
    if not isinstance(url, str) or len(url) > 2048 or any(ord(c) <= 32 or ord(c) >= 127 or c == "\\" for c in url):
        raise Denied("policy.url_invalid", "invalid URL")
    try:
        sp = urlsplit(url)
        port = sp.port
    except ValueError:
        raise Denied("policy.url_invalid", "invalid URL")
    if "@" in sp.netloc or sp.fragment or not sp.hostname:
        raise Denied("policy.url_invalid", "userinfo, fragments and empty hosts are not allowed")
    scheme, host = sp.scheme.lower(), sp.hostname.lower()
    if scheme not in scope.schemes:
        raise Denied("policy.url_denied", "scheme not allowed")
    default = {"http": 80, "https": 443}.get(scheme)
    if scope.ports and (port or default) not in scope.ports:
        raise Denied("policy.url_denied", "port not allowed")
    try:
        ipaddress.ip_address(host)
        literal = True
    except ValueError:
        literal = False
    if not literal and not re.fullmatch(r"[a-z0-9]([a-z0-9.-]*[a-z0-9])?", host):
        raise Denied("policy.url_invalid", "host contains characters outside letters, digits, '-' and '.'")
    if not literal and _NUMERIC_HOST.match(host):
        raise Denied("policy.url_invalid", "numeric host in a non-standard notation")
    if scope.block_private and literal and block_private(host):
        raise Denied("policy.url_denied", "private, loopback, link-local or metadata address")
    if not any(host == h.lower() or (h.startswith("*.") and host.endswith(h[1:].lower()) and host != h[2:].lower())
               for h in scope.hosts):
        raise Denied("policy.url_denied", "host not allowed")
    if not any(glob_match(p, sp.path or "/") for p in scope.paths):
        raise Denied("policy.url_denied", "path not allowed")
    return f"{scheme}://{host}{':' + str(port) if port else ''}{sp.path or '/'}{'?' + sp.query if sp.query else ''}"


# ---------------------------------------------------------------- commands
ESCAPE_CAPABLE = {"sh", "bash", "dash", "zsh", "env", "xargs", "find", "awk", "gawk", "perl", "python", "python3",
                  "node", "ruby", "php", "lua", "git", "make", "ssh", "vi", "vim", "less", "more", "man", "nice",
                  "nohup", "timeout", "strace", "time", "tar", "sed", "busybox", "docker", "sudo", "su", "script"}
PROJECT_FILE = {"pytest", "make", "npm", "npx", "yarn", "pnpm", "go", "cargo", "mvn", "gradle", "tox", "nox", "pip",
                "uv", "poetry"}
WRITERS = {"cp", "mv", "tee", "dd", "curl", "wget", "rsync", "install", "ln", "zip", "unzip", "tar"}
NETWORK = {"curl", "wget", "ssh", "scp", "nc", "socat"}
READONLY_UTILS = {"cat", "ls", "head", "tail", "wc", "stat", "file", "grep"}

ENV_NEVER = ("PATH", "HOME", "USER", "SHELL", "TMPDIR", "LD_*", "DYLD_*", "PYTHON*", "NODE_*", "npm_config_*",
             "NPM_*", "PIP_*", "UV_*", "JAVA_*", "_JAVA_*", "JDK_JAVA_OPTIONS", "GCONV_PATH", "LOCPATH", "NLSPATH",
             "HOSTALIASES", "*_PROXY", "*_proxy", "SSL_*", "CURL_*", "REQUESTS_*", "GIT_*", "BASH_*", "ENV", "IFS",
             "SHELLOPTS", "PS4", "PROMPT_COMMAND", "LESSOPEN", "LESSCLOSE", "PERL*", "RUBY*", "XDG_*", "EBX_*",
             "*_API_KEY", "*_BASE_URL", "*_TOKEN")
DENY_ENV_DEFAULT = ENV_NEVER                      # kept name for callers; the list can only grow
_ENV_VALUE = re.compile(r"^[A-Za-z0-9_@%+=:,./-]{0,256}$")
_ENV_SNAPSHOT: dict = dict(os.environ)             # env_pass reads THIS, never the live environment (IS-C2c)


def snapshot_env() -> None:
    _ENV_SNAPSHOT.clear()
    _ENV_SNAPSHOT.update(os.environ)


def env_never(name: str) -> bool:
    return any(fnmatch.fnmatchcase(name, pat) for pat in ENV_NEVER)


_WORD = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.@:+=,-]*$")
_INT = re.compile(r"^[0-9]{1,9}$")
_GLOB = re.compile(r"[*?\[]")


def expand_short_flags(argv):
    out = []
    for a in argv:
        if re.fullmatch(r"-[A-Za-z]{2,}", a):
            out += ["-" + c for c in a[1:]]
        else:
            out.append(a)
    return out


def _token_match(t: str, a: str, strict: bool) -> bool:
    """One argv element vs one literal/glob token: `*` never crosses '/', '.'/'..' segments never match a glob (IS-C1)."""
    if not _GLOB.search(t):
        return t == a
    if strict and "/" in a and any(seg in ("..", ".") for seg in a.split("/")[1:] + [a.split("/")[0]]):
        raise Denied("policy.command_invalid", "'.'/'..' path segments are not accepted in arguments")
    if "/" in t or "/" in a:
        return "/" in t and "/" in a and glob_match(t, a)
    return _seg_match(t, a)


def match_argv(pattern: Sequence[str], argv: Sequence[str], typed: list | None = None, strict: bool = True) -> bool:
    """Tokens: literal/glob (1:1, segment-aware), '...' (0..n args), '{path}' / '{path:w}' / '{path:rw}',
    '{int}', '{word}'.  `typed` collects (argv_index, effect) for path tokens."""
    p, a = list(pattern), list(argv)

    def rec(i, j, acc):
        if i == len(p):
            return acc if j == len(a) else None
        if p[i] == "...":
            for k in range(j, len(a) + 1):
                r = rec(i + 1, k, acc)
                if r is not None:
                    return r
            return None
        if j == len(a):
            return None
        t = p[i]
        if t in ("{path}", "{path:w}", "{path:rw}"):
            ok = bool(a[j]) and not a[j].startswith("-") and "\x00" not in a[j]
            eff = "read" if t == "{path}" else "write"
            return rec(i + 1, j + 1, acc + [(j, eff)]) if ok else None
        if t == "{int}":
            return rec(i + 1, j + 1, acc) if _INT.match(a[j]) else None
        if t == "{word}":
            return rec(i + 1, j + 1, acc) if _WORD.match(a[j]) else None
        return rec(i + 1, j + 1, acc) if _token_match(t, a[j], strict) else None
    r = rec(0, 0, [])
    if r is None:
        return False
    if typed is not None:
        typed.extend(r)
    return True


@dataclasses.dataclass(frozen=True)
class CommandScope:
    allow: tuple = ()               # patterns (str, shlex-split) or tuples
    deny: tuple = ()
    shell: bool = False
    exec_dirs: tuple = ("/usr/bin", "/bin", "/usr/local/bin")
    cwd: PathScope | None = None
    env_pass: tuple = ("PATH", "LANG", "HOME")      # copied from the STARTUP snapshot of the server environment
    env_set: tuple = ()                              # exact names the CALLER may set (default: none)
    env_deny: tuple = ENV_NEVER
    timeout: float = 60.0
    max_output_bytes: int = 1_000_000
    unrestricted_unsafe: bool = False

    def __post_init__(self):
        sv = object.__setattr__
        if isinstance(self.cwd, (str, list, tuple)):
            sv(self, "cwd", PathScope(self.cwd) if isinstance(self.cwd, str) else PathScope(*self.cwd))
        sv(self, "allow", (self.allow,) if isinstance(self.allow, str) else tuple(self.allow))
        sv(self, "deny", (self.deny,) if isinstance(self.deny, str) else tuple(self.deny))
        sv(self, "env_set", (self.env_set,) if isinstance(self.env_set, str) else tuple(self.env_set))
        sv(self, "timeout", parse_duration(self.timeout))
        sv(self, "max_output_bytes", parse_size(self.max_output_bytes))
        bad = [n for n in self.env_set if env_never(n) or any(c in n for c in "*?[")]
        if bad:
            raise ValueError(f"env_set may not contain {bad}: names are exact, and PATH/HOME/LD_*/proxies/EBX_*/"
                             f"*_API_KEY... are never settable by callers (ENV_NEVER)")

    @classmethod
    def unrestricted(cls, *, unsafe=False, **kw):
        """Any argv resolved from exec_dirs. A lint error unless `unsafe=True`; never the result of an omission."""
        if not unsafe:
            raise ValueError("CommandScope.unrestricted() allows every command; pass unsafe=True to confirm")
        return cls(allow=("...",), unrestricted_unsafe=True, **kw)

    @property
    def timeout_max(self):
        return self.timeout

    @staticmethod
    def _p(x):
        return tuple(shlex.split(x)) if isinstance(x, str) else tuple(x)

    def lint(self, write_roots=()):
        warn = []
        cwd_roots = [os.path.realpath(r) for r in (self.cwd.roots if self.cwd else ())]
        for pat in self.allow:
            toks = self._p(pat)
            exe = os.path.basename(toks[0]) if toks else ""
            loose = "..." in toks or any(_GLOB.search(t) for t in toks[1:])
            if exe in ESCAPE_CAPABLE and loose:
                warn.append(f"error: allow pattern {pat!r}: '{exe}' can execute arbitrary code; pin all arguments")
            if exe in PROJECT_FILE:
                if any(_within(c, w) or _within(w, c) for c in cwd_roots for w in write_roots):
                    warn.append(f"error: allow pattern {pat!r}: '{exe}' runs project files (conftest.py, Makefile, "
                                f"scripts) and this policy lets callers write under its cwd: arbitrary code execution")
                else:
                    warn.append(f"warn: allow pattern {pat!r}: '{exe}' runs project files; keep the workspace read-only")
            if exe in NETWORK:
                warn.append(f"warn: allow pattern {pat!r}: '{exe}' reaches the network")
            if exe in WRITERS and exe not in NETWORK:
                warn.append(f"warn: allow pattern {pat!r}: '{exe}' writes files; check readonly scopes")
            if exe in WRITERS and exe in NETWORK:
                warn.append(f"warn: allow pattern {pat!r}: '{exe}' writes files and reaches the network")
            if toks and any("/" in t and _GLOB.search(t) for t in toks[1:]):
                warn.append(f"error: allow pattern {pat!r}: a glob token that can match paths; write {{path}} instead")
            if exe not in READONLY_UTILS and "{path}" in toks and self.cwd is not None and self.cwd.readonly:
                warn.append(f"error: allow pattern {pat!r}: '{exe}' is not a read-only utility but the cwd scope is readonly")
        if self.shell:
            warn.append("error: shell=True: argv patterns cannot constrain a shell line")
        if self.unrestricted_unsafe:
            warn.append("error: unrestricted command scope")
        return warn


def normalise_argv(command, argv, shell=False):
    """ONE argv for every policy step (IS-P2b). `command` xor `argv`; shell mode is never admitted by a scope."""
    if shell:
        raise Denied("policy.shell_not_allowed", "shell mode is not allowed")
    if command and argv:
        raise Denied("args.invalid", "give either `command` or `argv`, not both")
    if argv is None:
        try:
            argv = shlex.split(command or "")
        except ValueError as exc:
            raise Denied("policy.command_invalid", f"unparseable command: {exc}")
    argv = list(argv)
    if not argv or any(not isinstance(x, str) or "\x00" in x for x in argv):
        raise Denied("policy.command_invalid", "empty or invalid command")
    return argv


def argv_denied(patterns, argv) -> bool:
    base = [os.path.basename(argv[0])] + list(argv[1:])
    for d in patterns:
        dp = tuple(shlex.split(d)) if isinstance(d, str) else tuple(d)
        if any(match_argv(dp, v, strict=False) for v in (argv, expand_short_flags(argv), base, expand_short_flags(base))):
            return True
    return False


def check_command(scope: CommandScope, command: str | None, argv: Sequence[str] | None, shell: bool = False):
    """Returns (argv, executable, path_effects). Raises Denied."""
    argv = normalise_argv(command, argv, shell)
    if argv_denied(scope.deny, argv):
        raise Denied("policy.command_denied", "command matches a deny rule")
    exe0 = argv[0]
    if "/" in exe0:
        exe = exe0
    else:
        exe = next((os.path.join(d, exe0) for d in scope.exec_dirs if os.access(os.path.join(d, exe0), os.X_OK)),
                   None)
        if exe is None:
            raise Denied("policy.command_not_found", f"executable {exe0!r} not found in allowed directories")
    if not any(_within(os.path.dirname(os.path.abspath(exe)), os.path.realpath(d)) or
               os.path.dirname(os.path.abspath(exe)) == d for d in scope.exec_dirs):
        raise Denied("policy.executable_not_allowed", "executable outside allowed directories")
    if scope.unrestricted_unsafe:
        return argv, exe, []
    exe_name = os.path.basename(exe0)
    for pat in scope.allow:
        typed: list = []
        if match_argv(scope._p(pat), [exe0] + argv[1:], typed) or match_argv(scope._p(pat), [exe] + argv[1:], typed):
            out = list(argv)
            effects = []
            for idx, eff in typed:
                if scope.cwd is None:
                    raise Denied("policy.path_not_allowed", "{path} tokens need a path scope (cwd=...)")
                if eff == "read" and exe_name not in READONLY_UTILS:
                    eff = "write"                       # `{path}` of a non-read-only program may be written
                out[idx] = resolve_path(scope.cwd, out[idx], eff)   # canonical value is what gets executed
                effects.append((idx, eff))
            return out, exe, effects
    raise Denied("policy.command_not_allowed", "command is not in the allowlist")


def filter_env(scope: CommandScope, env: dict | None) -> dict:
    out = {k: _ENV_SNAPSHOT[k] for k in scope.env_pass if k in _ENV_SNAPSHOT}
    for k, v in (env or {}).items():
        if env_never(k) or any(fnmatch.fnmatchcase(k, pat) for pat in scope.env_deny):
            raise Denied("policy.env_var_denied", f"environment variable {k!r} is not allowed")
        if k not in scope.env_set:
            raise Denied("policy.env_var_denied", f"environment variable {k!r} may not be set by callers "
                                                   f"(allow it with env_set=(...))")
        if not isinstance(v, (str, int)) or not _ENV_VALUE.match(str(v)):
            raise Denied("policy.env_var_denied", f"value of {k!r} has characters outside the safe set")
        out[k] = str(v)
    return out
