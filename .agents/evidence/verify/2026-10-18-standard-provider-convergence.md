# Standard/provider convergence verification — 2026-10-18

Result: PARTIAL; candidate remains draft.

Ordinary merge of accepted SDK13b214b3 into PR47 original33d75c4f. Python3.13 clean
paired editable environment. No upstream E2B distribution in project runtime.
Separate fresh reference pins e2b2.31.0/interpreter2.8.1.

-354 public callable signatures and sync/async shapes match pinned reference: PASS.
- Native PTY feature test: FAIL before (wire access), PASS after (typed capability refusal).
- Full client2191 PASS/one stale native fixture FAIL/24 SKIP. Correcting the fixture
  back to current canonical ABX contract:90 focused PASS. Earlier config/import
  integration failures were reproduced and corrected, never called passes.
- Maintained lint PASS; mypy56 server/103 client source files PASS. Packaging and
  final format/full suite checks follow after current main metadata convergence.
- Actual standard Express E2E:3 PASS (sync lifecycle/files/stdin/process error,
  interpreter contexts/stream/output, async lifecycle/files/process, real outbound
  network policy denial and restoration); snapshot1 SKIP: no enabled MicroVM
  template/allowlist fixture. Explicit verified Express origin used for credentials.
- Each created resource tracked/tagged and killed in finally; native tracker sweep
  and list readback cleaned the owned run. No unrelated resource was changed.

Native E2B, enabled pause/snapshot success and whole-artifact provenance acceptance
remain distinct prerequisites from passing ordinary CI. No package release or
new hosted model/cloud test workflow is introduced.

After ordinarily merging accepted main5a99f0fa: full client2193 PASS/24 SKIP;
server853 PASS/2 local raw-network FAIL/1 SKIP (proxy changed expected HTTP
framing/WebSocket rejection to502). No assertions or transport checks were removed.
Maintained lint/format PASS; mypy56 server/105 client files PASS; pinned public
contract354 PASS. Both sdist/wheel builds PASS. Paired artifact and record checks
are recorded below; exact-head hosted matrix is separate from these local results.

Final paired distributions:twine check PASS, both py.typed markers PASS, clean
combined wheel installation/import PASS; hygienePASS; health106 PASS/1 historical
WARN/zero FAIL. Exact implementation headcceb318d hosted matrix10/10 PASS.

Documentation audit found the standard sync examples still installed a pre-port
async-root source revision. Updated15 live installation/example guides in both
languages to the verified implementationcceb318d. Actual displayed two-archive
recipe installed in a fresh environment; pip check PASS; synchronous Sandbox/
interpreter, asynchronous AsyncSandbox/ProviderSandbox and server imports PASS.
Neither upstream E2B runtime distribution is present. This changes documentation
only and does not claim a PyPI release. The accepted implementation remains
pinned independently of subsequent documentation-only commits.
