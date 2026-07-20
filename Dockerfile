FROM python:3.13-slim

LABEL org.opencontainers.image.title="freeact"
LABEL org.opencontainers.image.description="Undetectable browser automation CLI for AI agents"
LABEL org.opencontainers.image.version="0.4.0"
LABEL org.opencontainers.image.source="https://github.com/xuviga/freeact"

RUN pip install --no-cache-dir freeact-cli==0.4.0 \
    && playwright install chromium \
    && playwright install-deps chromium

RUN mkdir -p /root/.freeact

ENV FREACT_HOME=/root/.freeact

ENTRYPOINT ["freeact"]
CMD ["--help"]
