"""Import-only migration example / 仅替换导入的迁移示例.

Configure E2B_API_KEY, E2B_API_URL, E2B_DOMAIN for Alibaba Express.
配置阿里云极速版连接参数后直接执行。
"""
from agent_sandbox.code_interpreter import Sandbox

with Sandbox.create(template="code-interpreter-v1", timeout=300) as sandbox:
    sandbox.files.write("/tmp/migration.txt", "hello")
    print(sandbox.commands.run("cat /tmp/migration.txt").stdout)
    sandbox.run_code("value = 41")
    print(sandbox.run_code("value + 1").text)
