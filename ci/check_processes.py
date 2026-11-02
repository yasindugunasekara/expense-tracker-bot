"""Deployment readiness: API, scheduler and Telegram must all be running."""
import subprocess
result = subprocess.run(["supervisorctl", "status"], capture_output=True, text=True)
processes = {line.split()[0]: line.split()[1] for line in result.stdout.splitlines() if len(line.split()) >= 2}
required = ("api", "scheduler", "telegram_bot")
if any(processes.get(name) != "RUNNING" for name in required):
    raise SystemExit("Required supervisor processes are not all RUNNING")
print("API, scheduler and Telegram processes RUNNING")
