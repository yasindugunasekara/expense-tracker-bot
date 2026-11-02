# Jenkins to Azure deployment

Push to GitHub `main` triggers local Jenkins polling every two minutes. Jenkins must be running and this PC must be online. The `expense-tracker` pipeline uses Python 3.12, creates a clean environment, installs pinned dependencies, runs `pip check` and pytest, publishes JUnit results, and archives the tested Git commit before deployment. Failed tests skip deployment.

## Installed configuration

- Jenkins: http://localhost:8080/job/expense-tracker/
- Python: `C:\ProgramData\Jenkins\tools\Python312\tools\python.exe` (Python Software Foundation NuGet runtime 3.12.10).
- Repository: https://github.com/yasindugunasekara/expense-tracker-bot.git, branch `main`, Jenkinsfile from SCM.
- Jenkins SSH credential: `expense-azure-ssh`, username `azureuser`.
- Azure root: `/home/azureuser/expense-tracker` on `172.197.160.37`.
- SSH host key is pinned in `ci/known_hosts`; verify any replacement through a trusted connection.

The pipeline supports `DEPLOY=false` for a test/package-only run. Pipeline credentials are used through Jenkins credential binding. The temporary SSH key ACL is restricted to the Jenkins service identity before invoking Windows OpenSSH. Production `.env`, OAuth client credentials and `gmail-state/` stay on Azure and are excluded from Git, build contexts and release archives.

## Releases and rollback

Azure builds image `expense-tracker:<commit>`, then replaces only the app container on the existing external Docker network. The MCP gateway remains attached. Deployment is serialized with `flock`; lower or repeated successful Jenkins build numbers are rejected. The current main revision is checked before upload. Do not reset the Jenkins build sequence without reconciling `.ci/build`.

Readiness requires healthy HTTP, database connectivity and RUNNING API, scheduler and Telegram supervisor processes. Any replacement or verification error restores the captured prior compose configuration and exact prior image. The previous image and compose path are retained under `.ci/previous-*`; do not prune them or their release directory before the next successful deployment. A successful deployment records `.ci/commit` and `.ci/build`.

Manual rollback on Azure (the release image must still exist):

```bash
cd /home/azureuser/expense-tracker
export DEPLOY_ROOT="$PWD"
export RELEASE_IMAGE="$(cat .ci/previous-image)"
docker compose --project-directory "$(cat .ci/previous-root)" -p expense-tracker -f "$(cat .ci/previous-compose)" -f .ci/rollback-image.yml up -d --no-deps --no-build expense-tracker
docker exec expense-tracker curl -fsS http://127.0.0.1:8000/health/db
```

## Gmail recovery

Run locally: `.venv\Scripts\python.exe -m app.gmail_auth`, consent to Gmail read and send, and securely transfer `gmail-state/token.json` into the Azure `gmail-state` directory with mode 600. Do not replace a mounted token file while using the old single-file mount; production CI uses a directory mount to support atomic token replacement.

Runtime authentication never opens a browser. Both importer and sender share a file lock and atomic refresh writes. A revoked refresh grant requires new consent. Google OAuth apps with External audience in Testing issue refresh grants that normally expire after seven days; check the project's publishing status and move to Production when appropriate. See [Google OAuth documentation](https://developers.google.com/identity/protocols/oauth2).

Receipt sync scans every Gmail page (`--max` is the page size), serializes callers, aborts if tracking cannot be read, and recovers partially tracked inserts through message markers. Existing expenses are retained. Scheduled task failures retry at 1, 2, 4 and 8 minute intervals, with at most five attempts in a reporting period. Task errors contain JSON attempt counts and a readable message. A successful send suppresses further sends that period. Delivery confirmation and database status updates are separate services, so a crash after Gmail accepts a message but before status persistence can still require manual reconciliation.

Weekly summary tasks remain controlled by Claude MCP and always report the most recently completed Monday–Sunday in Asia/Colombo. A Sunday delivery therefore reports the preceding completed week; choose Monday or later to receive the week that just ended. Totals use stored expense dates, paginated reads and decimal arithmetic. There are no required database migrations.

## Verification

Run `python -m pytest -q` and `python -m pip check` in the CI environment. CI tests substitute database and Gmail clients and do not send mail. `tests/test_deploy.sh` runs the deployment script with fake Docker commands in a temporary directory and verifies success, stale-build rejection and rollback without touching the real service. Real receipt imports and a single real summary email are rollout checks, separate from CI.
