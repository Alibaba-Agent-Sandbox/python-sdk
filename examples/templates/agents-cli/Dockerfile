FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV LANG=C.UTF-8
ENV ABX_SERVER_ENABLED_GROUPS=agents

# The Agents API lives in agent-sandbox-server. This image does not install
# Node, Codex, or Qwen Code. Add one of these lines to your own Dockerfile
# only for the CLI you actually call:
#   RUN apt-get update && apt-get install -y --no-install-recommends nodejs npm ca-certificates \
#       && npm install -g @openai/codex && rm -rf /var/lib/apt/lists/*
#   RUN apt-get update && apt-get install -y --no-install-recommends nodejs npm ca-certificates \
#       && npm install -g @qwen-code/qwen-code && rm -rf /var/lib/apt/lists/*

# Install the published runtime; no local wheel or source fallback is required.
RUN python3 -m pip install --index-url https://pypi.org/simple --no-cache-dir "agent-sandbox-server==0.4.0a6"

WORKDIR /app
COPY commands.py .
EXPOSE 9000
CMD ["python3", "commands.py"]
