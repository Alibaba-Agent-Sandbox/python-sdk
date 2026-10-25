FROM ubuntu:22.04
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y python3 python3-pip && rm -rf /var/lib/apt/lists/*

# Install the published runtime; no local wheel or source fallback is required.
RUN python3 -m pip install --index-url https://pypi.org/simple --no-cache-dir "agent-sandbox-server==0.4.0a6"

WORKDIR /app
COPY commands.py .
EXPOSE 9000
CMD ["python3", "commands.py"]
