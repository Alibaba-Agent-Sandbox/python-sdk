"""Run the 8 card-derived template tests + the card import test."""
import pathlib, subprocess, sys
here = pathlib.Path(__file__).resolve().parent
bad = 0
for f in sorted(list(here.glob("t[1-8]_*.py")) + [here / "card_imports.py"]):
    if not f.exists():
        continue
    p = subprocess.run([sys.executable, str(f)], capture_output=True, text=True, cwd=here)
    tail = p.stdout.strip().splitlines()[-1:] or p.stderr.strip().splitlines()[-1:]
    print(f"{'ok  ' if p.returncode == 0 else 'FAIL'} {f.name}: {tail[0] if tail else ''}")
    if p.returncode:
        bad += 1
        print("\n".join(l for l in (p.stdout + p.stderr).splitlines() if l.startswith("FAIL") or "Error" in l)[:1500])
print("templates:", "ALL OK" if not bad else f"{bad} failing")
sys.exit(1 if bad else 0)
