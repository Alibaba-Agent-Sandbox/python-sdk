# Native provider preflight verification — 2026-10-18

Result: scoped local PASS; exact-head full hosted matrix pending.

Base5a99f0fa; Python3.13 with the locked development environment and actual current
client/server sources selected before imports.

- Regression before fix:1 FAIL (session.url accessed on absent context); after:
 1 PASS with ProviderFeatureNotSupportedError before context or wire access.
- Full maintained client2180 PASS/24 SKIP. Lint/format/typecheck PASS for both packages.
- Actual local Express suite112 PASS/2 Volume opt-in SKIP/2 slow DESELECT/1 existing
 KI-009 XFAIL (Jupyter404 and documented shell fallback). No assertion weakened.
- Task tracker cleanup executed; independent complete read-only list confirmed zero
 current-date E2E-tagged sandboxes. No unrelated resource was deleted.
- Server code/distribution metadata are unchanged; full hosted Python3.10/3.11/3.12
 client/server/package matrix is required before merge. No cloud/model Actions run.
- Final owner record/link/hygiene checks follow preparation.

The standard migration and successful account-dependent pause/snapshot acceptance
remain separate in PR47. This patch enables no new capability or package release.
