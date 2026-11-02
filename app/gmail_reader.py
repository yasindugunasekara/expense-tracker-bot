import base64
import logging
import re
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from email.utils import parsedate_to_datetime, parseaddr
from zoneinfo import ZoneInfo
from html.parser import HTMLParser


from app.core.database import supabase
from app.automation.telegram_notifications import queue_notification, deliver_pending

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


from app.gmail_auth import get_gmail_service


def extract_payload_text(payload: dict) -> str:
    """Recursively extract and clean all text from a Gmail message payload."""
    html_parts, plain_parts = [], []
    def collect(part):
        mime = part.get("mimeType", "")
        data = part.get("body", {}).get("data")
        if data and not part.get("filename") and mime in ("text/html", "text/plain"):
            decoded = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
            (html_parts if mime == "text/html" else plain_parts).append(decoded)
        for child in part.get("parts", []):
            collect(child)
    collect(payload)
    if html_parts:
        parser = HTMLTextExtractor()
        parser.feed(" ".join(html_parts))
        return " ".join(parser.get_text().split())
    return " ".join(" ".join(plain_parts).split())


IMPORT_START_DATE = date(2026, 1, 1)
LOCAL_TIMEZONE = ZoneInfo("Asia/Colombo")


def validate_receipt(parsed, today=None):
    """Reject invalid facts and exclude genuine receipts outside the selected period."""
    transaction_date = date.fromisoformat(parsed["expense_date"])
    today = today or datetime.now(LOCAL_TIMEZONE).date()
    if transaction_date > today:
        raise ValueError("Receipt transaction date is in the future")
    try:
        amount = Decimal(str(parsed["amount"]))
    except (InvalidOperation, TypeError):
        raise ValueError("Receipt amount is invalid") from None
    if not amount.is_finite() or amount <= 0:
        raise ValueError("Receipt amount must be positive and finite")
    return transaction_date >= IMPORT_START_DATE


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


def receipt_header_date(value):
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(LOCAL_TIMEZONE).date().isoformat()
    except (ValueError, TypeError, OverflowError):
        raise ValueError("Receipt has no valid transaction date or email Date header") from None


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
        re.search(r"Paid Amount\s*:?\s*LKR\s*([\d,.]+)", norm_text, re.IGNORECASE)
        or re.search(r"Total Trip Fare\s*:?\s*LKR\s*([\d,.]+)", norm_text, re.IGNORECASE)
        or re.search(r"Actual Fare\s*:?\s*LKR\s*([\d,.]+)", norm_text, re.IGNORECASE)
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
        except ValueError:
            raise ValueError("PickMe receipt contains an invalid transaction date") from None
    else:
        expense_date = receipt_header_date(date_header)

    # Payment method
    pay_m = re.search(r"(Cash|Card|Credit Card|PickMe Wallet)\s*LKR", norm_text, re.IGNORECASE)
    pay_method = pay_m.group(1) if pay_m else None

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
    else:
        return None

    # Date format: DATE 2026-10-04 04:22:12 PM
    date_m = re.search(r"DATE\s+(\d{4}-\d{2}-\d{2})", norm_text)
    expense_date = date.fromisoformat(date_m.group(1)).isoformat() if date_m else receipt_header_date(date_header)

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


def verified_spam_receipt(message):
    """Only import Spam receipts with provider-aligned Gmail DKIM/DMARC verification."""
    headers = message.get("payload", {}).get("headers", [])
    sender = next((h["value"] for h in headers if h["name"].lower() == "from"), "")
    domain = parseaddr(sender)[1].lower().rsplit("@", 1)[-1]
    def provider(value):
        value = value.lower().strip('"').rsplit("@", 1)[-1]
        return next((root for root in ("pickme.lk", "helapay.lk") if value == root or value.endswith("." + root)), None)
    expected = provider(domain)
    if not expected:
        return False
    authentication = next((h["value"] for h in headers if h["name"].lower() == "authentication-results" and h["value"].lstrip().lower().startswith("mx.google.com;")), "")
    for segment in authentication.split(";")[1:]:
        if re.match(r"\s*(?:dkim|dmarc)=pass\b", segment, re.I):
            fields = re.findall(r"header\.(?:i|d|from)=([^\s;]+)", segment, re.I)
            if any(provider(field) == expected for field in fields):
                return True
    return False


def sync_receipt_emails(max_emails: int = 50, dry_run: bool = False) -> dict:
    from filelock import FileLock, Timeout
    from app.gmail_auth import token_path
    path = token_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with FileLock(str(path.parent / "receipt-sync.lock"), timeout=0):
            result = _sync_receipt_emails(max_emails, dry_run)
            if not dry_run:
                result["telegram_notifications"] = deliver_pending()
            return result
    except Timeout:
        return {"success": False, "busy": True, "message": "Receipt import already running; retry later."}


def _sync_receipt_emails(max_emails: int = 50, dry_run: bool = False) -> dict:
    """
    Scan Gmail for unimported PickMe receipts and HelaPay payment confirmations,
    extract bill details, prevent duplicate imports, and record expenses in Supabase.
    """
    service = get_gmail_service()
    cutoff = int(datetime.combine(IMPORT_START_DATE, datetime.min.time(), LOCAL_TIMEZONE).timestamp()) - 1
    query = f"(from:pickme.lk OR from:helapay.lk) -in:trash after:{cutoff}"

    if not 1 <= max_emails <= 500:
        raise ValueError("max_emails must be between 1 and 500 (Gmail page size)")
    messages = []
    page_token = None
    while True:
        response = service.users().messages().list(
            userId="me", q=query, maxResults=max_emails, pageToken=page_token, includeSpamTrash=True,
        ).execute(num_retries=3)
        messages.extend(response.get("messages", []))
        logging.getLogger(__name__).info("Receipt scan: %d matching message IDs found", len(messages))
        page_token = response.get("nextPageToken")
        if not page_token:
            break

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
        existing_imports = {}
        for offset in range(0, len(messages), 100):
            ids = [message["id"] for message in messages[offset:offset + 100]]
            imports_res = supabase.table("email_imports").select("message_id,expense_id,status").in_("message_id", ids).execute()
            existing_imports.update({row["message_id"]: row for row in (imports_res.data or [])})
        linked_ids = list({row.get("expense_id") for row in existing_imports.values() if row.get("expense_id") is not None})
        valid_ids = set()
        for offset in range(0, len(linked_ids), 100):
            linked = supabase.table("expenses").select("id").in_("id", linked_ids[offset:offset + 100]).execute()
            valid_ids.update(row["id"] for row in (linked.data or []))
        missing_links = {mid for mid, row in existing_imports.items() if row.get("status") in ("imported", "skipped_duplicate") and row.get("expense_id") not in valid_ids}
        for mid in missing_links:
            del existing_imports[mid]
    except Exception:
        raise RuntimeError("Cannot load email import tracking; aborting to prevent duplicate expenses.") from None

    imported_items = []
    skipped_duplicates = 0
    ignored_count = 0
    failed_count = 0
    excluded_count = 0
    unverified_spam_count = 0

    for message_index, msg_meta in enumerate(messages):
        if message_index % 50 == 0:
            logging.getLogger(__name__).info("Receipt import progress: %d/%d inspected, %d imported", message_index, len(messages), len(imported_items))
        sender, subject = "Unknown", ""
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
                .execute(num_retries=3)
            )
            if "TRASH" in full_msg.get("labelIds", []):
                ignored_count += 1
                continue
            if "SPAM" in full_msg.get("labelIds", []) and not verified_spam_receipt(full_msg):
                unverified_spam_count += 1
                logging.getLogger(__name__).warning("Skipping Spam receipt without verified provider authentication: %s", msg_id)
                continue
            headers = {
                h["name"].lower(): h["value"]
                for h in full_msg.get("payload", {}).get("headers", [])
            }
            sender = headers.get("from", "Unknown")
            subject = headers.get("subject", "")
            date_hdr = headers.get("date", "")

            norm_text = extract_payload_text(full_msg.get("payload", {}))
            parsed = detect_and_parse_receipt(sender, subject, norm_text, date_hdr)

            if not parsed:
                ignored_count += 1
                continue
            if not validate_receipt(parsed):
                excluded_count += 1
                continue

            marker = f"[gmail:{msg_id}]"
            recovered = supabase.table("expenses").select("id").like("notes", f"%{marker}%").limit(1).execute()
            if recovered.data:
                if not dry_run:
                    queue_notification(msg_id, {**parsed, "expense_id": recovered.data[0]["id"]})
                    supabase.table("email_imports").upsert({"provider": "gmail", "message_id": msg_id, "status": "imported", "expense_id": recovered.data[0]["id"]}, on_conflict="message_id").execute()
                skipped_duplicates += 1
                continue

            # 2. Secondary duplicate check: check if reference already exists in expenses.notes
            ref = parsed.get("reference")
            if ref:
                existing_expense = (
                    supabase.table("expenses")
                    .select("id, title, amount, notes")
                    .ilike("notes", f"%{ref}%")
                    .execute()
                )
                matches = [row for row in (existing_expense.data or []) if re.search(r"(?<!\d)" + re.escape(ref) + r"(?!\d)", row.get("notes") or "")]
                if matches:
                    # Already imported under a previous run/source
                    if not dry_run:
                        supabase.table("email_imports").upsert(
                            {
                                "provider": "gmail",
                                "message_id": msg_id,
                                "sender": sender,
                                "subject": subject,
                                "status": "skipped_duplicate",
                                "expense_id": matches[0]["id"],
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
                    "notes": f"{parsed['notes']} {marker}",
                    "source": parsed["source"],
                }
                exp_res = supabase.table("expenses").insert(expense_payload).execute()
                created_expense = exp_res.data[0]
                new_expense_id = created_expense["id"]
                queue_notification(msg_id, {**parsed, "expense_id": new_expense_id})

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
        "success": failed_count == 0,
        "total_found": len(messages),
        "imported_count": len(imported_items),
        "duplicates_skipped": skipped_duplicates,
        "ignored_count": ignored_count,
        "failed_count": failed_count,
        "excluded_before_start_date": excluded_count,
        "import_start_date": IMPORT_START_DATE.isoformat(),
        "missing_links_retried": len(missing_links),
        "unverified_spam_skipped": unverified_spam_count,
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
    """Run a dedicated background scheduler for hourly email receipt fetching."""
    from apscheduler.schedulers.blocking import BlockingScheduler
    from zoneinfo import ZoneInfo

    tz = ZoneInfo("Asia/Colombo")
    scheduler = BlockingScheduler(timezone=tz)

    print("\n" + "=" * 65)
    print("EXPENSA AUTOMATED EMAIL RECEIPT SCHEDULER")
    print("=" * 65)
    print("Schedule: Every hour at minute 00 (Asia/Colombo)")
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
        scheduled_run, trigger="cron", hour="*", minute=0,
        id="email_sync_hourly", name="Hourly receipt email sync",
        kwargs={"trigger_name": "Hourly Sync"}, max_instances=1,
        coalesce=True, misfire_grace_time=3600,
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
        help="Run continuously; fetch every hour at minute 00 in Colombo time",
    )
    parser.add_argument(
        "--max",
        "-m",
        type=int,
        default=50,
        help="Gmail page size; all pages are scanned (default: 50)",
    )
    args = parser.parse_args()

    if args.schedule:
        start_email_sync_scheduler()
    else:
        find_receipt_emails(max_results=args.max)
