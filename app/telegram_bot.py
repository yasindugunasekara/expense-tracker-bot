
import os
import re
import logging

import httpx
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

load_dotenv()

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ALLOWED_USER_ID = os.getenv("TELEGRAM_ALLOWED_USER_ID")
API_BASE_URL = os.getenv(
    "API_BASE_URL",
    "http://127.0.0.1:8000",
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

if not BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is missing from .env")

if not ALLOWED_USER_ID:
    raise RuntimeError("TELEGRAM_ALLOWED_USER_ID is missing from .env")

ALLOWED_USER_ID = int(ALLOWED_USER_ID)


def _matches_keyword(text: str, keyword: str) -> bool:
    """Check if keyword matches whole-word or substring for multi-word phrases."""
    if " " in keyword:
        return keyword in text
    return bool(re.search(r"\b" + re.escape(keyword) + r"\b", text))


def detect_category_and_keyword(title: str) -> tuple[str, str | None]:
    """
    Detect the category and the specific matched keyword from title.
    Keywords are sorted by length descending so longer/more specific phrases
    (e.g., 'bday party', 'after exam party') match before shorter ones ('bday', 'party').
    Returns: (category, matched_keyword)
    """
    text = title.lower().strip()

    category_rules = [
        (
            "Bodim Fee",
            [
                "bodim fee", "bodim", "bodima", "boarding fee", "boarding",
                "room rent", "house rent", "hostel fee", "hostel", "room fee",
            ],
        ),
        (
            "Medicine",
            [
                "meet doctor", "doctor fee", "doctor", "medicine", "medicines",
                "pharmacy", "channeling", "chanelling", "drugs", "tablets",
                "pills", "panadol", "paracetamol", "syrup", "medical", "clinic",
                "hospital", "dentist", "blood test", "test report", "scan",
                "injection", "ointment", "health",
            ],
        ),
        (
            "Loan",
            [
                "loan to", "took loan", "gave loan", "loan", "borrow",
                "borrowed", "lend", "lent", "lending", "debt", "nawa",
                "naya", "credit",
            ],
        ),
        (
            "Enjoy",
            [
                "after exam party", "birthday party", "pool party", "birthday",
                "bday party", "bday", "party", "fun", "outing", "hangout",
                "celebration", "treat", "trip", "club", "concert", "drinks",
                "game", "gaming", "movie", "cinema", "gathering",
            ],
        ),
        (
            "Utilities",
            [
                "water bill", "current bill", "electricity", "water", "ceb",
                "leco", "wifi", "internet", "dialog", "mobitel", "slt",
                "airtel", "hutch", "reload", "recharge", "phone bill", "bill","package",
            ],
        ),
        (
            "Transport",
            [
                "tuk tuk", "three wheeler", "threewheeler", "threewheel",
                "bus", "train", "pickme", "uber", "petrol", "fuel", "bike",
                "taxi", "tuk", "van", "highway", "diesel", "parking",
                "expressway","petral",
            ],
        ),
        (
            "Food",
            [
                "short eats", "water bottle", "cool drink", "ice cream",
                "lunch", "dinner", "breakfast", "food", "restaurant",
                "coffee", "tea", "snack", "snacks", "kottu", "rice",
                "curry", "hoppers", "bakery", "cafe", "bites", "juice",
                "pizza", "burger", "dessert",
            ],
        ),
        (
            "Buy",
            [
                # Purchase actions
                "buy", "bought", "purchase", "purchased", "order", "ordered",
                # Clothing & wearables
                "shirt", "shairt", "t-shirt", "tshirt", "cloth", "clouth",
                "clothes", "clothing", "dress", "pants", "trousers", "jeans",
                "shoes", "slippers", "sandal", "sandals", "sarong", "socks",
                "jacket", "hoodie", "cap", "belt",
                # Electronics & accessories
                "phone", "mobile", "laptop", "tablet", "mouse", "keyboard",
                "headphones", "headphone", "earphones", "earphone", "airpods",
                "earbuds", "charger", "cable", "power bank", "pendrive", "monitor",
                "bag", "backpack", "watch", "perfume", "wallet", "sunglasses",
                "glasses", "book", "books", "stationery", "pen", "notebook",
            ],
        ),
    ]

    for category, keywords in category_rules:
        # Sort keywords longest-first so 'bday party' matches before 'bday' or 'party'
        sorted_keywords = sorted(keywords, key=len, reverse=True)
        for kw in sorted_keywords:
            if _matches_keyword(text, kw):
                return category, kw

    return "Other", None


def detect_category(title: str) -> str:
    """Helper returning only the category name."""
    category, _ = detect_category_and_keyword(title)
    return category



async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    await update.message.reply_text(
        "👋 Welcome to your Expense Tracker!\n\n"
        "✨ Quick Guide:\n\n"
        "🎯 Events & Trips:\n"
        "• start trip to Kandy (or start trip Galle)\n"
        "• start campus (or start go to campus)\n"
        "• start event Birthday Party\n"
        "• active event (check active event)\n"
        "• end event (finish & deactivate active event)\n\n"
        "💵 Record Expenses:\n"
        "• Single: bus 1000\n"
        "• Multiple (one per line):\n"
        "  bus 600\n"
        "  party 2500\n"
        "  dinner 400\n\n"
        "💡 Any expenses added during an active event are automatically linked to it!"
    )


async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    await update.message.reply_text(
        "📖 Available Commands & Formats:\n\n"
        "🌴 Trips & Events:\n"
        "• start trip to <destination>\n"
        "• start campus\n"
        "• start event <event name>\n"
        "• active trip / active event\n"
        "• end trip / end event\n\n"
        "💸 Expenses (description amount):\n"
        "• bus 1000\n"
        "• lunch 800\n"
        "• bodim fee 15000\n"
        "• electricity 4500\n"
        "• buy shirt 2500\n"
        "• buy phone 40000\n"
        "• perera bday party 3000\n"
        "• meet doctor 2000\n"
        "• loan to amal 5000\n\n"
        "📋 Multi-line Expenses:\n"
        "bus 600\n"
        "party 2500\n"
        "dinner 400"
    )


async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    user = update.effective_user
    message = update.effective_message

    # Only accept messages from the allowed Telegram account.
    if user is None or user.id != ALLOWED_USER_ID:
        await message.reply_text("Sorry, you are not authorized.")
        return

    text = (message.text or "").strip()
    if not text:
        return

    # -------------------------------------------------------------
    # 1. Event Command: Check active event
    # -------------------------------------------------------------
    if text.lower() in {"active trip", "active event", "current trip", "current event", "trip status", "event status"}:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(f"{API_BASE_URL}/events/active")
                response.raise_for_status()
                data = response.json()
                event = data.get("active_event") if isinstance(data, dict) and "active_event" in data else data

            if not event:
                await message.reply_text("There is no active trip or event.")
            else:
                dest = event.get("destination") or "-"
                event_type = (event.get("event_type") or "other").capitalize()
                await message.reply_text(
                    "📌 Active Event:\n\n"
                    f"• Name: {event.get('name', 'Unknown')}\n"
                    f"• Type: {event_type}\n"
                    f"• Destination: {dest}\n"
                    f"• Event ID: {event.get('id')}\n\n"
                    "💡 Future expenses will be automatically linked to this event."
                )
        except httpx.HTTPError:
            logger.exception("Could not retrieve active event")
            await message.reply_text("Could not check the active event. Ensure FastAPI is running.")
        return

    # -------------------------------------------------------------
    # 2. Event Command: End / Deactivate active event
    # -------------------------------------------------------------
    if text.lower() in {"end trip", "end event", "trip end", "event end", "finish trip", "finish event", "stop trip", "stop event"}:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(f"{API_BASE_URL}/events/active")
                response.raise_for_status()
                data = response.json()
                event = data.get("active_event") if isinstance(data, dict) and "active_event" in data else data

                if not event:
                    await message.reply_text("There is no active trip or event to end.")
                    return

                event_id = event.get("id")
                if event_id is None:
                    await message.reply_text("Could not find the active event ID.")
                    return

                end_response = await client.post(f"{API_BASE_URL}/events/{event_id}/end")
                end_response.raise_for_status()

            await message.reply_text(
                "✅ Event ended successfully!\n\n"
                f"• Event: {event.get('name', 'Unknown')}\n"
                f"• Event ID: {event_id}\n\n"
                "Your future expenses will no longer be linked to this event."
            )
        except httpx.HTTPError:
            logger.exception("Could not end event")
            await message.reply_text("Could not end the event. Check the FastAPI terminal for details.")
        return

    # -------------------------------------------------------------
    # 3. Event Command: Start a trip, campus event, or custom event
    # -------------------------------------------------------------
    trip_match = re.fullmatch(r"start\s+trip(?:\s+to)?\s+(.+)", text, re.IGNORECASE)
    event_match = re.fullmatch(r"start\s+event(?:\s+to)?\s+(.+)", text, re.IGNORECASE)
    is_campus = text.lower() in {"start go to campus", "start campus"}

    if trip_match or is_campus or event_match:
        if is_campus:
            event_name = "Go to campus"
            event_type = "campus"
            destination = "Campus"
        elif trip_match:
            destination = trip_match.group(1).strip()
            event_name = f"Trip to {destination}"
            event_type = "trip"
        else:
            destination = None
            event_name = event_match.group(1).strip()
            event_type = "other"

        try:
            payload = {
                "name": event_name,
                "event_type": event_type,
            }
            if destination:
                payload["destination"] = destination

            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.post(
                    f"{API_BASE_URL}/events",
                    json=payload,
                )

                if response.status_code == 409:
                    err_msg = response.json().get("detail", "You already have an active event.")
                    await message.reply_text(
                        f"⚠️ {err_msg}\n\n"
                        "Send 'active event' to check it, or 'end event' before starting another."
                    )
                    return

                response.raise_for_status()
                data = response.json()
                created = data.get("event", data)

            await message.reply_text(
                "🎉 Event started successfully!\n\n"
                f"• Event: {created.get('name', event_name)}\n"
                f"• Type: {event_type.capitalize()}\n"
                f"• Destination: {destination or '-'}\n"
                f"• Event ID: {created.get('id', 'created')}\n\n"
                "Now send expenses normally (e.g., 'bus 1000').\n"
                "They will be automatically linked to this event."
            )
        except httpx.HTTPError:
            logger.exception("Could not start event")
            await message.reply_text("Could not start the event. Check the FastAPI terminal.")
        return

    # -------------------------------------------------------------
    # 4. Expense Entry: Single or Multiple Lines
    # -------------------------------------------------------------
    raw_lines = [line.strip() for line in text.splitlines() if line.strip()]
    parsed_items = []
    invalid_lines = []
    line_pattern = re.compile(r"^(.+?)\s+(\d+(?:,\d{3})*(?:\.\d{1,2})?)$")

    for line in raw_lines:
        match = line_pattern.match(line)
        if not match:
            invalid_lines.append(f"'{line}' (Invalid format - expected: description amount)")
            continue

        title = match.group(1).strip()
        try:
            amount = float(match.group(2).replace(",", ""))
        except ValueError:
            invalid_lines.append(f"'{line}' (Invalid number)")
            continue

        if amount <= 0:
            invalid_lines.append(f"'{line}' (Amount must be > 0)")
            continue

        category, subcategory = detect_category_and_keyword(title)
        parsed_items.append({
            "title": title,
            "amount": amount,
            "category": category,
            "subcategory": subcategory,
            "source": "telegram",
        })

    # If no lines were valid expenses or commands
    if not parsed_items:
        await message.reply_text(
            "I couldn't understand that message.\n\n"
            "Try one of these commands:\n"
            "• start trip to Kandy\n"
            "• start campus\n"
            "• start event Birthday Party\n"
            "• active event\n"
            "• end event\n\n"
            "Or send an expense:\n"
            "• bus 1000\n"
            "• lunch 800\n\n"
            "Or multiple expenses:\n"
            "bus 600\n"
            "party 2500\n"
            "dinner 400"
        )
        return

    # Case A: Single expense entered
    if len(parsed_items) == 1 and not invalid_lines:
        item = parsed_items[0]
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.post(
                    f"{API_BASE_URL}/expenses",
                    json=item,
                )
                response.raise_for_status()
                saved_data = response.json()

            expense_obj = saved_data.get("expense", saved_data)
            expense_id = expense_obj.get("id", "saved")
            event_name = expense_obj.get("event_name")
            linked_event = expense_obj.get("event_id")

            msg_lines = [
                "Expense saved successfully!\n",
                f"Description: {item['title']}",
                f"Amount: LKR {item['amount']:,.2f}",
                f"Category: {item['category']}",
            ]
            if item["subcategory"]:
                msg_lines.append(f"Tag / Keyword: {item['subcategory']}")
            if event_name:
                msg_lines.append(f"Linked Event: {event_name}")
            elif linked_event:
                msg_lines.append(f"Linked Event: Event #{linked_event}")

            await message.reply_text("\n".join(msg_lines))
            return

        except httpx.HTTPStatusError:
            logger.exception("API rejected the expense")
            await message.reply_text(
                "The API could not save this expense. "
                "Check the FastAPI terminal for details."
            )
            return

        except httpx.RequestError:
            logger.exception("Could not connect to the expense API")
            await message.reply_text(
                "Cannot connect to the expense API. "
                "Make sure FastAPI is running."
            )
            return

    # Case B: Multiple expenses entered
    saved_results = []
    failed_items = []
    active_event_name = None

    async with httpx.AsyncClient(timeout=30) as client:
        for item in parsed_items:
            try:
                response = await client.post(
                    f"{API_BASE_URL}/expenses",
                    json=item,
                )
                response.raise_for_status()
                saved_data = response.json()
                expense_obj = saved_data.get("expense", saved_data)
                ev_name = expense_obj.get("event_name")
                if ev_name and not active_event_name:
                    active_event_name = ev_name
                elif expense_obj.get("event_id") and not active_event_name:
                    active_event_name = f"Event #{expense_obj.get('event_id')}"
                saved_results.append({
                    "item": item,
                    "id": expense_obj.get("id", "saved"),
                })
            except Exception as exc:
                logger.exception("Failed to save expense '%s': %s", item["title"], exc)
                failed_items.append(f"{item['title']} (Save error)")

    total_amount = sum(r["item"]["amount"] for r in saved_results)
    reply_blocks = []

    if saved_results:
        count = len(saved_results)
        reply_blocks.append(f"✅ {count} expense{'s' if count > 1 else ''} saved successfully!\n")
        for idx, res in enumerate(saved_results, 1):
            it = res["item"]
            tag_info = f" ({it['subcategory']})" if it["subcategory"] else ""
            reply_blocks.append(
                f"{idx}. {it['title']}\n"
                f"   • Amount: LKR {it['amount']:,.2f}\n"
                f"   • Category: {it['category']}{tag_info}\n"
            )
        reply_blocks.append(f"\n💰 Total: LKR {total_amount:,.2f}")
        if active_event_name:
            reply_blocks.append(f"Linked Event: {active_event_name}")

    if invalid_lines or failed_items:
        issues = invalid_lines + failed_items
        reply_blocks.append("\n⚠️ Skipped lines:\n• " + "\n• ".join(issues))

    await message.reply_text("\n".join(reply_blocks))


def main():
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message,
        )
    )

    print("Telegram expense bot is running...")
    application.run_polling()


if __name__ == "__main__":
    main()