import os,sys
from types import ModuleType
from unittest.mock import MagicMock
os.environ["SUPABASE_URL"]="https://example.invalid"
os.environ["SUPABASE_KEY"]="test-only"
os.environ["GMAIL_REPORT_TO"]="test@example.invalid"
database=ModuleType("app.core.database")
database.supabase=MagicMock()
sys.modules["app.core.database"]=database

import pytest
@pytest.fixture(autouse=True)
def isolate_telegram_notifications(monkeypatch,tmp_path):
    from app.automation import telegram_notifications
    monkeypatch.setattr(telegram_notifications,"token_path",lambda:tmp_path/"token.json")
    monkeypatch.setattr(telegram_notifications,"send_notification",MagicMock(return_value=123))
