# Accessibility

**English** | [中文](#中文)

This repository is a Python library and an in-sandbox HTTP service. It has no graphical application. Text, JSON, and documented exit behavior are the interface.

The terminal interface is `ebx`, maintained in [easy-sandbox](https://github.com/Easy-Sandbox/easy-sandbox). Its commitment, supported terminals, and how to turn color and animation off are in that repository's [ACCESSIBILITY.md](https://github.com/Easy-Sandbox/easy-sandbox/blob/main/ACCESSIBILITY.md).

## Commitment

- Public APIs return structured data (objects and JSON), not an arrangement that only makes sense on a screen.
- Error messages name the failure in text. A secret value is not copied into the message.
- HTTP routes that a template serves identify themselves with status codes and JSON bodies.
- A report of a barrier is a product bug. We will answer it in the issue tracker.

## Supported environments

| Environment | What we support |
|---|---|
| Python | 3.10 or newer |
| Operating systems | Linux, macOS, and Windows, for the client library |
| In-sandbox server | Linux, the image you build from a template, listening on port 9000 by default |
| Clients | Any HTTP client that can send and receive UTF-8 JSON, including a screen reader's browse mode when the caller renders that JSON as text |
| Terminal use of the library | The same terminals and screen readers as the CLI, when you print SDK results as text |

`GET /health` and other JSON routes stay text. File upload and download carry bytes and say so in the API; they are not a text alternative for the file's own contents.

## Known limitations

- Streaming responses (server-sent events and WebSockets) arrive as a sequence of frames. A screen reader will not announce them unless the program you wrote reads the frames and prints text.
- The server does not render HTML and does not set a page language, landmarks, or focus order.
- Examples under `examples/` are scripts. Their printed output is plain text. They are not an accessible interactive tutorial.
- Sandbox images you build can run third-party programs. Those programs are outside this statement.

## How to report a barrier

Open an issue:

https://github.com/Easy-Sandbox/python-sdk/issues/new/choose

Include the call or HTTP request with secrets removed, the Python version, the operating system, and what you expected to read versus what you received. If the barrier is in `ebx` rather than the library, file it on [easy-sandbox](https://github.com/Easy-Sandbox/easy-sandbox/issues/new/choose).

## 中文

这个仓库是 Python 库和沙箱内的 HTTP 服务，没有图形界面。接口是文本、JSON，以及文档里写明的退出行为。

终端程序是 `ebx`，在 [easy-sandbox](https://github.com/Easy-Sandbox/easy-sandbox) 仓库。终端、读屏软件，以及如何关闭颜色和动画，写在该仓库的 [ACCESSIBILITY.md](https://github.com/Easy-Sandbox/easy-sandbox/blob/main/ACCESSIBILITY.md)。

我们承诺：公开 API 返回结构化数据；错误信息用文字说明失败，且不把密钥抄进消息；模板对外的 HTTP 路由用状态码和 JSON 表明自己；无障碍障碍视为产品缺陷，并在议题里回复。

支持的环境：Python 3.10 及以上；客户端库支持 Linux、macOS、Windows；沙箱内服务运行在模板构建出的 Linux 镜像里，默认监听 9000 端口；任何能收发 UTF-8 JSON 的 HTTP 客户端都可以调用。

已知限制：

- 服务器发送事件和 WebSocket 是一帧一帧到达的。除非你的程序把帧打印成文字，读屏软件不会自动朗读。
- 服务不渲染 HTML，也不提供页面语言、地标或焦点顺序。
- `examples/` 下的示例是脚本，输出是纯文本，不是一套可交互的无障碍教程。
- 你构建的沙箱镜像里可以运行第三方程序，那些程序不在本说明的范围内。

报告障碍：打开 https://github.com/Easy-Sandbox/python-sdk/issues/new/choose 。写上调用或 HTTP 请求（去掉密钥）、Python 版本、操作系统，以及你期望读到的内容和实际收到的内容。如果问题出在 `ebx` 而不是这个库，请提到 [easy-sandbox](https://github.com/Easy-Sandbox/easy-sandbox/issues/new/choose)。
