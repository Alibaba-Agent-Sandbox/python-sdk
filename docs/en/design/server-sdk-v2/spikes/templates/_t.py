"""Shared bits for the template tests. `easy_sandbox.server` in the card == `ebxp.api` in the spike."""
import os, pathlib, sys, tempfile, json, urllib.request, urllib.error
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
R = []


def check(name, cond, extra=""):
    R.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + ((" :: " + str(extra)) if (extra and not cond) else ""))


def done(tag):
    print(f"== {tag}: {sum(R)}/{len(R)}")
    sys.exit(0 if all(R) else 1)


def workspace(**files):
    d = pathlib.Path(tempfile.mkdtemp(prefix="ebx-tpl-")).resolve()
    for n, c in files.items():
        (d / n).parent.mkdir(parents=True, exist_ok=True)
        (d / n).write_text(c)
    return d


def http(port, method, path, body=None, token=None, headers=None):
    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method=method,
                                 data=None if body is None else json.dumps(body).encode())
    if body is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        r = urllib.request.urlopen(req)
        raw = r.read()
        return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")
