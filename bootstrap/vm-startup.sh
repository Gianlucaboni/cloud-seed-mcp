#!/usr/bin/env bash
###############################################################################
# vm-startup.sh — Cloud Seed MCP VM Startup Script
#
# Runs at first boot on a GCP VM. Installs Docker, clones the repo,
# and starts the seed via docker compose.
###############################################################################

set -euo pipefail
exec > /var/log/cloud-seed-startup.log 2>&1

echo "=== Cloud Seed MCP startup — $(date) ==="

# ─── Install Docker ──────────────────────────────────────────────────────────
if ! command -v docker &> /dev/null; then
    echo "Installing Docker..."
    apt-get update -y
    apt-get install -y ca-certificates curl gnupg
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian $(. /etc/os-release && echo "$VERSION_CODENAME") stable" > /etc/apt/sources.list.d/docker.list
    apt-get update -y
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
    systemctl enable docker
    systemctl start docker
    echo "Docker installed: $(docker --version)"
else
    echo "Docker already installed: $(docker --version)"
fi

# ─── Clone repo ──────────────────────────────────────────────────────────────
REPO_DIR="/opt/cloud-seed-mcp"

if [ ! -d "$REPO_DIR" ]; then
    echo "Cloning repository..."
    apt-get install -y git
    git clone https://github.com/Gianlucaboni/cloud-seed-mcp.git "$REPO_DIR"
else
    echo "Repository already exists, pulling latest..."
    cd "$REPO_DIR" && git pull origin main
fi

cd "$REPO_DIR"

# ─── Authenticate gcloud for Docker containers ──────────────────────────────
echo "Setting up GCP credentials for containers..."
# On a GCP VM, the metadata server provides default credentials.
# We create an ADC file that containers can use.
if [ ! -f /root/.config/gcloud/application_default_credentials.json ]; then
    mkdir -p /root/.config/gcloud
    # Use the VM's service account to generate ADC
    curl -s -H "Metadata-Flavor: Google" \
        "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token" \
        > /dev/null 2>&1 && {
        echo "VM service account detected — gcloud will use metadata server."
        # gcloud inside containers can use the mounted config + metadata server
    }
fi

# ─── Create .env with GCP project context ────────────────────────────────────
echo "Creating .env with auto-detected GCP context..."
SEED_PROJECT_ID=$(curl -s -H "Metadata-Flavor: Google" \
    "http://metadata.google.internal/computeMetadata/v1/project/project-id" 2>/dev/null || echo "")
ORG_ID=$(gcloud projects describe "$SEED_PROJECT_ID" \
    --format="value(parent.id)" 2>/dev/null || echo "")

cp .env.example .env

# Inject actual values into .env
if [ -n "$SEED_PROJECT_ID" ]; then
    sed -i "s|^CORE_MCP_SEED_PROJECT_ID=.*|CORE_MCP_SEED_PROJECT_ID=${SEED_PROJECT_ID}|" .env
    echo "Detected seed project: $SEED_PROJECT_ID"
fi
if [ -n "$ORG_ID" ]; then
    sed -i "s|^CORE_MCP_ORG_ID=.*|CORE_MCP_ORG_ID=${ORG_ID}|" .env
    echo "Detected org ID: $ORG_ID"
fi

# ─── Export HOME for docker-compose volume mount ─────────────────────────────
export HOME=/root

# ─── Start seed ──────────────────────────────────────────────────────────────
echo "Starting Cloud Seed MCP..."
docker compose up -d --build

echo "=== Cloud Seed MCP startup complete — $(date) ==="
echo "Waiting for health checks..."
sleep 30
docker compose ps
