"""Generate and verify Python code with a real OpenAI-compatible model.

Requires ABX_SANDBOX_API_KEY and OPENAI_API_KEY. OPENAI_BASE_URL and OPENAI_MODEL
select another compatible service/model. This is a code-generation example;
Codex/Qwen CLI sessions are demonstrated by the hosted Agents API examples.
"""

import asyncio
import json
import os

from agent_sandbox import ProviderSandbox

CASES = [[38, 27, 43, 3, 9, 82, 10], [5, 1, 4, 2, 8], [], [1], [2, -1, 2, 0]]
TASK = r"""
import json, os
from pathlib import Path
from openai import OpenAI

response = OpenAI().chat.completions.create(
    model=os.environ["OPENAI_MODEL"],
    messages=[
        {"role": "system", "content": "Return executable Python only, without markdown."},
        {"role": "user", "content": (
            "Implement quicksort(values), returning an ascending sorted list. "
            "Preserve duplicates, empty lists and negative numbers. "
            "No IO or imports are needed.")},
    ],
    temperature=0,
    max_tokens=2000,
)
source = response.choices[0].message.content
if not source:
    raise RuntimeError("The model returned no code")
source = source.strip()
if source.startswith("```") and source.endswith("```"):
    source = "\n".join(source.splitlines()[1:-1])
compile(source, "generated_sort.py", "exec")
Path("/tmp/generated_sort.py").write_text(source)
scope = {}
exec(compile(source, "generated_sort.py", "exec"), scope)
cases = json.loads(os.environ["EXAMPLE_SORT_CASES"])
results = [scope["quicksort"](list(values)) for values in cases]
assert results == [sorted(values) for values in cases]
print(json.dumps(results))
"""


async def main() -> None:
    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError("Set OPENAI_API_KEY for a real model call; no simulation is performed")
    env = {
        name: os.environ[name]
        for name in ("OPENAI_API_KEY", "OPENAI_BASE_URL")
        if os.environ.get(name)
    }
    env["OPENAI_MODEL"] = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    env["EXAMPLE_SORT_CASES"] = json.dumps(CASES)
    async with await ProviderSandbox.create("base", timeout=300, envs=env) as sandbox:
        installed = await sandbox.commands.run("python3 -m pip install --quiet openai", timeout=120)
        if installed.exit_code != 0:
            raise RuntimeError("Could not install the model client in the sandbox")
        await sandbox.files.write("/tmp/model_task.py", TASK)
        result = await sandbox.commands.run("python3 /tmp/model_task.py", timeout=120)
        if result.exit_code != 0:
            raise RuntimeError("The model task failed; check model access and generated code")
        assert json.loads(result.stdout) == [sorted(values) for values in CASES]
        source = await sandbox.files.read("/tmp/generated_sort.py")
        compile(source, "generated_sort.py", "exec")
        print(
            "PASS: real model code; five sorting cases match independent sorted()"
        )
    print("Sandbox destroyed")


if __name__ == "__main__":
    asyncio.run(main())
