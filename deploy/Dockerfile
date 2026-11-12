# syntax=docker/dockerfile:1
FROM docker.io/library/node:22-bookworm-slim@sha256:e9f565d32859f0cbfb52125eafe8be39390f24dac302dc3cdf566e8ba3ab21ee AS frontend
WORKDIR /frontend
COPY dashboard/package.json dashboard/package-lock.json ./
RUN --mount=type=secret,id=proxy_ca \
    if [ -f /run/secrets/proxy_ca ]; then export NODE_EXTRA_CA_CERTS=/run/secrets/proxy_ca; fi; \
    npm ci --ignore-scripts --strict-ssl=true
COPY dashboard/ ./
RUN npm run build

FROM ghcr.io/astral-sh/uv:0.13.5@sha256:32a7bb39b496babbd997b0a39a4d66c126bdaf5661b302bf6f06abda8deca6ff AS uv
FROM docker.io/library/python:3.12-slim-bookworm@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df AS application
COPY --from=uv /uv /usr/local/bin/uv
RUN apt-get update && apt-get install --no-install-recommends -y libgomp1 ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --chown=10001:10001 . ./
RUN --mount=type=secret,id=proxy_ca --mount=type=cache,target=/root/.cache/uv \
    if [ -f /run/secrets/proxy_ca ]; then export SSL_CERT_FILE=/run/secrets/proxy_ca; fi; \
    uv sync --frozen --no-dev --extra ml --extra discovery --extra futures \
      --extra paper --extra dashboard --extra agent
COPY --from=frontend --chown=10001:10001 /frontend/dist ./dashboard/dist
RUN useradd --create-home --uid 10001 quantlab \
    && mkdir -p /app/data/dashboard /app/data/paper /app/data/execution /app/data/agent \
    && chown -R 10001:10001 /app/data /home/quantlab
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    QUANTLAB_WORKSPACE=/app
USER 10001:10001
ENTRYPOINT ["quantlab"]
CMD ["dashboard", "--host", "0.0.0.0", "--port", "8000"]
