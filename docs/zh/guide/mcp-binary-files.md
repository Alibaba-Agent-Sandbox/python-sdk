# 通过 Python MCP 传输二进制文件

Python MCP 的 STDIO 与 Streamable HTTP 共用 `upload_file` 和 `download_file`。
CLI 的独立 MCP 实现不随此变更。工具只操作选中沙箱的文件，不打开 MCP 主机路径；
文本继续使用 `read_file` / `write_file`。

**本源码版本的资源归属：** 显式指定外部 `sandbox_id` 时借用连接。会话关闭或 HTTP
session delete 只关闭该客户端连接，不销毁外部沙箱。仅由同一 MCP manager 创建的沙箱
会自动删除；明确保留的后台任务继续遵循独立保留规则。显式、已授权的 `kill_sandbox`
仍会删除选中的沙箱。此修正晚于公开的 0.4.0a6；包含修正的新版本发布前，须使用已验证
的修正源码或构建产物。

上传使用标准 Base64，覆盖远端路径：

```json
{"name":"upload_file","arguments":{"path":"/tmp/artifact.bin","content_base64":"AP8="}}
```

示例写入 `00 ff` 两个字节，返回 `success`、`bytes_written`、`sha256`。
下载调用如下，返回 `content_base64`、`bytes_read`、`sha256`：

```json
{"name":"download_file","arguments":{"path":"/tmp/artifact.bin"}}
```

由 MCP 客户端解码并核对长度/摘要，再保存到客户端自己选择的路径。
工具不返回含凭据的下载 URL，也不接受主机本地路径。文件内容会有意交给已授权调用者，
不承诺过滤文件中的秘密。

可选 `sandbox_id`；省略时使用默认沙箱，没有默认时按现有文件工具规则创建。
TTL 续期与会话清理规则保持一致；文件传输不会保留断连沙箱，也不改变
[后台任务资源归属](mcp-background-tasks.md)。

## 限额与错误

- 解码后最多 **1,048,576 字节（1 MiB）**，支持空文件、NUL 与非 UTF8。
  编码输入最多 1,398,104 字符，先检查长度，再严格解码 Base64。
  未知参数、非法编码或路径在解析沙箱和写文件之前拒绝。
- 远端绝对路径最多 4096 UTF-8 字节，不含 NUL 或父目录跳转；仍遵守沙箱已有权限。
- 下载按实际流式响应计数，不依赖 Stat 或 Content-Length；有界路径请求
  `Accept-Encoding: identity`，非 identity 编码在读取/解压前拒绝；原有无上限读取仍兼容 gzip。
  超限、出错、取消时关闭响应，
  不返回部分成功。工具读写等待上限 120 秒；超时的上传可能已到达沙箱，重试前应检查
  远端文件。不保证原子写入或断点续传。
- 最大文件的 JSON 请求/响应可放入 Python STDIO 的 8 MiB 行限额，真实本地 STDIO
  进程与 HTTP 会话均有最大容量回归。HTTP 未新增全局 body 限额；反向代理/客户端需允许
  Base64 加 JSON 开销（约 1.4 MiB）。更大文件、分块和断点续传不属于本工具契约。
- 失败返回 MCP `isError: true`、固定消息 `error` 与 `error_category`，分类为
  `invalid_input`、`size_limit`、`not_found`、`permission_denied`、`sandbox_not_found`、
  `unsupported`、`timeout` 或 `file_transfer`。错误消息和二进制工具日志不回显原始上游异常、
  凭据和文件内容；失败不表示已接受的远端操作被取消。

## SDK 可选下载限额

已有无上限默认行为保持兼容；显式限额用法：

```python
from agent_sandbox.models import FileSizeLimitError

try:
    data = await sandbox.files.read_bytes("/tmp/artifact.bin", max_bytes=1024 * 1024)
except FileSizeLimitError:
    pass  # 响应已关闭；改用更小文件或另一个明确限额。
```

`max_bytes` 为非负整数或 `None`。超限抛出 `FileSizeLimitError`（`E4003`，继承
`FileOperationError`，带 `limit`）。复用现有 envd `GET /files`，不编造 Range 端点，
不依赖 stat/read 间的大小判断；并发修改时不保证文件快照。

参考 [MCP 集成](mcp-integration.md) 与 [English](../../en/guide/mcp-binary-files.md)。

原生 Express 的 create/connect 路径支持该有界下载。Node provider adapter 在
流式契约落实前明确拒绝有界读取，不会退回无限读取；不声称其他 provider 已真实验收。
