#!/usr/bin/env bash
# =================================================================
# Automated 24/7 Deployment Script for Azure VPS (Ubuntu 22.04 / 24.04)
# =================================================================

set -e

echo "🚀 Starting Expense Tracker deployment..."

# 1. Configure 2GB Swap Memory (Crucial for low-cost 1GB RAM Azure B1s VMs to prevent OOM)
SWAP_TOTAL=$(free -m | awk '/^Swap:/ {print $2}')
if [ "$SWAP_TOTAL" -eq 0 ]; then
    echo "⚙️ Configuring 2GB Swap memory to optimize low-cost VPS stability..."
    sudo fallocate -l 2G /swapfile || sudo dd if=/dev/zero of=/swapfile bs=1M count=2048
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile
    if ! grep -q '/swapfile' /etc/fstab; then
        echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
    fi
    echo "✅ 2GB Swap configured successfully."
else
    echo "✅ Swap memory already present (${SWAP_TOTAL} MB)."
fi

# 2. Check and Install Docker & Docker Compose if missing
if ! command -v docker &> /dev/null; then
    echo "📦 Docker not detected. Installing Docker Engine..."
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    sudo usermod -aG docker $USER
    rm get-docker.sh
    echo "✅ Docker installed."
fi

# 3. Ensure persistent OAuth token file exists as a file (not directory)
if [ ! -f "token.json" ]; then
    echo "📄 Initializing placeholder token.json..."
    touch token.json
    chmod 600 token.json
fi

# 4. Check for .env file
if [ ! -f ".env" ]; then
    echo "⚠️ Warning: .env file not found!"
    if [ -f ".env.example" ]; then
        echo "📋 Creating .env from .env.example. Please edit .env with your credentials:"
        cp .env.example .env
        echo "👉 Run: nano .env (then rerun ./deploy.sh)"
        exit 1
    fi
fi

# 5. Build and launch the container in the background
echo "🐳 Building and starting Docker containers..."
docker compose up -d --build

echo ""
echo "================================================================="
echo "🎉 Expense Tracker is now running 24/7 on your Azure VPS!"
echo "================================================================="
echo "📊 Check status: docker compose ps"
echo "📜 View live logs: docker compose logs -f"
echo "🔄 Restart: docker compose restart"
echo "🛑 Stop: docker compose down"
echo ""
echo "🔌 MCP Access (from local machine):"
echo "   ssh -T $USER@$(curl -s ifconfig.me || echo '<YOUR_VPS_IP>') \"docker exec -i expense-tracker python -m app.mcp_server\""
echo "================================================================="
