# Azure VPS 24/7 Docker Deployment Guide

This guide walks you through deploying your **Expense Tracker Bot, API, Scheduler, and FastMCP Server** on a low-cost Azure Virtual Machine (e.g., `Standard_B1s` with 1 vCPU and 1 GB RAM) to run 24/7.

---

## 🏗️ Architecture Overview

To run reliably on a budget 1 GB VPS without running out of memory (OOM), we use an **All-in-One Multi-Process Supervisor** container:

```
┌─────────────────────────────────────────────────────────────┐
│                 Docker Container (expense-tracker)           │
│                                                             │
│   ┌─────────────────────────────────────────────────────┐   │
│   │               supervisord (Process Manager)         │   │
│   └──────┬─────────────────┬───────────────────┬────────┘   │
│          │                 │                   │            │
│          ▼                 ▼                   ▼            │
│     FastAPI App       Telegram Bot         Scheduler        │
│    (Port: 8000)       (Long-polling)    (Reports & Sync)    │
│                                                             │
│                      Optional: FastMCP                      │
│            (SSH stdio bridge OR SSE Port 8001)              │
└─────────────────────────────────────────────────────────────┘
```
- **Memory footprint**: ~180MB total (leaves >800MB free on a 1GB VPS!).
- **Auto-restart**: Automatically recovers after crashes or VM reboots (`restart: unless-stopped`).
- **Persistent storage**: Google OAuth tokens (`token.json`) survive container restarts and updates.

---

## 📋 Step 1: Provision Low-Cost Azure VPS

1. Log in to [Azure Portal](https://portal.azure.com).
2. Search for **Virtual Machines** $\rightarrow$ **Create** $\rightarrow$ **Azure Virtual Machine**.
3. Configure the VM:
   - **OS**: Ubuntu Server 24.04 LTS (or 22.04 LTS) - x64 Gen2.
   - **Size**: **Standard_B1s** (1 vCPU, 1 GiB RAM — ~$7-10/month) or **Standard_B2s** (2 vCPU, 4 GiB RAM).
   - **Authentication**: SSH public key (recommended) or password.
4. **Networking (Inbound Ports)**:
   - Allow **SSH (Port 22)** (Required).
   - Allow **Port 8000** (Optional: only if you want public access to the FastAPI docs/API).
   - Allow **Port 8001** (Optional: only if using MCP over HTTP/SSE instead of SSH).

---

## 📋 Step 2: Transfer Code to Your Azure VPS

From your local terminal, transfer your project to the Azure VM (or clone your GitHub repository):

```bash
# Option A: Git Clone on the VPS (Recommended)
ssh azureuser@<YOUR_VPS_IP>
git clone https://github.com/<your-username>/expense-tracker.git
cd expense-tracker
```

Or using `scp` from your local machine:
```bash
# Option B: Copy files from your local machine
scp -r "d:/works/expense tracker" azureuser@<YOUR_VPS_IP>:~/expense-tracker
```

---

## 📋 Step 3: Configure Environment & Credentials

On your Azure VPS inside the `expense-tracker` directory:

1. **Create `.env` file**:
   ```bash
   cp .env.example .env
   nano .env
   ```
   Fill in your actual keys:
   - `SUPABASE_URL` and `SUPABASE_KEY`
   - `TELEGRAM_BOT_TOKEN` and `TELEGRAM_ALLOWED_USER_ID`
   - `GEMINI_API_KEY`
   - `GMAIL_REPORT_TO`
   - Keep `API_BASE_URL=http://127.0.0.1:8000`

2. **Copy Google API credentials**:
   Ensure `credentials.json` and `token.json` (if already generated) are in the project root:
   ```bash
   # Make sure token.json exists as a file so Docker doesn't mount it as a directory
   touch token.json
   chmod 600 token.json
   ```

---

## 📋 Step 4: One-Click Automated Deployment

We provide an automated script that configures 2GB swap memory (critical for 1GB VPS), installs Docker if needed, and starts the container:

```bash
chmod +x deploy.sh
./deploy.sh
```

Or run directly with Docker Compose:
```bash
docker compose up -d --build
```

---

## 📋 Step 5: Connecting to FastMCP

You can connect your local AI assistants (Claude Desktop, Cursor, Antigravity, Cline) to the MCP server running on your Azure VPS.

### Method A: SSH Bridge (Recommended — Maximum Security, Zero Open Ports)
No open firewall ports required! Your local machine connects over encrypted SSH and runs MCP via `docker exec`:

Add this to your local **`claude_desktop_config.json`** or Antigravity / Cursor MCP config:

```json
{
  "mcpServers": {
    "expense-tracker": {
      "command": "ssh",
      "args": [
        "-T",
        "azureuser@<YOUR_AZURE_VPS_IP>",
        "docker exec -i expense-tracker python -m app.mcp_server"
      ]
    }
  }
}
```

### Method B: Remote HTTP / SSE Endpoint
If you prefer connecting via HTTP/SSE:
1. In `.env` on your VPS, set:
   ```env
   START_MCP=true
   MCP_TRANSPORT=sse
   MCP_PORT=8001
   ```
2. Restart the container:
   ```bash
   docker compose up -d
   ```
3. Open inbound port **8001** in your Azure Network Security Group (NSG).
4. In your local AI client config:
   ```json
   {
     "mcpServers": {
       "expense-tracker": {
         "url": "http://<YOUR_AZURE_VPS_IP>:8001/sse"
       }
     }
   }
   ```

---

## 🛠️ Management & Monitoring Commands

| Action | Command |
| :--- | :--- |
| **Check container status** | `docker compose ps` |
| **View live logs** | `docker compose logs -f` |
| **View logs for Bot only** | `docker exec -it expense-tracker supervisorctl tail -f telegram_bot` |
| **View logs for API only** | `docker exec -it expense-tracker supervisorctl tail -f api` |
| **View logs for Scheduler** | `docker exec -it expense-tracker supervisorctl tail -f scheduler` |
| **Restart all services** | `docker compose restart` |
| **Restart specific service** | `docker exec -it expense-tracker supervisorctl restart telegram_bot` |
| **Check RAM & CPU usage** | `docker stats` |
| **Stop container** | `docker compose down` |

---

## 💡 Low-Cost Azure VPS Optimization Tips

1. **Swap Memory (Enabled by `deploy.sh`)**:
   Azure B1s instances have 1 GB RAM. A 2GB swap file prevents Linux from abruptly killing your Python processes during spike loads (such as image receipt processing with Gemini).

2. **Single-Worker Uvicorn**:
   We set `--workers 1` in `supervisord.conf`. On a 1 vCPU machine, 1 asynchronous worker handles thousands of requests while using only ~45MB of RAM.

3. **Persistent Token File**:
   Because `token.json` is bind-mounted with read-write (`rw`) permissions, automatic Google OAuth refresh tokens persist seamlessly across image rebuilds and container restarts.
