"""Import-only migration example / 仅替换导入的迁移示例.

Configure E2B_API_KEY, E2B_API_URL, E2B_DOMAIN for Alibaba Express.
配置阿里云极速版连接参数后直接执行。
"""

from agent_sandbox.code_interpreter import Sandbox

with Sandbox.create(template="code-interpreter-v1", timeout=300) as sandbox:
    sandbox.files.write("/tmp/migration.txt", "hello")
    output = sandbox.commands.run("cat /tmp/migration.txt")
    assert output.exit_code == 0 and output.stdout == "hello"
    assert sandbox.files.read("/tmp/migration.txt") == "hello"
    print(output.stdout)
    initialized = sandbox.run_code("value = 41")
    assert initialized.error is None
    result = sandbox.run_code("value + 1")
    assert result.error is None and result.text.strip() == "42"
    print(result.text)
