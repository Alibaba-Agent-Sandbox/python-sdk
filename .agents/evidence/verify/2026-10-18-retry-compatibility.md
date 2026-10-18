# Verification: legacy retry compatibility documentation

- Date:2026-10-18
- Result:PARTIAL; document/record/hosted checks pending.

Source inspection:Python and CLI HttpClient platform/envd methods do not read
max_retries/retry_base_delay. Python and CLI ExecProvider explicitly forward
max_retries in the EPP connection core. Existing names/defaults/schema and
source files are unchanged by this prose correction. Engine safe-read recovery
and mutation refusal are separately verified by accepted Python PR54; no generic
transport replay is introduced. No cloud run is required to validate this prose;
existing real-component receipts are not relabeled as new executions.
