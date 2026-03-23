FROM python:3.12-slim

WORKDIR /app

# ─── Install Terraform + gcloud CLI ──────────────────────────────────────────
RUN apt-get update -y && apt-get install -y --no-install-recommends \
        curl gnupg unzip apt-transport-https ca-certificates && \
    # Terraform
    curl -fsSL https://releases.hashicorp.com/terraform/1.9.8/terraform_1.9.8_linux_amd64.zip \
        -o /tmp/terraform.zip && \
    unzip /tmp/terraform.zip -d /usr/local/bin/ && rm /tmp/terraform.zip && \
    # gcloud CLI
    echo "deb [signed-by=/usr/share/keyrings/cloud.google.gpg] https://packages.cloud.google.com/apt cloud-sdk main" \
        > /etc/apt/sources.list.d/google-cloud-sdk.list && \
    curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg \
        | gpg --dearmor -o /usr/share/keyrings/cloud.google.gpg && \
    apt-get update -y && apt-get install -y --no-install-recommends google-cloud-cli && \
    # Cleanup
    apt-get clean && rm -rf /var/lib/apt/lists/*

# ─── Install Python deps ─────────────────────────────────────────────────────
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml .
COPY src/ src/

RUN uv pip install --system -e .

EXPOSE 8000

CMD ["python", "-m", "core_mcp"]
