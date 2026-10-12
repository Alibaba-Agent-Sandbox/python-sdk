"""T5: a custom op with an authorize hook, written from the card."""
from _t import *
from ebxp.api import op, Registry, SandboxServer, Policy, Principal, Narrow, Deny, Limits, ops, REG

ws = workspace(**{"sub/a.txt": "x"})


@op("custom.grade", effects="exec", paths={"submission": str(ws / "sub")})
def grade(ctx, submission: str) -> dict:
    r = ctx.run(["cat", ctx.paths["submission"]])
    return {"exit_code": r.exit_code, "out": r.stdout}


@op("custom.forgot_effects")
def forgot(ctx) -> dict:
    return {"ok": True}


pol = Policy().allow(ops.custom.grade, principals=["role:grader"], limits=Limits(timeout="30s"))


@pol.authorize
def only_during_exam(ctx):
    if ctx.principal.claims.get("exam_open") is False:
        return Deny("exam closed", code="exam.closed")
    return Narrow(Limits(timeout="10s"))


srv = SandboxServer(pol, tokens={"g" * 20: Principal("g", ("grader",), claims={"exam_open": True})})
g = Principal("g", ("grader",), claims={"exam_open": True})
closed = Principal("g2", ("grader",), claims={"exam_open": False})
check("custom op runs for a grader, the path is jailed", srv.call("custom.grade", principal=g, submission=str(ws / "sub" / "a.txt"))[0] == 200)
check("jail refuses a path outside the op's own scope", srv.call("custom.grade", principal=g, submission="/etc/passwd")[0] == 403)
check("hook can veto with a custom code", srv.call("custom.grade", principal=closed, submission=str(ws / "sub" / "a.txt"))[1].get("code") == "exam.closed")
check("anonymous gets 404 (not mounted for them)", srv.call("custom.grade", principal=Principal("anonymous"), submission="x")[0] == 404)
check("an op without effects= is explicit-only (never granted by effect:/group:/*) and linted",
      not Policy().allow("*").mounted(REG.get("custom.forgot_effects")) and any("effects=" in m for m in REG.lint()))
try:
    SandboxServer(Policy().allow("custom.grad"))
    check("typo custom.grad is rejected at construction", False)
except Exception as e:
    check("typo custom.grad is rejected at construction", "did you mean 'custom.grade'" in str(e), e)
done("T5")
