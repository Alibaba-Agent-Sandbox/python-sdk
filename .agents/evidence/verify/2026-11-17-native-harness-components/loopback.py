# Real installed native binaries; placeholder credentials are sent only to loopback.
import argparse
import json
import os
import shutil
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from agent_sandbox.server.agents.adapters import AdapterRegistry, TurnContext
from agent_sandbox.server.agents.config import AgentSpec, ProviderSpec

arguments = argparse.ArgumentParser(
    description=(
        "Real native CLI transport and resume against a deterministic local model; "
        "not real-model acceptance."
    )
)
arguments.add_argument("--native-bin", required=True)
arguments.add_argument("--node-bin", required=True)
options = arguments.parse_args()
requests = []


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        body = json.dumps(
            {
                "object": "list",
                "data": [{"id": "test-model", "object": "model", "owned_by": "test"}],
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        requests.append(body)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        if "messages" in self.path and "chat/completions" not in self.path:
            events = [
                (
                    "message_start",
                    {
                        "type": "message_start",
                        "message": {
                            "id": "msg_probe",
                            "type": "message",
                            "role": "assistant",
                            "model": "test-model",
                            "content": [],
                            "stop_reason": None,
                            "usage": {"input_tokens": 5, "output_tokens": 0},
                        },
                    },
                ),
                (
                    "content_block_start",
                    {
                        "type": "content_block_start",
                        "index": 0,
                        "content_block": {"type": "text", "text": ""},
                    },
                ),
                (
                    "content_block_delta",
                    {
                        "type": "content_block_delta",
                        "index": 0,
                        "delta": {"type": "text_delta", "text": "Native probe answer"},
                    },
                ),
                ("content_block_stop", {"type": "content_block_stop", "index": 0}),
                (
                    "message_delta",
                    {
                        "type": "message_delta",
                        "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                        "usage": {"output_tokens": 3},
                    },
                ),
                ("message_stop", {"type": "message_stop"}),
            ]
            self.wfile.write(
                "".join(
                    "event: " + kind + "\ndata: " + json.dumps(event) + "\n\n"
                    for kind, event in events
                ).encode()
            )
        else:
            for delta, finish in [
                ({"role": "assistant", "content": "Native probe answer"}, None),
                ({}, "stop"),
            ]:
                self.wfile.write(
                    (
                        "data: "
                        + json.dumps(
                            {
                                "id": "chat_probe",
                                "object": "chat.completion.chunk",
                                "created": 1,
                                "model": "test-model",
                                "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
                            }
                        )
                        + "\n\n"
                    ).encode()
                )
            self.wfile.write(b"data: [DONE]\n\n")


server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
for name in ["opencode", "deepseek-harness"]:
    adapter = AdapterRegistry().get(name)
    root = Path(tempfile.mkdtemp(prefix="native-harness-loopback-"))
    (root / "turn").mkdir()
    spec = AgentSpec(
        name="probe",
        runtime=name,
        model="test-model",
        provider=ProviderSpec(
            base_url="http://127.0.0.1:" + str(server.server_port) + "/v1",
            api_key="placeholder-loopback-only",
        ),
        permissions="full_access",
    )
    sid = None
    for turn in range(2):
        ctx = TurnContext(
            spec=spec,
            prompt="Remember native-resume-marker" if turn == 0 else "Recall the previous marker",
            workdir=str(root),
            turn_dir=str(root / "turn"),
            native_session_id=sid,
        )
        inv = adapter.build_invocation(ctx)
        for f in inv.files:
            Path(f.path).write_bytes(f.content)
        env = {
            "PATH": options.node_bin
            + os.pathsep
            + options.native_bin
            + os.pathsep
            + "/usr/local/bin:/usr/bin:/bin",
            "HOME": str(root / "home"),
            "CI": "1",
            "LANG": "C.UTF-8",
            **inv.env,
        }
        try:
            r = subprocess.run(
                inv.argv, input=inv.stdin, cwd=root, env=env, capture_output=True, timeout=25
            )
        except subprocess.TimeoutExpired:
            print(
                json.dumps({"adapter": name, "turn": turn, "timeout": True, "exit_confirmed": True})
            )
            break
        parser = adapter.new_parser(ctx)
        events = [e for line in r.stdout.decode().splitlines() for e in parser.feed(line)]
        events += parser.finish(r.returncode)
        previous = sid
        sid = next((e.text for e in events if e.kind == "session"), sid)
        print(
            json.dumps(
                {
                    "adapter": name,
                    "turn": turn,
                    "exit": r.returncode,
                    "native_session_present": bool(sid),
                    "same_native_session": previous is None or sid == previous,
                    "event_kinds": [e.kind for e in events],
                    "terminal_ok": any(e.kind == "result" and e.data.get("ok") for e in events),
                }
            )
        )
        if r.returncode or not sid:
            break
    print(
        json.dumps(
            {
                "adapter": name,
                "request_count": len(requests),
                "resume_history_contains_marker": any(
                    "Recall the previous marker" in json.dumps(r)
                    and "native-resume-marker" in json.dumps(r)
                    for r in requests
                ),
            }
        )
    )
    requests.clear()
    shutil.rmtree(root)
server.shutdown()
server.server_close()
