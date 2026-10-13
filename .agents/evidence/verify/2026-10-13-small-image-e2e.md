# Verification: small-image ACR push and base sandbox create (2026-10-13)

Follow-up to KI-011 (full image push too slow from this host). One tiny local image, one short ACR push, and one short-lived sandbox from the public `base` template. Credential values are omitted.

## Result

- Local image `abx-tiny-e2e:dev`: size **119448702** bytes (docker image inspect). Build used cached `python:3.12-slim` plus a one-line `CMD`.
- ACR push: **did not succeed**. Login succeeded. `docker push` was stopped after 180s with no further progress (exit 143, elapsed 243.5s). Two small layers reported `Pushed`; two layers stayed at `Preparing` with 0 bytes shown in the progress lines.
- Sandbox create from public template `base`: **succeeded**, then **kill succeeded**. The sandbox was not left running. See the create section for the earlier failed attempts.

## Docker

- `docker version` server 29.1.3, exit 0.
- Build context: `/tmp/abx-tiny-ctx` (Dockerfile only, 2.048 kB sent).
- Build exit 0, elapsed 0.13 s. Image id `sha256:6d35754c19e7db723c2e801e5d799298d277fe6cd37dc017ede9b4a23c7e5cd9`.

Dockerfile:

```dockerfile
FROM python:3.12-slim
CMD ["python","-c","print(\"abx-tiny-e2e\")"]
```

## Credentials present (names only)

- `ACR_NAMESPACE`: set (non-empty) in `python-sdk/.env`.
- Region: `ALIBABA_CLOUD_REGION_ID` unset. API host in `E2B_API_URL` is `api.cn-hangzhou.e2b.fc.aliyuncs.com`, so login used `cn-hangzhou` / `registry.cn-hangzhou.aliyuncs.com`.
- Alibaba credentials: `AccessKey` and `AccessSecret` set. `ALICLOUD_ACCESS_KEY_ID` / `ALICLOUD_ACCESS_KEY_SECRET` unset.
- `ABX_SANDBOX_API_KEY` unset in `python-sdk/.env`. `E2B_API_KEY` set. Current `create_auth_provider` reads `ABX_SANDBOX_API_KEY` (not `E2B_API_KEY`). The successful create mapped that existing key into `ABX_SANDBOX_API_KEY` in the process only. It was not written back to `.env`.

## ACR login and push

- Image ref: `registry.cn-hangzhou.aliyuncs.com/<ns>/abx-tiny-e2e:dev`
- Login attempted: True
- Login exit: 0 elapsed: 4.86 s mode: temp-token
- Push exit: 143 elapsed: 243.5 s
- Bytes observed in progress lines: 0
- Stop reason: no progress for 180s
- Layers: 15f1c8eb1ab1:preparing, b361fa3b9794:preparing, dca2a125b490:pushed, e1fa2746ad6d:pushed

Last push log lines:

```
The push refers to repository [registry.cn-hangzhou.aliyuncs.com/<ns>/abx-tiny-e2e]
dca2a125b490: Preparing
b361fa3b9794: Preparing
e1fa2746ad6d: Preparing
15f1c8eb1ab1: Preparing
dca2a125b490: Pushed
e1fa2746ad6d: Pushed
```

## Sandbox create (`template=base`, ttl 60s) then kill

Attempt 1, same process as the push, `E2B_API_KEY` exported, `http2` left at the default:

- Create exit: 1
- Elapsed: 1.84 s
- Sandbox id: none (exception before an id was returned)
- Error: `ModuleNotFoundError: No module named 'h2.config'`

`h2` 4.4.1 was installed with `python3 -m pip install --user h2` so the default HTTP/2 client could import.

Attempt 2, after that install, without `ABX_SANDBOX_API_KEY`:

- Create exit: 1
- Elapsed: 0.01 s
- Error: `InvalidAPIKeyError: [E1001] No authentication credentials provided`
- Suggestion text: set `ABX_SANDBOX_API_KEY` or both `ALICLOUD_ACCESS_KEY_ID` and `ALICLOUD_ACCESS_KEY_SECRET`.

Attempt 3, process environment only: `ABX_SANDBOX_API_KEY` set from the existing `E2B_API_KEY` value, `ABX_SANDBOX_BASE_URL` set from `E2B_API_URL` (`https://api.cn-hangzhou.e2b.fc.aliyuncs.com`):

- Create exit: 0
- Elapsed: 2.32 s
- Sandbox id: `sbx-fccf3216-a3ea-4538-912c-770390c0fd2f`
- Template: `base`
- TTL: 60 s
- Metadata: `purpose=abx-tiny-e2e`
- Kill exit: 0
- Kill elapsed: 0.36 s
- Follow-up `Sandbox.list` (limit 100): `list_match_count=0` for that id and for metadata `purpose=abx-tiny-e2e`

## Runner log (redacted)

```
cred_presence ACR_NAMESPACE=True len=23 AccessKey=True ALICLOUD_ACCESS_KEY_ID=False AccessSecret=True ALICLOUD_ACCESS_KEY_SECRET=False ABX_SANDBOX_API_KEY=False E2B_API_KEY=True ALIBABA_CLOUD_REGION_ID=False region_used=cn-hangzhou (from API host, not a dedicated env var)
image_inspect exit=0 size_bytes=119448702 stderr=
acr_login ok elapsed=4.86s mode=temp-token keys=['authorizationToken', 'tempUserName']
docker tag exit=0 elapsed=0.02s stderr=
docker push start ref=registry.cn-hangzhou.aliyuncs.com/<ns>/abx-tiny-e2e:dev stall=180s overall=360s
docker push done exit=143 elapsed=243.5s bytes_seen=0 stopped=no progress for 180s layers=15f1c8eb1ab1:preparing, b361fa3b9794:preparing, dca2a125b490:pushed, e1fa2746ad6d:pushed
push_tail:
The push refers to repository [registry.cn-hangzhou.aliyuncs.com/<ns>/abx-tiny-e2e]
dca2a125b490: Preparing
b361fa3b9794: Preparing
e1fa2746ad6d: Preparing
15f1c8eb1ab1: Preparing
dca2a125b490: Pushed
e1fa2746ad6d: Pushed
sandbox create FAIL elapsed=1.84s ModuleNotFoundError: No module named 'h2.config'
```

