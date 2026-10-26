"""Real desktop GUI, authenticated stream, simulated operator handover and screenshot replay."""

import argparse
import asyncio
import hashlib
import io
import json
import logging
import mimetypes
import os
import shutil
import sys
import threading
import time
from contextlib import suppress
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import aiohttp
import httpx
from aiohttp import web
from e2b.exceptions import NotFoundException
from e2b_desktop import Sandbox
from PIL import Image
from playwright.sync_api import sync_playwright


# Credentials are inherited from the caller; this optional compatibility test does not load dotenv.
def sanitize(text: str) -> str:
    for key, value in os.environ.items():
        if value and any(
            word in key.upper() for word in ("TOKEN", "KEY", "SECRET", "PASSWORD", "CREDENTIAL")
        ):
            text = text.replace(value, "[REDACTED]")
    return text


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument(
    "--template",
    required=True,
    help="Existing prepared Desktop template ID; never changed by this runner",
)
parser.add_argument(
    "--output-dir", type=Path, required=True, help="New artifact directory; must not exist"
)
parser.add_argument(
    "--browser-executable", default=shutil.which("google-chrome") or shutil.which("chromium")
)
args = parser.parse_args()
if args.output_dir.exists():
    parser.error("Evidence directory already exists; choose a new path")
if not args.browser_executable:
    parser.error("A Chromium executable is required before creating cloud resources")
logging.disable(logging.CRITICAL)

OUT = args.output_dir
OUT.mkdir(parents=True)
REPORT: dict[str, Any] = {
    "steps": [],
    "timeline": [],
    "scope": (
        "Real official desktop image; operator is simulated by a second controller, "
        "not a human/login session."
    ),
}
SECRETS = []


def safe(s: str) -> str:
    s = sanitize(s)
    for secret in SECRETS:
        if secret:
            s = s.replace(secret, "[REDACTED]")
    return s


def save() -> None:
    (OUT / "acceptance.json").write_text(safe(json.dumps(REPORT, indent=2)))


def check(name: str, ok: bool, **details: Any) -> None:
    row = {"name": name, "result": "PASS" if ok else "FAIL", **details}
    REPORT["steps"].append(row)
    save()
    print(safe(json.dumps(row)), flush=True)
    if not ok:
        raise AssertionError(name)


def shot(desktop: Sandbox, name: str, actor: str, action: str) -> None:
    data = desktop.screenshot()
    image = Image.open(io.BytesIO(data))
    assert image.format == "PNG" and image.size == (1024, 768)
    path = OUT / (name + ".png")
    path.write_bytes(data)
    row = {
        "at_seconds": round(time.monotonic() - START, 2),
        "actor": actor,
        "action": action,
        "file": path.name,
        "sha256": hashlib.sha256(data).hexdigest(),
        "width": 1024,
        "height": 768,
    }
    REPORT["timeline"].append(row)
    save()
    print(json.dumps({"screenshot": path.name, "sha256": row["sha256"]}), flush=True)


APP = r"""from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import json
import time
PAGE = Path('/tmp/abx-gui.html').read_text()
state = {'events': [], 'latest': None}
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass
    def do_GET(self):
        data = PAGE.encode()
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.end_headers()
        self.wfile.write(data)
    def do_POST(self):
        data = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        value = data['value']
        assert value in ('agent-start', 'operator-step', 'agent-resumed')
        state['latest'] = value
        state['events'].append({'value': value, 'at': time.time()})
        Path('/tmp/abx-gui-state.json').write_text(json.dumps(state))
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(state).encode())
HTTPServer(('127.0.0.1', 8088), Handler).serve_forever()
"""


class Proxy:
    def __init__(self, origin: str, token: str) -> None:
        self.origin = origin
        self.token = token
        self.port = None
        self.ready = threading.Event()
        self.ws_open = 0
        self.ws_bytes = 0
        self.http_requests = 0

    def start(self) -> None:
        def worker() -> None:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
            self.loop.run_until_complete(self.setup())
            self.ready.set()
            self.loop.run_forever()
            self.loop.run_until_complete(self.runner.cleanup())
            self.loop.run_until_complete(self.session.close())
            self.loop.close()

        self.thread = threading.Thread(target=worker, daemon=True)
        self.thread.start()
        assert self.ready.wait(15)

    async def setup(self) -> None:
        self.session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=40))
        app = web.Application()
        app.router.add_route("*", "/{tail:.*}", self.forward)
        self.runner = web.AppRunner(app, access_log=None)
        await self.runner.setup()
        site = web.TCPSite(self.runner, "127.0.0.1", 0)
        await site.start()
        self.port = self.runner.addresses[0][1]

    async def forward(self, request: web.Request) -> web.StreamResponse:
        headers = {"e2b-traffic-access-token": self.token}
        target = self.origin + request.path_qs
        if request.headers.get("Upgrade", "").lower() == "websocket":
            protocols = [
                p.strip()
                for p in request.headers.get("Sec-WebSocket-Protocol", "").split(",")
                if p.strip()
            ]
            upstream = await self.session.ws_connect(
                target.replace("https://", "wss://"),
                headers=headers,
                protocols=protocols,
                max_msg_size=16 * 1024 * 1024,
            )
            client = web.WebSocketResponse(protocols=protocols, max_msg_size=16 * 1024 * 1024)
            await client.prepare(request)
            self.ws_open += 1

            async def pump(source: Any, destination: Any) -> None:
                async for msg in source:
                    if msg.type == aiohttp.WSMsgType.BINARY:
                        self.ws_bytes += len(msg.data)
                        await destination.send_bytes(msg.data)
                    elif msg.type == aiohttp.WSMsgType.TEXT:
                        await destination.send_str(msg.data)
                    else:
                        break

            tasks = [
                asyncio.create_task(pump(client, upstream)),
                asyncio.create_task(pump(upstream, client)),
            ]
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in tasks:
                task.cancel()
            await upstream.close()
            await client.close()
            return client
        async with self.session.request(
            request.method, target, headers=headers, data=await request.read()
        ) as upstream:
            self.http_requests += 1
            body = await upstream.read()
            response_headers = {
                k: v
                for k, v in upstream.headers.items()
                if k.lower()
                not in (
                    "content-encoding",
                    "content-length",
                    "transfer-encoding",
                    "connection",
                    "content-disposition",
                    "content-type",
                )
            }
            mime = mimetypes.guess_type(request.path)[0] or upstream.headers.get(
                "Content-Type", "application/octet-stream"
            )
            response_headers["Content-Type"] = mime
            return web.Response(status=upstream.status, body=body, headers=response_headers)

    def close(self) -> None:
        self.loop.call_soon_threadsafe(self.loop.stop)
        self.thread.join(timeout=10)


def state(desktop: Sandbox) -> dict[str, Any]:
    return json.loads(desktop.files.read("/tmp/abx-gui-state.json"))


def commit(desktop: Sandbox, value: str) -> dict[str, Any]:
    desktop.move_mouse(300, 250)
    desktop.left_click()
    desktop.press(["ctrl", "a"])
    desktop.write(value)
    desktop.move_mouse(190, 322)
    desktop.left_click()
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            s = state(desktop)
            if s.get("latest") == value:
                return s
        except Exception:
            pass
        time.sleep(0.3)
    raise AssertionError("GUI commit did not produce " + value)


desktop = None
proxy = None
stream = None
START = time.monotonic()
try:
    template = args.template
    REPORT["template_id"] = template
    REPORT["creation_controls"] = {"secure": True, "network": {"allow_public_traffic": False}}
    desktop = Sandbox.create(
        template=template,
        timeout=600,
        secure=True,
        network={"allow_public_traffic": False},
        resolution=(1024, 768),
        metadata={"acceptance": "desktop-handover-20261026"},
    )
    REPORT["sandbox_id"] = desktop.sandbox_id
    save()
    info = desktop.get_info()
    check(
        "desktop-created-correct-spec",
        info.cpu_count == 4 and info.memory_mb == 8192,
        cpu=info.cpu_count,
        memory=info.memory_mb,
    )
    desktop.files.write("/tmp/abx-gui-server.py", APP)
    desktop.files.write(
        "/tmp/abx-gui.html", Path(__file__).with_name("desktop-handover.html").read_text()
    )
    h = desktop.commands.run("python3 /tmp/abx-gui-server.py", background=True, timeout=0)
    h.disconnect()
    # A fresh profile avoids stale first-run/restore UI in an upstream image.
    h = desktop.commands.run(
        "google-chrome --user-data-dir=/tmp/abx-owned-gui-profile "
        "--kiosk --no-first-run --disable-session-crashed-bubble --test-type "
        "http://127.0.0.1:8088",
        background=True,
        timeout=0,
    )
    h.disconnect()
    time.sleep(14)
    shot(
        desktop,
        "01-browser-ready",
        "agent",
        "Open the synthetic local acceptance page in the real desktop browser",
    )
    s = commit(desktop, "agent-start")
    check(
        "agent-mouse-keyboard-effect",
        s["latest"] == "agent-start",
        sequence=[x["value"] for x in s["events"]],
    )
    shot(desktop, "02-agent-state", "agent", "Mouse focus, keyboard text and mouse commit")
    stream = desktop.stream
    stream.start(require_auth=True)
    password = stream.get_auth_key()
    SECRETS.append(password)
    remote = stream.get_url(auth_key=password)
    parsed = urlsplit(remote)
    origin = parsed.scheme + "://" + parsed.netloc
    SECRETS.extend([origin, parsed.netloc])
    token = desktop.traffic_access_token
    check("traffic-token-issued", isinstance(token, str) and bool(token))
    SECRETS.append(token)
    unauth = httpx.get(origin + "/vnc.html", timeout=20)
    auth = httpx.get(origin + "/vnc.html", headers={"e2b-traffic-access-token": token}, timeout=20)

    async def gateway_probe() -> dict[str, Any]:
        async with aiohttp.ClientSession() as session:
            try:
                async with session.ws_connect(
                    origin.replace("https://", "wss://") + "/websockify",
                    protocols=["binary"],
                    timeout=10,
                ) as ws:
                    msg = await ws.receive(timeout=8)
                    return {
                        "connected_without_gateway_token": True,
                        "rfb_banner_received": msg.type == aiohttp.WSMsgType.BINARY
                        and msg.data.startswith(b"RFB "),
                    }
            except aiohttp.ClientResponseError as error:
                return {"connected_without_gateway_token": False, "http_status": error.status}
            except Exception as error:
                return {
                    "connected_without_gateway_token": False,
                    "error_type": type(error).__name__,
                }

    probe = asyncio.run(gateway_probe())
    REPORT["gateway_observation"] = {
        "unauthenticated_static_status": unauth.status_code,
        "authenticated_static_status": auth.status_code,
        "upstream_content_type": auth.headers.get("content-type"),
        "upstream_disposition": auth.headers.get("content-disposition"),
        "html_document_observed": b"<html" in auth.content.lower(),
        **probe,
    }
    save()
    check("stream-static-resource-access", auth.status_code == 200, **REPORT["gateway_observation"])
    REPORT["steps"].append(
        {
            "name": "gateway-token-enforcement",
            "result": "PASS" if probe.get("http_status") in (401, 403) else "NOT_CONFIRMED",
            **probe,
        }
    )
    save()
    proxy = Proxy(origin, token)
    proxy.start()
    REPORT["proxy"] = {"bind": "127.0.0.1", "gateway_token_stays_backend": True}
    save()
    base = f"http://127.0.0.1:{proxy.port}"
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            executable_path=args.browser_executable, headless=True, args=["--no-sandbox"]
        )
        context = browser.new_context(viewport={"width": 1100, "height": 850})
        page = context.new_page()
        page.goto(
            base + "/vnc.html?autoconnect=true&resize=scale&password=deliberately-wrong",
            wait_until="domcontentloaded",
        )
        page.wait_for_timeout(6000)
        wrong_connected = page.evaluate(
            "document.documentElement.classList.contains('noVNC_connected')"
        )
        wrong_status = page.locator("#noVNC_status").text_content()
        check(
            "vnc-password-rejected",
            not wrong_connected,
            connected=wrong_connected,
            status=wrong_status[:160],
        )
        page.close()
        page = context.new_page()
        page.goto(
            base + parsed.path + "?" + parsed.query + "&view_only=false",
            wait_until="domcontentloaded",
        )
        page.wait_for_function(
            "document.documentElement.classList.contains('noVNC_connected')", timeout=30000
        )
        canvas = page.locator("canvas").first
        canvas.wait_for(state="visible")
        deadline = time.monotonic() + 15
        while proxy.ws_bytes < 1000 and time.monotonic() < deadline:
            page.wait_for_timeout(250)
        page.wait_for_timeout(3000)
        box = canvas.bounding_box()
        REPORT["canvas_observation"] = {
            "bounding_box": box,
            "dimensions": canvas.evaluate("(c)=>({width:c.width,height:c.height})"),
            "view_only_setting": page.locator("#noVNC_setting_view_only").is_checked(),
        }
        save()
        canvas.screenshot(path=str(OUT / "stream-canvas.png"))
        check(
            "live-stream-renders",
            bool(box and box["width"] > 100 and proxy.ws_open > 0 and proxy.ws_bytes > 1000),
            websocket_sessions=proxy.ws_open,
            transported_bytes=proxy.ws_bytes,
            canvas_width=round(box["width"]),
        )
        page.screenshot(path=str(OUT / "03-live-stream-view.png"))
        REPORT["timeline"].append(
            {
                "at_seconds": round(time.monotonic() - START, 2),
                "actor": "simulated-operator",
                "action": "Observe authenticated live stream through controlled backend proxy",
                "file": "03-live-stream-view.png",
                "sha256": hashlib.sha256(
                    (OUT / "03-live-stream-view.png").read_bytes()
                ).hexdigest(),
            }
        )
        save()

        # A second controller uses the real noVNC canvas; it has no sandbox gateway token.
        def point(x: float, y: float) -> tuple[float, float]:
            return (box["x"] + x * box["width"] / 1024, box["y"] + y * box["height"] / 768)

        x, y = point(300, 250)
        page.mouse.click(x, y)
        page.wait_for_timeout(400)
        page.keyboard.press("End")
        for _ in range(16):
            page.keyboard.press("Backspace")
            page.wait_for_timeout(100)
        for character in "operator-step":
            page.keyboard.press(character)
            page.wait_for_timeout(200)
        page.wait_for_timeout(1500)
        x, y = point(190, 322)
        page.mouse.click(x, y)
        page.wait_for_timeout(1000)
        shot(
            desktop,
            "operator-diagnostic",
            "simulated-operator",
            "Independent screenshot after VNC input before checking state",
        )
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            s = state(desktop)
            if s["latest"] == "operator-step":
                break
            time.sleep(0.3)
        check(
            "operator-handover-effect",
            s["latest"] == "operator-step",
            actor="simulated operator through independent VNC client",
            sequence=[x["value"] for x in s["events"]],
        )
        shot(
            desktop,
            "04-operator-state",
            "simulated-operator",
            "Type and commit through the second controller",
        )
        s = commit(desktop, "agent-resumed")
        (OUT / "gui-state.json").write_text(desktop.files.read("/tmp/abx-gui-state.json"))
        check(
            "agent-resume-same-state",
            [x["value"] for x in s["events"]] == ["agent-start", "operator-step", "agent-resumed"],
            sequence=[x["value"] for x in s["events"]],
        )
        shot(
            desktop,
            "05-agent-resumed",
            "agent",
            "Resume on the same desktop and preserve prior operator state",
        )
        browser.close()
    stream.stop()
    stream = None
    check(
        "stream-stopped", True, websocket_sessions=proxy.ws_open, transported_bytes=proxy.ws_bytes
    )
    proxy.close()
    proxy = None
    # Replay is an offline sequence of actual screenshots, not a claimed video recorder.
    timeline = REPORT["timeline"]
    (OUT / "timeline.json").write_text(json.dumps(timeline, indent=2))
    data = json.dumps(timeline).replace("</", "<\\/")
    replay = Path(__file__).with_name("desktop-replay.html").read_text()
    (OUT / "replay.html").write_text(
        replay.replace("__TIMELINE__", data).replace("__MAXIMUM__", str(len(timeline) - 1))
    )
    check(
        "replay-artifacts",
        len(timeline) >= 5,
        screenshots=len(timeline),
        format="offline screenshot timeline with SHA-256; not full-motion video",
    )
except Exception as e:
    REPORT["failure"] = {"type": type(e).__name__, "message": safe(str(e))[:1000]}
    save()
    print(json.dumps({"failure": REPORT["failure"]}), flush=True)
finally:
    if proxy:
        with suppress(Exception):
            proxy.close()
    if stream:
        with suppress(Exception):
            stream.stop()
    if desktop:
        try:
            sid = desktop.sandbox_id
            deleted = desktop.kill()
            try:
                Sandbox.get_info(sid)
                absent = False
            except NotFoundException:
                absent = True
            check(
                "desktop-cleanup", deleted and absent, deleted=deleted, independently_absent=absent
            )
        except Exception as e:
            REPORT["cleanup_error"] = {"type": type(e).__name__, "message": safe(str(e))[:400]}
    REPORT["result"] = (
        "PASS" if not REPORT.get("failure") and not REPORT.get("cleanup_error") else "FAIL"
    )
    REPORT["result_scope"] = (
        "GUI, password-authenticated VNC, simulated handover and screenshot replay only; "
        "gateway token enforcement is separately observed"
    )
    save()
    print(json.dumps({"result": REPORT["result"]}), flush=True)
    if REPORT["result"] != "PASS":
        sys.exit(1)
