# Verification: additional v1 ports and final runtime gates

- Date: 2026-11-12
- Base: consumer freeze `ab50ad8e750b15221c25ccf231caffdc3f196983`.
- Producer: [5cf4482](https://github.com/Alibaba-Agent-Sandbox/awesome-templates/commit/5cf448296361b3bcd8341bd8ae8131f2ca703496).
- Result: PARTIAL. Ports component checks pass; full gates and cloud acceptance remain open.
- Tracker: [templates309](https://github.com/Alibaba-Agent-Sandbox/awesome-templates/issues/309).

## Scope and verified behavior

Additional ports remain declarations, separate from protocol-bearing services. Discovery
and canonical compilation preserve their sorted union with service ports. The prepared
launcher requires `ports.resolve` for declared ports, resolves extra descriptors using the
existing Provider identity/audience/expiry checks, and never constructs a service client or
sends readiness probes for these ports. Descriptor headers stay in memory; plans/journals
contain no gateway token. Port declarations are not native TCP/public access guarantees.
Managed public Gateway/private bridge ports are unchanged.

`python -m pytest client-sdk/tests/test_template_v1_runtime.py
client-sdk/tests/test_api/test_template_launch.py client-sdk/tests/test_api/test_sandbox.py
-q --tb=short`: **189 passed**. This exercised actual Express HTTP serialization with
HTTP mocks, descriptor traffic-token audience, no extra requests/client construction,
provider mismatch cleanup, port union/defaults and existing application behavior.
Native cloud ports were not contacted. Producer source bytes are copied exactly, with
source-lock verification against the actual Git objects.

## Full-suite failure retained

The final `make test` attempt before this ports freeze returned exit2: Server875 passed /
1 skipped; Client2586 passed /20 skipped /1 failed. The existing active-cancel reuse
assertion failed again because its local backend resource had been disposed. This is a
required gate failure; it is not silently converted to a pass or dismissed by a retry.

No Worker cancellation, guest bridge or cancellation-test production behavior changed.
A separate local probe ran the original test with both the unchanged API-contract baseline
`ef61cfebf009ba5ea6783a0a94735cc26e4d0b9b` and the candidate source:

| Variant | Observed process-domain receipt | Original assertion |
| --- | --- | --- |
| Baseline, no controlled new process | `unknown_new_processes=0`, `stop_confirmed=true` | PASS |
| Candidate, no controlled new process | `unknown_new_processes=0`, `stop_confirmed=true` | PASS |
| Baseline, controlled unrelated same-UID child after baseline | `unknown_new_processes=1`, guest `stop_confirmed=false` | FAIL, same resource-reuse assertion |
| Candidate, same controlled child | `unknown_new_processes=1`, guest `stop_confirmed=false` | FAIL, same assertion |

This establishes the existing conservative process-domain behavior on the shared host:
unattributed new processes forbid reuse, and the Worker confirms stopping by destroying
owned compute. It does not prove the reason in the original full-suite failure, which did
not capture process-domain scan counts. No process filters or assertions were weakened.
Controlled child processes were terminated and waited for; baseline worktree was read-only.
The no-side-effect `unshare -Urpf --mount-proc true` probe succeeded. A further
`unshare -Upf --map-current-user --mount-proc id -u` probe preserved the current UID,
which avoids PostgreSQL's root prohibition while isolating `/proc`. The next full run
will use that actual PID/user namespace; no process-observation code is patched.

## Not verified

Cloud/model/FC joint operation, actual arbitrary port reachability, remote Python matrix,
package release and merged delivery. Source metadata version remains0.4.0a7; a pinned
source recipe must not be described as a newly published alpha. This evidence extends,
rather than overwrites, the [earlier freeze record](2026-11-12-template-v1-runtime.md).

`make lint typecheck format-check hygiene`: PASS. Repository health:106 PASS /1 existing
recommended release-guide warning /0 FAIL. Custom staged secret scan and diff checks run
before the source freeze. Full test/CI and cloud gates remain pending at this commit.
