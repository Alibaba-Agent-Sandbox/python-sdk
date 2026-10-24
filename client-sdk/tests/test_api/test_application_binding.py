"""Application namespace and credential boundary regressions."""

import httpx
import pytest

from agent_sandbox.api.server_client import ServerClient
from agent_sandbox.models.errors import ConnectionError_, ServerAPIError


@pytest.mark.parametrize("strip_bearer", [False, True])
async def test_application_token_survives_proxy_without_breaking_bearer_services(strip_bearer):
    requests = []

    def handler(request):
        requests.append(request)
        accepted = (
            request.headers.get("X-Access-Token") == "app-example"
            if strip_bearer
            else request.headers.get("Authorization") == "Bearer app-example"
        )
        return httpx.Response(200 if accepted else 401, json={"commands": []})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        client = ServerClient("https://gateway/owned", token="app-example", http_client=http)
        await client.commands.list()
        assert len(requests) == 1


@pytest.mark.parametrize("injected", [False, True])
@pytest.mark.parametrize("name", ["X-Access-Token", "x-aCcEsS-tOkEn"])
async def test_application_token_never_replaces_gateway_access_token(injected, name):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"commands": []})

    gateway = {name: "gateway-example"}
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), headers=gateway if injected else None
    ) as http:
        client = ServerClient(
            "https://gateway/owned",
            token="app-example",
            headers=None if injected else gateway,
            http_client=http,
        )
        await client.commands.list()
        assert requests[0].headers.get_list("X-Access-Token") == ["gateway-example"]
        assert requests[0].headers["Authorization"] == "Bearer app-example"
        await client.aclose()
        assert not http.is_closed


def test_application_token_rotation_does_not_persist_generated_headers():
    client = ServerClient("https://gateway/owned", token="first-example")
    assert client.auth_headers()["X-Access-Token"] == "first-example"
    rotated = client.with_token("second-example")
    assert rotated.auth_headers()["X-Access-Token"] == "second-example"
    assert rotated.auth_headers()["Authorization"] == "Bearer second-example"
    assert client.with_token(None).auth_headers() == {}


async def test_proxy_prefix_and_signature_query_are_preserved():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"commands": []})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True)
    client = ServerClient(
        "https://gateway/proxy/sandbox-a/9000?sig=a%2Fb&key=one&other=two",
        headers={"X-Gateway-Token": "gateway-example"},
        token="application-example",
        http_client=http,
    )
    await client.commands.list()
    request = requests[0]
    assert request.url.path == "/proxy/sandbox-a/9000/commands"
    assert request.url.query == b"sig=a%2Fb&key=one&other=two"
    assert request.headers["X-Gateway-Token"] == "gateway-example"
    assert request.headers["Authorization"] == "Bearer application-example"
    assert "sig=" not in repr(client) and "sig=" not in client.base_url
    await http.aclose()


@pytest.mark.parametrize(
    "location", ["https://foreign/sandbox-b", "/proxy/sandbox-b/9000/commands"]
)
async def test_redirects_refused_even_with_injected_follow_redirect_client(location):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(302, headers={"Location": location})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True)
    client = ServerClient(
        "https://gateway/proxy/sandbox-a/9000", token="application-example", http_client=http
    )
    with pytest.raises(ServerAPIError, match="redirect"):
        await client.commands.list()
    assert len(requests) == 1
    await http.aclose()


@pytest.mark.parametrize(
    "url", ["https://user:secret@gateway/path", "https://gateway/path#secret", "file:///etc/passwd"]
)
def test_invalid_endpoint_rejected(url):
    with pytest.raises(ValueError):
        ServerClient(url)


@pytest.mark.parametrize(
    "name", ["Host", "hOsT", "Proxy-Authorization", "Content-Length", "Transfer-Encoding"]
)
def test_authority_and_framing_headers_rejected(name):
    with pytest.raises(ValueError):
        ServerClient("https://gateway", headers={name: "override-example"})


def test_gateway_and_application_authorization_cannot_collide():
    with pytest.raises(ValueError):
        ServerClient(
            "https://gateway", headers={"authorization": "gateway-example"}, token="app-example"
        )


@pytest.mark.parametrize(
    "path",
    [
        "/../sandbox-b",
        "//foreign/path",
        "/commands/%2e%2e/x",
        "/commands/%252e%252e/x",
        "/commands/%5c..%5cx",
        "https://foreign/",
    ],
)
def test_operation_path_cannot_escape_bound_namespace(path):
    client = ServerClient("https://gateway/proxy/sandbox-a")
    with pytest.raises(ValueError):
        client._operation_url(path)


async def test_connection_errors_do_not_disclose_signed_endpoint():
    def fail(request):
        raise httpx.ConnectError(str(request.url), request=request)

    http = httpx.AsyncClient(transport=httpx.MockTransport(fail))
    client = ServerClient("https://gateway/prefix?signature=private-example", http_client=http)
    with pytest.raises(ConnectionError_) as caught:
        await client.commands.list()
    assert "private-example" not in str(caught.value)
    assert caught.value.__suppress_context__
    await http.aclose()


@pytest.mark.parametrize("path", ["/%25252e%25252e/foreign", "/%255cforeign", "/%00..", "/%7f.."])
def test_encoded_base_path_cannot_change_namespace(path):
    with pytest.raises(ValueError):
        ServerClient("https://gateway/proxy/owned" + path)


@pytest.mark.parametrize(
    "header", ["Forwarded", "X-Forwarded-Host", "X_Forwarded_Host", "X-Rewrite-URL"]
)
def test_forwarding_authority_headers_are_refused(header):
    with pytest.raises(ValueError):
        ServerClient("https://gateway/proxy/owned", headers={header: "foreign-example"})


def test_query_parameters_cannot_override_gateway_binding():
    client = ServerClient("https://gateway/proxy?path=owned&sig=opaque%2525")
    with pytest.raises(ValueError, match="bound query"):
        client._operation_url("/commands", {"path": "foreign"})
    assert client._operation_url("/commands", {"limit": 1}).endswith(
        "path=owned&sig=opaque%2525&limit=1"
    )


@pytest.mark.parametrize("version", ["2", 2.0, 2.5, True, 3])
async def test_protocol_discovery_refuses_coercion_and_caches_deny_all(version):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"api_version": version, "endpoints": {}})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = ServerClient("https://gateway/proxy/owned", http_client=http)
    with pytest.raises(ServerAPIError, match="protocol discovery"):
        await client.discover()
    assert client.capabilities is not None and not client.capabilities.can("run_command")
    from agent_sandbox.models.errors import EndpointNotAvailableError

    with pytest.raises(EndpointNotAvailableError):
        await client.commands.run("must-not-execute")
    assert len(requests) == 1
    await http.aclose()


@pytest.mark.parametrize(
    "query",
    [
        "sandbox=owned&sandbox=foreign",
        "sandbox=owned&%73andbox=foreign",
        "sandbox=owned&%2573andbox=foreign",
        "Sandbox=owned&sandbox=foreign",
    ],
)
def test_duplicate_decoded_binding_query_keys_rejected(query):
    with pytest.raises(ValueError, match="query keys"):
        ServerClient("https://gateway/owned?" + query)


@pytest.mark.parametrize("key", ["%73andbox", "%2573andbox", "SANDBOX"])
def test_encoded_added_query_key_cannot_override_binding(key):
    client = ServerClient("https://gateway/owned?sandbox=bound&sig=opaque%2525")
    with pytest.raises(ValueError, match="bound query"):
        client._operation_url("/commands", {key: "foreign"})
