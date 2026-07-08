FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN pip install --no-cache-dir .

# Usuario sin privilegios: el servidor solo habla stdio y HTTP saliente hacia Odoo
RUN useradd --create-home mcp
USER mcp

ENTRYPOINT ["odoo-mcp"]
