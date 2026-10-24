"""A catalog is a content locator, not a versioned package service."""

from __future__ import annotations

import json

import pytest

from agent_sandbox.models.errors import ProviderInstallError, ProviderTrustError
from agent_sandbox.providers import catalog, installer, store
from tests.iso import iso  # noqa: F401
from tests.test_providers.helpers import write_plugin


@pytest.fixture
def local_catalog(iso, tmp_path, monkeypatch):  # noqa: F811
    source = write_plugin(tmp_path / "plugin")
    index = tmp_path / "index.json"
    index.write_text(
        json.dumps({"providers": [{"id": "demo-prov", "version": "0.1.0", "url": str(source)}]})
    )
    monkeypatch.setenv("ABX_PROVIDER_REGISTRY", str(index))
    return source, index


def test_catalog_update_detects_changed_content_without_version_bump(local_catalog):
    source, _ = local_catalog
    original = installer.install("registry:demo-prov", yes=True)
    assert installer.update("demo-prov", check=True)["status"] == "up-to-date"
    (source / "provider.py").write_text("print('changed')\n")
    assert installer.update("demo-prov", check=True)["status"] == "available"
    assert store.read_receipt("demo-prov") == original
    with pytest.raises(ProviderTrustError):
        installer.update("demo-prov")
    result = installer.update("demo-prov", yes=True)
    assert result["status"] == "updated"
    assert result["installed"] == result["available"] == "0.1.0"
    assert result["receipt"]["tree_sha256"] != original["tree_sha256"]
    assert (store.provider_dir("demo-prov") / "provider.py").read_text() == "print('changed')\n"
    assert installer.update("demo-prov", check=True)["status"] == "up-to-date"


def test_catalog_update_uses_recorded_registry_and_rolls_back(local_catalog, monkeypatch):
    source, index = local_catalog
    original = installer.install("registry:demo-prov", yes=True)
    (source / "provider.py").write_text("print('changed')\n")
    monkeypatch.setenv("ABX_PROVIDER_REGISTRY", "file:missing-index.json")

    def reject(_):
        raise RuntimeError("initialize failed")

    with pytest.raises(RuntimeError, match="initialize failed"):
        installer.update("demo-prov", yes=True, verify=reject)
    assert store.read_receipt("demo-prov") == original
    assert catalog.registry_url() == "file:missing-index.json"
    assert original["source"]["registry"] == str(index)


def test_catalog_id_mismatch_is_rejected(local_catalog):
    source, _ = local_catalog
    installer.install("registry:demo-prov", yes=True)
    write_plugin(source, id="other-provider")
    with pytest.raises(ProviderInstallError, match="id changed"):
        installer.update("demo-prov", yes=True)
    with pytest.raises(ProviderInstallError, match="does not match"):
        installer.install("registry:demo-prov", force=True, yes=True)


def test_update_notice_compares_archive_hash_only(local_catalog):
    _, index = local_catalog
    installer.install("registry:demo-prov", yes=True)
    receipt = store.read_receipt("demo-prov")
    receipt["source"]["archive_sha256"] = "a" * 64
    store.write_receipt(store.provider_dir("demo-prov"), receipt)
    data = json.loads(index.read_text())
    data["providers"][0]["sha256"] = "b" * 64
    index.write_text(json.dumps(data))
    assert catalog.pending_updates() == [
        {"id": "demo-prov", "installed": "0.1.0", "version": "0.1.0"}
    ]
    receipt["source"]["archive_sha256"] = "b" * 64
    store.write_receipt(store.provider_dir("demo-prov"), receipt)
    assert catalog.pending_updates() == []


def test_identical_tree_acknowledges_repacked_archive_only_on_update(local_catalog):
    _, index = local_catalog
    original = installer.install("registry:demo-prov", yes=True)
    data = json.loads(index.read_text())
    data["providers"][0]["sha256"] = "c" * 64
    index.write_text(json.dumps(data))
    assert installer.update("demo-prov", check=True)["status"] == "up-to-date"
    assert store.read_receipt("demo-prov") == original
    assert installer.update("demo-prov")["status"] == "up-to-date"
    refreshed = store.read_receipt("demo-prov")
    assert refreshed["tree_sha256"] == original["tree_sha256"]
    assert refreshed["source"]["archive_sha256"] == "c" * 64
    assert catalog.pending_updates() == []
