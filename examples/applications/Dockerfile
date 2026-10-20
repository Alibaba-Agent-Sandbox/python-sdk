# Build from the python-sdk checkout root. Supply a reviewed/pinned Python base.
ARG PYTHON_IMAGE
FROM ${PYTHON_IMAGE}
WORKDIR /opt/agent-sandbox
COPY server-sdk ./server-sdk
COPY client-sdk ./client-sdk
COPY examples/applications/application_factory.py ./application_factory.py
RUN python -m pip install --no-cache-dir ./server-sdk './client-sdk[applications-fc]'
ENV ABX_APP_FACTORY=application_factory:create_application
ENV ABX_APP_BIND=0.0.0.0 ABX_APP_PORT=9000
EXPOSE 9000
CMD ["python", "-m", "agent_sandbox.applications", "gateway"]
