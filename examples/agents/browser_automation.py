"""Run real headless Chromium in a cloud sandbox / 云沙箱中的真实浏览器。

The default page is served by an owned HTTP server inside the sandbox, so this
example does not depend on a third-party website. Set BROWSER_URL to scrape your
own external site instead. Browser installation requires outbound network access.
默认访问沙箱内自建页面；可用 BROWSER_URL 指定外部站点。安装浏览器需要网络。
"""

import asyncio
import os

from agent_sandbox import ProviderSandbox as Sandbox

SCRAPER_SCRIPT = r"""import asyncio
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from playwright.async_api import async_playwright

PAGE = (b"<!doctype html><title>Sandbox browser example</title><h1>Browser works</h1>"
        b"<p>Rendered in Chromium.</p><a href='/details'>Details</a>")

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(PAGE)

    def log_message(self, *_args):
        pass

async def scrape():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    target = os.environ.get("BROWSER_URL") or f"http://127.0.0.1:{server.server_port}"
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            try:
                page = await browser.new_page(viewport={"width": 1280, "height": 720})
                response = await page.goto(target, wait_until="domcontentloaded", timeout=30000)
                if response is None or not response.ok:
                    status = response.status if response else None
                    raise RuntimeError(f"Page request failed: status={status}")
                title = await page.title()
                heading = await page.locator("h1").first.text_content(timeout=10000)
                links = await page.locator("a").evaluate_all(
                    "nodes => nodes.map(node => ({text: node.textContent, "
                    "href: node.getAttribute('href')}))"
                )
                if not os.environ.get("BROWSER_URL"):
                    assert title == "Sandbox browser example" and heading == "Browser works"
                    assert links == [{"text": "Details", "href": "/details"}]
                await page.screenshot(path="/tmp/screenshot.png", full_page=True)
                html = await page.content()
                Path("/tmp/page.html").write_text(html, encoding="utf-8")
                print(json.dumps({"title": title, "heading": heading, "links": links}))
            finally:
                await browser.close()
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)

asyncio.run(scrape())
"""


async def main() -> None:
    envs = {"BROWSER_URL": os.environ["BROWSER_URL"]} if os.environ.get("BROWSER_URL") else {}
    async with await Sandbox.create(
        template="base",
        timeout=900,
        envs=envs,
        sandbox_api_key=os.environ.get("ABX_SANDBOX_API_KEY", ""),
    ) as sandbox:
        for command, timeout in [
            ("pip install playwright --quiet", 120),
            ("python -m playwright install --with-deps --only-shell chromium", 300),
        ]:
            print(f"Installing browser dependency: {command}", flush=True)
            result = await sandbox.commands.run(command, timeout=timeout)
            if not result.success:
                raise RuntimeError(f"Browser installation failed: {result.stderr}")
        print("Running Chromium against the selected HTTP page", flush=True)
        await sandbox.files.write("/tmp/scraper.py", SCRAPER_SCRIPT)
        result = await sandbox.commands.run("python /tmp/scraper.py", timeout=60)
        if not result.success:
            raise RuntimeError(f"Browser execution failed: {result.stderr}")
        print(result.stdout)
        png = await sandbox.files.read_bytes("/tmp/screenshot.png")
        assert png.startswith(b"\x89PNG\r\n\x1a\n") and len(png) > 1000
        html = await sandbox.files.read("/tmp/page.html")
        if not envs:
            assert "Browser works" in html and "Rendered in Chromium." in html
        print(f"Screenshot: {len(png)} bytes; HTML: {len(html)} characters")
    print("Sandbox destroyed")


if __name__ == "__main__":
    asyncio.run(main())
