"""reviews/v2.1-disposition.md has exactly one row per finding of the three independent reviews, with a valid disposition."""
import pathlib, re, sys
here = pathlib.Path(__file__).resolve().parents[1] / "reviews"
disp = (here / "v2.1-disposition.md").read_text()
rows = re.findall(r"^\| ((?:IS|IF)-[A-Za-z0-9]+|[TCBN]-\d+) \| (\w+) \| .*? \| (accepted \(partial\)|accepted|rejected|deferred) \| (.+) \|$", disp, re.M)
ids = [r[0] for r in rows]
exp = set(re.findall(r"^#### (IS-[A-Za-z0-9]+)", (here / "independent-security.md").read_text(), re.M))
exp |= set(re.findall(r"^\| ([TCBN]-\d+) \|", (here / "independent-ux-and-ai.md").read_text(), re.M))
exp |= set(re.findall(r"^\*\*(IF-\d+) ", (here / "independent-feasibility.md").read_text(), re.M))
ok = True
for name, cond in [("123 findings in the reviews", len(exp) == 123), ("one row per finding", sorted(ids) == sorted(exp)),
                   ("no duplicate rows", len(ids) == len(set(ids))),
                   ("every row says where it was fixed", all(len(r[3].strip()) > 8 for r in rows)),
                   ("non-accepted rows are justified", all(i in disp.split("## Justifications")[1] for i, _, st, _ in rows if st != "accepted"))]:
    print(("PASS " if cond else "FAIL ") + name); ok &= cond
print(len(rows), "rows;", {k: sum(1 for r in rows if r[2] == k) for k in ("accepted", "accepted (partial)", "rejected", "deferred")})
sys.exit(0 if ok else 1)
