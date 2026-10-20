## ⚙️ Complete Setup Guide

Follow these steps to set up Expensa in your local development environment.

### 1. Clone the Repository

```bash
git clone https://github.com/yasindugunasekara/expense-tracker-bot.git
cd expense-tracker-bot
```

### 2. Create a Python Virtual Environment

**Windows (PowerShell):**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**Linux / macOS:**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Dependencies

If the repository contains `requirements.txt`, run:

```bash
pip install -r requirements.txt
```

Install any additional dependencies specified by the project.

### 4. Configure Environment Variables

Create a `.env` file in the project root and configure the credentials required for the integrations you want to use.

```dotenv
SUPABASE_URL=your_supabase_url
SUPABASE_KEY=your_supabase_key
TELEGRAM_BOT_TOKEN=your_telegram_bot_token
TELEGRAM_ALLOWED_USER_ID=your_telegram_user_id
API_BASE_URL=http://127.0.0.1:8000
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=your_configured_gemini_model
```

Replace the example values with your actual configuration. Gmail API OAuth credentials may also be required for email importing.

**Security:** Never commit `.env`, `token.json`, OAuth secrets, or API keys to GitHub.

### 5. Configure Supabase

1. Create a project in [Supabase](https://supabase.com/).
2. Configure the project URL and backend API key in your environment.
3. Create the database tables required by the application, including `expenses` and `expense_events`.
4. Apply any additional schema or automation-task setup required by the current application code.

### 6. Configure Telegram

1. Create a bot using [BotFather](https://t.me/BotFather).
2. Add the bot token to your `.env` file.
3. Configure `TELEGRAM_ALLOWED_USER_ID` to restrict access to your intended Telegram account.
4. Start the application using the project's configured startup command and test a manual expense entry.

### 7. Configure Gmail and Receipt Processing

**Gmail integration**

1. Enable the Gmail API in your Google Cloud project.
2. Configure OAuth credentials for the application.
3. Complete the authorization process and store generated token files securely.
4. Test fetching messages before enabling transaction imports.

**Gemini receipt processing**

1. Obtain a Gemini API key.
2. Configure `GEMINI_API_KEY` and `GEMINI_MODEL`.
3. Test receipt extraction with a sample receipt image.

Only enable integrations for which you have completed the required configuration.

### 8. Start the FastAPI Backend

Use the entry point configured in the repository. If the application exposes `app.main:app`, a typical development command is:

```bash
uvicorn app.main:app --reload
```

Open the API documentation at:

```text
http://127.0.0.1:8000/docs
```

Verify that the backend and database connection are working before proceeding.

### 9. Connect Claude Through MCP

1. Install Claude Desktop or use a compatible MCP client.
2. Configure the MCP server using the Python environment and entry point from your project.
3. Set the required environment variables and API URL.
4. Restart the MCP client and verify that the expense tools are available.
5. Test an expense summary and a search query.

For a local MCP setup, the configuration may resemble the following. Update the paths to match your machine and verify that the server supports the configured transport.

```json
{
  "mcpServers": {
    "expense-tracker": {
      "command": "D:\\path\\to\\expense-tracker\\.venv\\Scripts\\python.exe",
      "args": [
        "D:\\path\\to\\expense-tracker\\app\\mcp_server.py"
      ],
      "env": {
        "EXPENSE_API_URL": "http://127.0.0.1:8000"
      }
    }
  }
}
```

Replace the example paths with your actual project paths. If you use the Azure deployment, follow the deployment's configured MCP connection method instead of assuming the local configuration will work remotely.

### 10. Run with Docker (Optional)

If the repository includes a Dockerfile and Docker Compose configuration:

```bash
docker compose up -d --build
docker compose ps
```

Check the container health and application logs:

```bash
docker compose logs -f
```

Review exposed ports and authentication settings before deploying to a public server.

### 11. Verify the Installation

- [ ] FastAPI starts successfully.
- [ ] Supabase connection works.
- [ ] Telegram bot accepts an authorized test message.
- [ ] Manual expense entries are stored correctly.
- [ ] Receipt processing works when configured.
- [ ] Gmail transaction fetching works when configured.
- [ ] Claude can access the MCP tools.
- [ ] Scheduled tasks execute and record their status.
- [ ] Secrets and token files are excluded from Git.

> **Note:** Commands and configuration examples are templates. Confirm the actual dependencies, startup scripts, database schema, and MCP transport in the repository before using them.
