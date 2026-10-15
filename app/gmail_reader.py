import base64
import os
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from app.core.database import supabase

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CREDENTIALS_FILE = PROJECT_ROOT / "credentials.json"
TOKEN_FILE = PROJECT_ROOT / "token.json"

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]


class HTMLTextExtractor(HTMLParser):
    """Cleanly extracts visible text from HTML email bodies while ignoring code/style tags."""

    def __init__(self):
        super().__init__()
        self.text_parts = []
        self.ignore_tag = False

    def handle_starttag(self, tag, attrs):
        if tag.lower() in ("style", "script", "head", "meta", "link", "title"):
            self.ignore_tag = True

    def handle_endtag(self, tag):
        if tag.lower() in ("style", "script", "head", "meta", "link", "title"):
            self.ignore_tag = False

    def handle_data(self, data):
        if not self.ignore_tag:
            cleaned = data.strip()
            if cleaned:
                self.text_parts.append(cleaned)

    def get_text(self) -> str:
        return " ".join(self.text_parts)


def get_gmail_service():
    """Initialize and return an authorized Gmail API v1 service instance."""
    if not CREDENTIALS_FILE.exists():
        raise FileNotFoundError(f"Missing credentials file: {CREDENTIALS_FILE}")

    credentials = None

    if TOKEN_FILE.exists():
        credentials = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
            print("\n🔑 Opening your browser to authorize Gmail access...")
            print("👉 If your browser does not open automatically, copy and paste the URL shown below into your browser.")
            print("👉 Log into your Google account and click 'Allow'.\n")
            credentials = flow.run_local_server(
                host="localhost",
                port=0,
                open_browser=True,
                timeout_seconds=600,
                success_message="Gmail authorization successful! You can close this browser tab.",
            )

        TOKEN_FILE.write_text(credentials.to_json(), encoding="utf-8")

    return build("gmail", "v1", credentials=credentials, cache_discovery=False)


def extract_payload_text(payload: dict) -> str:
    """Recursively extract and clean all text from a Gmail message payload."""
    raw_html = ""

    def collect_parts(part: dict):
        nonlocal raw_html
        mime = part.get("mimeType", "")
        body = part.get("body", {})
        data = body.get("data")

        if data:
            try:
                decoded = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
                if "html" in mime:
                    raw_html += " " + decoded
                elif "plain" in mime and not raw_html:
                    raw_html += " " + decoded
            except Exception:
                pass

        for subpart in part.get("parts", []):
            collect_parts(subpart)

    collect_parts(payload)

    if not raw_html:
        return ""

    parser = HTMLTextExtractor()
    parser.feed(raw_html)
    text = parser.get_text()
    return " ".join(text.split())


def classify_helapay_merchant(merchant_raw: str) -> tuple[str, str]:
    """
    Classify a HelaPay payment recipient into (category, subcategory)
    based on actual bill details instead of assuming transport.
    """
    lower = merchant_raw.lower()

    if any(k in lower for k in ("broadband", "fiber", "slt", "wifi", "internet")):
        return "Bills", "Internet"

    if any(k in lower for k in ("reload", "dialog", "mobitel", "hutch", "airtel", "prepaid", "postpaid")):
        return "Bills", "Mobile Reload"

    if any(k in lower for k in ("electricity", "ceb", "leco")):
        return "Bills", "Electricity"

    if "water" in lower or "nwsdb" in lower:
        return "Bills", "Water"

    if "insurance" in lower or "ceylinco" in lower or "slic" in lower or "aia" in lower:
        return "Insurance", "Insurance"

    if any(k in lower for k in ("doctor", "hospital", "medical", "echannelling", "doc990")):
        return "Health", "Medical"

    if any(k in lower for k in ("school", "tuition", "class", "institute", "university")):
        return "Education", "Tuition"

    return "Bills", merchant_raw.strip()


def parse_pickme_receipt(subject: str, norm_text: str, date_header: str) -> dict | None:
    """Extract bill details from a genuine PickMe receipt email."""
    # Validate receipt indicator
    trip_id_m = re.search(r"Trip ID\s*[-:]?\s*(\d+)", norm_text, re.IGNORECASE) or re.search(
        r"Trip ID\s*(\d+)", subject, re.IGNORECASE
    )
    if not trip_id_m:
        return None

    trip_id = trip_id_m.group(1)

    # Amount extraction
    fare_m = (
        re.search(r"Paid Amount\s*LKR\s*([\d,.]+)", norm_text, re.IGNORECASE)
        or re.search(r"Total Trip Fare\s*LKR\s*([\d,.]+)", norm_text, re.IGNORECASE)
        or re.search(r"Actual Fare\s*LKR\s*([\d,.]+)", norm_text, re.IGNORECASE)
        or re.search(r"LKR\s*([\d,.]+)", norm_text)
    )
    if not fare_m:
        return None

    amount = float(fare_m.group(1).replace(",", ""))

    # Service classification
    service = "Rides"
    category = "Transport"
    subcategory = "PickMe Ride"

    if "FLASH" in norm_text:
        service = "Flash"
        subcategory = "PickMe Flash"
    elif "FOOD" in norm_text:
        service = "Food"
        category = "Food"
        subcategory = "PickMe Food"
    elif "MARKET" in norm_text:
        service = "Market"
        category = "Groceries"
        subcategory = "PickMe Market"

    # Vehicle / description
    veh_m = re.search(
        r"Rate now\s*[\d.]+\s*([A-Z0-9]+)\s+([A-Za-z0-9\s\-]+?)(?=Estimated|Actual|Fare)",
        norm_text,
        re.IGNORECASE,
    )
    veh_desc = veh_m.group(2).strip() if veh_m else ""

    # Transaction date
    date_m = re.search(r"Trip ID\s*[-:]?\s*\d+\s+([A-Za-z]+\s+\d{1,2},\s+\d{4})", norm_text)
    if date_m:
        try:
            dt = datetime.strptime(date_m.group(1), "%B %d, %Y").date()
            expense_date = dt.isoformat()
        except Exception:
            expense_date = str(date_header)[:10]
    else:
        expense_date = str(date_header)[:10]

    # Payment method
    pay_m = re.search(r"(Cash|Card|Credit Card|PickMe Wallet)\s*LKR", norm_text, re.IGNORECASE)
    pay_method = pay_m.group(1) if pay_m else "Cash"

    # Route locations (pickup and dropoff)
    loc_m = re.search(
        r"\d{1,2}:\d{2}\s*(?:AM|PM)\s*(.*?)\s*\d{1,2}:\d{2}\s*(?:AM|PM)\s*(.*?)\s*(?:Tell us|Call\s*\+|Digital Mobility|$)",
        norm_text,
        re.IGNORECASE,
    )
    pickup = loc_m.group(1).strip() if loc_m else ""
    dropoff = loc_m.group(2).strip() if loc_m else ""

    title = f"PickMe {service}" + (f" ({veh_desc})" if veh_desc else "")

    notes_parts = [f"Trip ID: {trip_id}"]
    if pickup and dropoff:
        notes_parts.append(f"Route: {pickup} -> {dropoff}")
    notes_str = " | ".join(notes_parts)

    return {
        "source": "email_pickme",
        "title": title,
        "amount": amount,
        "currency": "LKR",
        "category": category,
        "subcategory": subcategory,
        "merchant": "PickMe",
        "payment_method": pay_method,
        "expense_date": expense_date,
        "reference": trip_id,
        "notes": notes_str,
    }


def parse_helapay_receipt(subject: str, norm_text: str, date_header: str) -> dict | None:
    """Extract bill details from a genuine HelaPay payment confirmation email."""
    # Check for genuine payment indicators
    if "PAID" not in norm_text and not re.search(r"You paid Rs", subject, re.IGNORECASE):
        return None

    subj_m = re.search(r"You paid\s+Rs\.?\s*([\d,.]+)\s+to\s+(.+)", subject, re.IGNORECASE)
    amt_m = re.search(r"Rs\.?\s*([\d,.]+)", norm_text)

    if subj_m:
        amount = float(subj_m.group(1).replace(",", ""))
        merchant_raw = subj_m.group(2).strip()
    elif amt_m:
        amount = float(amt_m.group(1).replace(",", ""))
        merchant_raw = "HelaPay Merchant"
    else:
        return None

    # Date format: DATE 2026-10-04 04:22:12 PM
    date_m = re.search(r"DATE\s+(\d{4}-\d{2}-\d{2})", norm_text)
    expense_date = date_m.group(1) if date_m else str(date_header)[:10]

    # Bank account
    bank_m = re.search(r"BANK ACCOUNT\s+(.*?)\s+(?:PAYMENT|REFERENCE)", norm_text, re.IGNORECASE)
    pay_method = bank_m.group(1).strip() if bank_m else "HelaPay"

    # Transaction references
    pay_id_m = re.search(r"PAYMENT\s+ID\s+(\d+)", norm_text, re.IGNORECASE)
    ref_id_m = re.search(r"REFERENCE\s+ID\s+(\d+)", norm_text, re.IGNORECASE)
    payment_id = pay_id_m.group(1) if pay_id_m else None
    ref_id = ref_id_m.group(1) if ref_id_m else None
    reference = ref_id or payment_id

    category, subcategory = classify_helapay_merchant(merchant_raw)

    notes_parts = []
    if payment_id:
        notes_parts.append(f"HelaPay Payment ID: {payment_id}")
    if ref_id:
        notes_parts.append(f"Ref ID: {ref_id}")
    if pay_method:
        notes_parts.append(f"Account: {pay_method}")
    notes_str = " | ".join(notes_parts) if notes_parts else "HelaPay Confirmation"

    return {
        "source": "email_helapay",
        "title": merchant_raw,
        "amount": amount,
        "currency": "LKR",
        "category": category,
        "subcategory": subcategory,
        "merchant": merchant_raw,
        "payment_method": pay_method,
        "expense_date": expense_date,
        "reference": reference,
        "notes": notes_str,
    }


def detect_and_parse_receipt(sender: str, subject: str, norm_text: str, date_header: str) -> dict | None:
    """Detect whether the email is from PickMe or HelaPay and extract bill details."""
    clean_sender = sender.lower()
    clean_subject = subject.lower()

    if "pickme.lk" in clean_sender or "pickme" in clean_sender or "pickme" in clean_subject:
        return parse_pickme_receipt(subject, norm_text, date_header)

    if "helapay.lk" in clean_sender or "helapay" in clean_sender or "helapay" in clean_subject or "you paid rs" in clean_subject:
        return parse_helapay_receipt(subject, norm_text, date_header)

    return None


def sync_receipt_emails(max_emails: int = 50, dry_run: bool = False) -> dict:
    """
    Scan Gmail for unimported PickMe receipts and HelaPay payment confirmations,
    extract bill details, prevent duplicate imports, and record expenses in Supabase.
    """
    service = get_gmail_service()
    query = "from:pickme.lk OR from:helapay.lk"

    response = (
        service.users()
        .messages()
        .list(
            userId="me",
            q=query,
            maxResults=max_emails,
        )
        .execute()
    )
    messages = response.get("messages", [])

    if not messages:
        return {
            "success": True,
            "total_found": 0,
            "imported_count": 0,
            "duplicates_skipped": 0,
            "ignored_count": 0,
            "imported_expenses": [],
        }

    # Load already imported message IDs to prevent duplicate processing
    try:
        imports_res = (
            supabase.table("email_imports")
            .select("message_id, expense_id, status")
            .execute()
        )
        existing_imports = {row["message_id"]: row for row in (imports_res.data or [])}
    except Exception as exc:
        print(f"Warning: could not query email_imports ({exc}). Falling back to empty set.")
        existing_imports = {}

    imported_items = []
    skipped_duplicates = 0
    ignored_count = 0
    failed_count = 0

    for msg_meta in messages:
        msg_id = msg_meta["id"]

        # 1. Primary duplicate check via email_imports table
        if msg_id in existing_imports and existing_imports[msg_id].get("status") in ("imported", "skipped_duplicate"):
            skipped_duplicates += 1
            continue

        try:
            full_msg = (
                service.users()
                .messages()
                .get(userId="me", id=msg_id, format="full")
                .execute()
            )
            headers = {
                h["name"].lower(): h["value"]
                for h in full_msg.get("payload", {}).get("headers", [])
            }
            sender = headers.get("from", "Unknown")
            subject = headers.get("subject", "")
            date_hdr = headers.get("date", "")

            norm_text = extract_payload_text(full_msg.get("payload", {}))
            parsed = detect_and_parse_receipt(sender, subject, norm_text, date_hdr)

            if not parsed or parsed["amount"] <= 0:
                ignored_count += 1
                continue

            # 2. Secondary duplicate check: check if reference already exists in expenses.notes
            ref = parsed.get("reference")
            if ref:
                existing_expense = (
                    supabase.table("expenses")
                    .select("id, title, amount")
                    .ilike("notes", f"%{ref}%")
                    .limit(1)
                    .execute()
                )
                if existing_expense.data:
                    # Already imported under a previous run/source
                    if not dry_run:
                        supabase.table("email_imports").upsert(
                            {
                                "provider": "gmail",
                                "message_id": msg_id,
                                "sender": sender,
                                "subject": subject,
                                "status": "skipped_duplicate",
                                "expense_id": existing_expense.data[0]["id"],
                                "imported_at": datetime.now(timezone.utc).isoformat(),
                            },
                            on_conflict="message_id",
                        ).execute()
                    skipped_duplicates += 1
                    continue

            # 3. Save to Supabase expenses table
            if not dry_run:
                expense_payload = {
                    "title": parsed["title"],
                    "amount": parsed["amount"],
                    "category": parsed["category"],
                    "subcategory": parsed["subcategory"],
                    "merchant": parsed["merchant"],
                    "payment_method": parsed["payment_method"],
                    "expense_date": parsed["expense_date"],
                    "notes": parsed["notes"],
                    "source": parsed["source"],
                }
                exp_res = supabase.table("expenses").insert(expense_payload).execute()
                created_expense = exp_res.data[0]
                new_expense_id = created_expense["id"]

                # 4. Record successful import in email_imports
                supabase.table("email_imports").upsert(
                    {
                        "provider": "gmail",
                        "message_id": msg_id,
                        "sender": sender,
                        "subject": subject,
                        "status": "imported",
                        "expense_id": new_expense_id,
                        "imported_at": datetime.now(timezone.utc).isoformat(),
                    },
                    on_conflict="message_id",
                ).execute()

                parsed["expense_id"] = new_expense_id
            else:
                parsed["expense_id"] = None

            imported_items.append(parsed)

        except Exception as exc:
            failed_count += 1
            print(f"Error processing message {msg_id}: {exc}")
            if not dry_run:
                try:
                    supabase.table("email_imports").upsert(
                        {
                            "provider": "gmail",
                            "message_id": msg_id,
                            "sender": sender if "sender" in locals() else "Unknown",
                            "subject": subject if "subject" in locals() else "",
                            "status": "failed",
                            "error_message": str(exc)[:1000],
                        },
                        on_conflict="message_id",
                    ).execute()
                except Exception:
                    pass

    return {
        "success": True,
        "total_found": len(messages),
        "imported_count": len(imported_items),
        "duplicates_skipped": skipped_duplicates,
        "ignored_count": ignored_count,
        "failed_count": failed_count,
        "imported_expenses": imported_items,
    }


def find_receipt_emails(max_results: int = 10):
    """CLI preview command displaying matching Gmail messages and parsed details."""
    result = sync_receipt_emails(max_emails=max_results, dry_run=False)
    print("\n" + "=" * 65)
    print("EXPENSA EMAIL RECEIPT SYNCHRONIZER")
    print("=" * 65)
    print(f"Total matching emails inspected : {result['total_found']}")
    print(f"Newly imported expenses         : {result['imported_count']}")
    print(f"Duplicate emails skipped        : {result['duplicates_skipped']}")
    print(f"Non-receipt/ignored emails      : {result['ignored_count']}")
    print(f"Failed emails                   : {result.get('failed_count', 0)}")
    print("-" * 65)

    if result["imported_expenses"]:
        print("\nIMPORTED TRANSACTIONS:")
        for idx, exp in enumerate(result["imported_expenses"], start=1):
            ref_info = f"Ref: {exp.get('reference')}" if exp.get("reference") else ""
            print(
                f" {idx:2d}. [{exp['expense_date']}] {exp['category']:<11} | "
                f"{exp['title']:<32} | LKR {exp['amount']:>8,.2f} | {ref_info}"
            )
    else:
        print("\nAll emails are up-to-date! No new unimported receipts found.")
    print("=" * 65 + "\n")


def start_email_sync_scheduler():
    """Run a dedicated background scheduler for twice-daily email receipt fetching."""
    from apscheduler.schedulers.blocking import BlockingScheduler
    from zoneinfo import ZoneInfo

    tz = ZoneInfo("Asia/Colombo")
    scheduler = BlockingScheduler(timezone=tz)

    print("\n" + "=" * 65)
    print("EXPENSA AUTOMATED EMAIL RECEIPT SCHEDULER")
    print("=" * 65)
    print("Schedule: Twice daily (Asia/Colombo)")
    print("  1. Afternoon : 2:00 PM (14:00)")
    print("  2. Night     : 11:30 PM (23:30)")
    print("=" * 65)

    def scheduled_run(trigger_name: str):
        now_str = datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n[{now_str}] Executing {trigger_name} email sync...")
        res = sync_receipt_emails(max_emails=50, dry_run=False)
        print(
            f"Finished {trigger_name}: {res['total_found']} inspected, "
            f"{res['imported_count']} newly imported, {res['duplicates_skipped']} duplicates skipped."
        )

    scheduler.add_job(
        scheduled_run,
        trigger="cron",
        hour=14,
        minute=0,
        id="email_sync_2pm",
        name="Receipt Email Sync (2:00 PM)",
        kwargs={"trigger_name": "2:00 PM Afternoon Sync"},
    )
    scheduler.add_job(
        scheduled_run,
        trigger="cron",
        hour=23,
        minute=30,
        id="email_sync_1130pm",
        name="Receipt Email Sync (11:30 PM)",
        kwargs={"trigger_name": "11:30 PM Night Sync"},
    )

    # Initial sync on startup
    print("Running initial sync on scheduler startup...")
    scheduled_run("Startup Check")

    print("\nScheduler active. Waiting for scheduled triggers (Ctrl+C to stop)...")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("\nAutomated receipt email scheduler stopped.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Expensa Gmail Receipt Fetcher & Synchronizer",
    )
    parser.add_argument(
        "--schedule",
        "-s",
        action="store_true",
        help="Run continuously on the twice-daily automated schedule (2:00 PM & 11:30 PM Colombo time)",
    )
    parser.add_argument(
        "--max",
        "-m",
        type=int,
        default=50,
        help="Maximum emails to inspect in a single sync run (default: 50)",
    )
    args = parser.parse_args()

    if args.schedule:
        start_email_sync_scheduler()
    else:
        find_receipt_emails(max_results=args.max)
