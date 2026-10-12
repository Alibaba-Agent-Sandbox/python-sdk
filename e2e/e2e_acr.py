"""Best-effort Alibaba Cloud Container Registry (personal edition) REST helpers for cleanup.

Uses the signing helpers shipped with the SDK. Never logs credentials.
"""

from __future__ import annotations

import uuid
from email.utils import formatdate
from typing import Any

import httpx


def _call(method: str, path: str, ak: str, sk: str, region: str, *, params: dict[str, Any] | None = None) -> httpx.Response:
    from easy_sandbox.api.docker_builder import _sign_roa

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Date": formatdate(usegmt=True),
        "x-acs-signature-method": "HMAC-SHA1",
        "x-acs-signature-nonce": str(uuid.uuid4()),
        "x-acs-signature-version": "1.0",
        "x-acs-version": "2016-06-07",
    }
    query = ""
    if params:
        query = "?" + "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    # The canonicalised resource includes the (sorted) query string.
    sig = _sign_roa(method, path + query, headers, sk)
    headers["Authorization"] = f"acs {ak}:{sig}"
    with httpx.Client() as client:
        return client.request(
            method, f"https://cr.{region}.aliyuncs.com{path}{query}", headers=headers, timeout=20
        )


def list_repos(ak: str, sk: str, namespace: str, region: str = "cn-hangzhou") -> list[str]:
    resp = _call("GET", f"/repos/{namespace}", ak, sk, region, params={"Page": 1, "PageSize": 100})
    if resp.status_code != 200:
        raise RuntimeError(f"ACR list repos failed: HTTP {resp.status_code}")
    data = resp.json().get("data", {})
    return [r["repoName"] for r in data.get("repos", [])]


def delete_repo(ak: str, sk: str, namespace: str, repo: str, region: str = "cn-hangzhou") -> bool:
    resp = _call("DELETE", f"/repos/{namespace}/{repo}", ak, sk, region)
    return resp.status_code in (200, 204, 404)
