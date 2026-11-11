# Backend image for AWS Lambda via Lambda Web Adapter (response streaming).
# uv pattern: https://docs.astral.sh/uv/guides/integration/docker/ (multi-stage, --no-editable)
# Adapter:    https://github.com/awslabs/aws-lambda-web-adapter (v1.1.0)
FROM public.ecr.aws/docker/library/python:3.12-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:0.11.14 /uv /bin/
ENV UV_PYTHON_DOWNLOADS=0 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-editable --no-dev
COPY pyproject.toml uv.lock ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-editable --no-dev

FROM public.ecr.aws/docker/library/python:3.12-slim
COPY --from=public.ecr.aws/awsguru/aws-lambda-adapter:1.1.0 /lambda-adapter /opt/extensions/lambda-adapter
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
EXPOSE 8080
CMD ["uvicorn", "labor_law_agent.api:app", "--host", "0.0.0.0", "--port", "8080"]
