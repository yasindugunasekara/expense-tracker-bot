import os,sys
from types import ModuleType
from unittest.mock import MagicMock
os.environ["SUPABASE_URL"]="https://example.invalid"
os.environ["SUPABASE_KEY"]="test-only"
os.environ["GMAIL_REPORT_TO"]="test@example.invalid"
database=ModuleType("app.core.database")
database.supabase=MagicMock()
sys.modules["app.core.database"]=database
