
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
        "Welcome to your Expense Tracker!\n\n"
        "You can send single or multiple expenses:\n\n"
        "📌 Single expense:\n"
        "bus 1000\n\n"
        "📌 Multiple expenses (one per line):\n"
        "bus 600\n"
        "party 2500\n"
        "dinner 400\n\n"
        "Format: description amount"
    )


async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    await update.message.reply_text(
        "Send expenses in this format:\n"
        "description amount\n\n"
        "Examples:\n"
        "• bus 1000\n"
        "• lunch 800\n"
        "• bodim fee 15000\n"
        "• electricity 4500\n"
        "• buy shairt 2500\n"
        "• buy phone 40000\n"
        "• perera bday party 3000\n"
        "• meet doctor 2000\n"
        "• loan to amal 5000\n\n"
        "You can also send multiple expenses together:\n"
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

    raw_lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not raw_lines:
        return

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

    # If no lines were valid
    if not parsed_items:
        err_text = (
            "No valid expenses found.\n\n"
            "Please send in this format:\n"
            "description amount\n\n"
            "Example:\n"
            "bus 600\n"
            "party 2500\n"
            "dinner 400"
        )
        if invalid_lines:
            err_text += "\n\n⚠️ Issues found:\n• " + "\n• ".join(invalid_lines)
        await message.reply_text(err_text)
        return

    # Case 1: Single expense entered (clean standard response)
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

            msg_lines = [
                "Expense saved successfully!\n",
                f"Description: {item['title']}",
                f"Amount: LKR {item['amount']:,.2f}",
                f"Category: {item['category']}",
            ]
            if item["subcategory"]:
                msg_lines.append(f"Tag / Keyword: {item['subcategory']}")
            

            await message.reply_text("\n".join(msg_lines))
            return

        except httpx.HTTPStatusError as exc:
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

    # Case 2: Multiple expenses entered (or mixture of valid + invalid lines)
    saved_results = []
    failed_items = []

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