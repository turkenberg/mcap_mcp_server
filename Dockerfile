FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src/ src/

RUN pip install --no-cache-dir ".[all]"

ENV MCAP_DATA_DIR=/data
ENV MCAP_TRANSPORT=sse

EXPOSE 8080

ENTRYPOINT ["mcap-mcp-server"]
