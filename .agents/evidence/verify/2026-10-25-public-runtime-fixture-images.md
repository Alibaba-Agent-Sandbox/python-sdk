# Verification: public runtime fixture images

- Date: 2026-10-25
- Base: ea4df4e9cf2bdf4ae120f2863e130fb3a318b64b plus scoped fixture/CI/docs changes.
- Runtime: official PyPI agent-sandbox-server0.4.0a2, unchanged published files.
- Local result: PARTIAL; YAML/shell and owner static gates pass. Docker unavailable
  locally; actual builds and HTTP runtime acceptance are required from current-head CI.

## Regression scope

The previous Dockerfiles COPY local wheels before a fallback shell, and install
an unversioned server if reached. This is a source finding; no unavailable local
Docker execution is represented as a pass or an observed build failure.

The existing CI now builds each actual fixture Dockerfile without injecting files,
checks the server distribution version and import inside the image, starts the
image unchanged, checks public health and either the hello business result or
agents runtime listing, and removes the owned container even on failure.
A separate daemon check and inventory confirm cleanup absence. No model CLI or
model endpoint is substituted into these image checks.

## Executed local checks

- PASS: workflow YAML loads; each maintained shell step passes bash-n.
- PASS: public a2 healthcheck help confirms its host/port/timeout contract.
- Owner health/hygiene and remote build/HTTP results: pending before merge.

## Limits

These are SDK offline fixtures, not a new template publishing source or an
OpenSandbox/Express template matrix. Agents runtime listing does not establish
model execution; real Codex/Qwen calls retain their installation/auth requirements.
No cloud resources or external registry uploads were created by local validation.
