
import os
import re
import logging
import asyncio
import json
from datetime import datetime, date, timedelta

import httpx
from dotenv import load_dotenv
from google import genai
from google.genai import types
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

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv(
    "GEMINI_MODEL",
    "gemini-3.8-flash",
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

if not BOT_TOKEN:
    raise RuntimeError("TELEGRAM_BOT_TOKEN is missing from .env")

if not ALLOWED_USER_ID:
    raise RuntimeError("TELEGRAM_ALLOWED_USER_ID is missing from .env")

ALLOWED_USER_ID = int(ALLOWED_USER_ID)

ai_client = (
    genai.Client(api_key=GEMINI_API_KEY)
    if GEMINI_API_KEY
    else None
)


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
            "Rental",
            [
                "rent lens", "rent scooter", "rent camera", "rent bike", "rent car",
                "rent vehicle", "rent van", "rent dress", "rent suit", "rent equipment",
                "rent room", "rent house", "rent apartment", "rent hall", "rent sound",
                "rent lights", "rent drone", "lens rent", "scooter rent", "camera rent",
                "bike rent", "car rent", "vehicle rent", "equipment rent", "scooter rental",
                "bike rental", "car rental", "camera rental", "lens rental", "drone rent",
                "rental", "rent", "rented", "renting", "hire", "hired", "hiring", "lease", "leasing",
            ],
        ),
        (
            "Fitness",
            [
                "gym fee", "gym membership", "gym package", "gym sub", "gym subscription",
                "gym", "fitness", "workout", "crossfit", "bodybuilding", "calisthenics",
                "yoga class", "yoga", "pilates", "zumba", "aerobics", "swimming pool",
                "swimming", "personal trainer", "trainer fee", "trainer", "pt fee",
                "badminton court", "badminton", "futsal court", "futsal", "cricket net",
                "cricket ground", "tennis court", "tennis", "sports", "whey protein",
                "whey", "protein powder", "protein", "creatine", "pre-workout", "preworkout",
                "supplements", "supplement",
            ],
        ),
        (
            "Fund",
            [
                "welfare fund", "batch fund", "class fund", "society fund", "club fund",
                "office fund", "department fund", "charity fund", "memorial fund",
                "fund collection", "fund contribution", "fund fee", "fund", "funds",
                "donation", "donate", "donations", "charity", "alms", "dana",
                "pinketa", "pin keta", "seettuwa", "seettu", "chitty", "contribution",
            ],
        ),
        (
            "Subscription",
            [
                "gemini advanced", "gemini sub", "gemini", "chatgpt plus", "chatgpt sub",
                "chatgpt", "chat gpt", "openai", "claude pro", "claude sub", "claude",
                "anthropic", "github copilot", "copilot", "cursor pro", "cursor sub",
                "cursor", "midjourney", "perplexity", "aws", "amazon web services",
                "azure", "google cloud", "gcp", "digitalocean", "digital ocean",
                "vercel", "heroku", "render", "github", "cloudflare", "domain renewal",
                "domain", "web hosting", "hosting", "api credits", "spotify premium",
                "spotify sub", "spotify", "netflix sub", "netflix", "youtube premium",
                "youtube sub", "youtube", "amazon prime", "prime video", "prime sub",
                "prime", "apple music", "apple tv", "apple sub", "apple one", "disney", "disney+",
                "hulu", "deezer", "soundcloud", "google one", "google drive",
                "icloud storage", "icloud", "dropbox", "onedrive", "microsoft 365",
                "office 365", "notion plus", "notion sub", "notion", "canva pro",
                "canva", "adobe creative cloud", "adobe sub", "adobe", "figma pro",
                "figma sub", "figma", "patreon", "medium subscription", "substack",
                "linkedin premium", "twitter blue", "x premium", "nordvpn", "expressvpn",
                "surfshark", "vpn sub", "vpn", "subscription", "subscriptions",
                "subscribed", "monthly sub", "yearly sub", "annual sub", "sub fee",
            ],
        ),
        (
            "Medicine",
            [
                "pharmacy bill", "meet doctor", "doctor fee", "doctor", "medicine", "medicines",
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
                "celebration", "treat", "trip", "club", "concert",
                "game", "gaming", "movie", "cinema", "gathering",
            ],
        ),
        (
            "Drink",
            [
                # Multi-word drink actions & phrases (longest matched first)
                "drink milk", "drink coffee", "drink coffiee", "drink tea",
                "drink juice", "drink water", "drink soda", "drink beer",
                "drink wine", "drank milk", "drank coffee", "drank coffiee",
                "drank tea", "drank juice", "drank water", "drinking milk",
                "drinking coffee", "drinking tea", "drinking water",
                "cool drink", "soft drink", "energy drink", "water bottle",
                "mineral water", "drinking water", "fruit juice", "fresh juice",
                "lime juice", "orange juice", "apple juice", "mango juice",
                "iced coffee", "ice coffee", "cold coffee", "milk shake",
                "milkshake", "hot chocolate", "green tea", "black tea",
                "ginger tea", "milk tea", "plain tea", "faluda", "bubble tea",
                "boba tea", "boba",
                # Action & beverage keywords
                "drink", "drinks", "drank", "drinking", "beverage", "beverages",
                "coffee", "coffiee", "tea", "juice", "smoothie",
                "soda", "coke", "pepsi", "fanta", "sprite", "milo", "nescafe",
                "beer", "wine", "liquor",
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
                "bus ticket", "train ticket", "ticket", "tickets",
                "tuk tuk", "three wheeler", "threewheeler", "threewheel",
                "bus", "train", "pickme", "uber", "petrol", "fuel", "bike",
                "taxi", "tuk", "van", "highway", "diesel", "parking",
                "expressway","petral","metro bus"
            ],
        ),
        (
            "Food",
            [
                "short eats", "ice cream",
                "lunch", "dinner", "breakfast", "food", "restaurant",
                "snack", "snacks", "kottu", "rice",
                "curry", "hoppers", "bakery", "cafe", "bites",
                "pizza", "burger", "dessert", "milk", "banana", "bananas",
                "bread", "fruits", "fruit", "vegetables", "egg", "eggs",
                "groceries", "grocery", "cheese", "butter", "biscuit",
                "biscuits", "meat", "fish", "chicken", "sugar", "dhal",
                "curd", "yoghurt",
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
                "camera", "lens", "phone", "mobile", "laptop", "tablet", "mouse", "keyboard",
                "headphones", "headphone", "earphones", "earphone", "airpods",
                "earbuds", "charger", "cable", "power bank", "pendrive", "monitor",
                "tripod", "mic", "microphone", "speaker", "speakers", "tv",
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
                short_tag = clean_short_subcategory(category, kw, title)
                return category, short_tag

    return "Other", None


def clean_short_subcategory(category: str, raw_tag: str | None, title: str) -> str | None:
    """Normalize subcategory tags into clean, short names (e.g., bus ticket -> bus)."""
    text = f"{title} {raw_tag or ''}".lower()

    # Transport
    if "bus" in text:
        return "bus"
    if "train" in text:
        return "train"
    if "petrol" in text or "fuel" in text or "petral" in text:
        return "petrol"
    if "diesel" in text:
        return "diesel"
    if "taxi" in text or "pickme" in text or "uber" in text:
        return "taxi"
    if "tuk" in text or "three wheeler" in text or "threewheel" in text:
        return "tuk tuk"
    if "highway" in text or "expressway" in text or "toll" in text:
        return "highway"
    if "ticket" in text and category == "Transport":
        return "ticket"

    # Drink
    if category == "Drink":
        drink_pattern = r"^(?:drink|drinks|drank|drinking)\s+(?:a\s+|an\s+|the\s+)?(.+)$"
        m = re.match(drink_pattern, title.strip(), re.IGNORECASE)
        if m:
            extracted_item = m.group(1).strip().lower()
            for kw in [
                "coffee", "coffiee", "tea", "milk", "juice", "water",
                "beer", "wine", "liquor", "soda", "coke", "pepsi", "fanta", "sprite",
                "milo", "nescafe", "smoothie", "shake", "faluda", "boba"
            ]:
                if kw in extracted_item:
                    if kw == "coffiee":
                        return "coffee"
                    if kw in {"coke", "pepsi", "fanta", "sprite"}:
                        return "soda"
                    if kw == "nescafe":
                        return "coffee"
                    if kw == "shake":
                        return "smoothie"
                    return kw
            return extracted_item

        for kw in [
            "coffee", "coffiee", "tea", "milk", "juice", "water",
            "beer", "wine", "liquor", "soda", "coke", "pepsi", "fanta", "sprite",
            "milo", "nescafe", "smoothie", "shake", "faluda", "boba",
            "cool drink", "soft drink", "energy drink"
        ]:
            if kw in text:
                if kw == "coffiee":
                    return "coffee"
                if kw in {"coke", "pepsi", "fanta", "sprite"}:
                    return "soda"
                if kw == "nescafe":
                    return "coffee"
                if kw == "shake":
                    return "smoothie"
                return kw

        if raw_tag and raw_tag.lower() not in {"drink", "drinks", "drank", "drinking"}:
            return raw_tag.lower()
        return "drink"

    # Food
    if "milk" in text:
        return "milk"
    if "banana" in text:
        return "banana"
    if "bread" in text:
        return "bread"
    if "egg" in text:
        return "eggs"
    if "rice" in text:
        return "rice"
    if "chicken" in text or "meat" in text:
        return "chicken"
    if "fish" in text:
        return "fish"
    if "biscuit" in text:
        return "biscuits"
    if "coffee" in text:
        return "coffee"
    if "tea" in text:
        return "tea"
    if "snack" in text or "short eats" in text:
        return "snacks"
    if "lunch" in text:
        return "lunch"
    if "dinner" in text:
        return "dinner"
    if "breakfast" in text:
        return "breakfast"
    if "fruit" in text:
        return "fruits"
    if "vege" in text or "vegetable" in text:
        return "vegetables"

    # Medicine
    if "panadol" in text or "paracetamol" in text:
        return "panadol"
    if "doctor" in text or "channel" in text:
        return "doctor"
    if "pharmacy" in text or "medicine" in text or "tablet" in text or "pill" in text:
        return "medicine"
    if "hospital" in text or "clinic" in text:
        return "hospital"

    # Utilities
    if "electricity" in text or "current bill" in text:
        return "electricity"
    if "water" in text:
        return "water bill"
    if "reload" in text or "recharge" in text:
        return "reload"
    if "wifi" in text or "internet" in text:
        return "internet"

    # Buy
    if category == "Buy":
        # Extract item from "buy camera", "buy new lens", "bought a phone", "order watch"
        buy_pattern = r"^(?:buy|bought|purchase|purchased|order|ordered)\s+(?:a\s+|an\s+|new\s+|the\s+)?(.+)$"
        m = re.match(buy_pattern, title.strip(), re.IGNORECASE)
        if m:
            extracted_item = m.group(1).strip().lower()
            for kw in [
                "camera", "lens", "phone", "mobile", "laptop", "tablet", "mouse", "keyboard",
                "headphones", "earphones", "airpods", "earbuds", "charger", "cable",
                "power bank", "tripod", "mic", "microphone", "speaker", "speakers", "monitor",
                "shirt", "pants", "trousers", "jeans", "shoes", "slippers", "sandals",
                "bag", "backpack", "watch", "perfume", "wallet", "sunglasses", "glasses",
                "book", "stationery", "pen", "notebook"
            ]:
                if kw in extracted_item:
                    if kw in {"mobile", "phone"}:
                        return "phone"
                    if kw in {"trousers", "jeans", "pants"}:
                        return "pants"
                    if kw in {"slippers", "sandals", "shoes"}:
                        return "shoes"
                    if kw in {"earphones", "airpods", "earbuds", "headphones"}:
                        return "headphones"
                    return kw
            return extracted_item

        for kw in [
            "camera", "lens", "phone", "mobile", "laptop", "tablet", "mouse", "keyboard",
            "headphones", "earphones", "airpods", "earbuds", "charger", "cable",
            "power bank", "tripod", "mic", "microphone", "speaker", "speakers", "monitor",
            "shirt", "pants", "trousers", "jeans", "shoes", "slippers", "sandals",
            "bag", "backpack", "watch", "perfume", "wallet", "sunglasses", "glasses",
            "book", "stationery", "pen", "notebook"
        ]:
            if kw in text:
                if kw in {"mobile", "phone"}:
                    return "phone"
                if kw in {"trousers", "jeans", "pants"}:
                    return "pants"
                if kw in {"slippers", "sandals", "shoes"}:
                    return "shoes"
                if kw in {"earphones", "airpods", "earbuds", "headphones"}:
                    return "headphones"
                return kw

        if raw_tag and raw_tag.lower() not in {"buy", "bought", "purchase", "purchased", "order", "ordered"}:
            return raw_tag.lower()
        return "item"

    # Rental
    if category == "Rental":
        rent_prefix_pattern = r"^(?:rent|rented|renting|rental|hire|hired|hiring|lease|leased)\s+(?:a\s+|an\s+|new\s+|the\s+)?(.+)$"
        m = re.match(rent_prefix_pattern, title.strip(), re.IGNORECASE)
        if m:
            extracted_item = m.group(1).strip().lower()
            for kw in [
                "lens", "scooter", "camera", "bike", "bicycle", "car", "van", "vehicle",
                "tripod", "light", "lights", "sound", "mic", "microphone", "dress", "suit",
                "costume", "room", "house", "hall", "equipment", "drone"
            ]:
                if kw in extracted_item:
                    if kw in {"bicycle", "bike"}:
                        return "bike"
                    if kw in {"lights", "light"}:
                        return "lights"
                    if kw in {"microphone", "mic"}:
                        return "mic"
                    return kw
            return extracted_item

        rent_suffix_pattern = r"^(.+?)\s+(?:rent|rental|rented|hire|lease)$"
        m_suff = re.match(rent_suffix_pattern, title.strip(), re.IGNORECASE)
        if m_suff:
            extracted_item = m_suff.group(1).strip().lower()
            for kw in [
                "lens", "scooter", "camera", "bike", "bicycle", "car", "van", "vehicle",
                "tripod", "light", "lights", "sound", "mic", "microphone", "dress", "suit",
                "costume", "room", "house", "hall", "equipment", "drone"
            ]:
                if kw in extracted_item:
                    if kw in {"bicycle", "bike"}:
                        return "bike"
                    if kw in {"lights", "light"}:
                        return "lights"
                    if kw in {"microphone", "mic"}:
                        return "mic"
                    return kw
            return extracted_item

        for kw in [
            "lens", "scooter", "camera", "bike", "car", "van", "vehicle",
            "drone", "tripod", "dress", "suit", "equipment"
        ]:
            if kw in text:
                return kw

        if raw_tag and raw_tag.lower() not in {"rent", "rental", "rented", "hire", "lease"}:
            return raw_tag.lower()
        return "rental"

    # Fitness
    if category == "Fitness":
        if "gym" in text:
            return "gym"
        if "workout" in text or "crossfit" in text:
            return "workout"
        if "yoga" in text:
            return "yoga"
        if "pilates" in text:
            return "pilates"
        if "swimming" in text:
            return "swimming"
        if "trainer" in text or "pt fee" in text:
            return "trainer"
        if "badminton" in text:
            return "badminton"
        if "futsal" in text:
            return "futsal"
        if "tennis" in text:
            return "tennis"
        if any(k in text for k in ("protein", "whey", "creatine", "supplement")):
            return "supplements"
        if raw_tag and raw_tag.lower() not in {"fitness", "sports"}:
            return raw_tag.lower()
        return "fitness"

    # Fund
    if category == "Fund":
        if "batch" in text:
            return "batch fund"
        if "class" in text:
            return "class fund"
        if "welfare" in text:
            return "welfare fund"
        if "society" in text:
            return "society fund"
        if "club" in text:
            return "club fund"
        if "office" in text:
            return "office fund"
        if "charity" in text:
            return "charity"
        if "donation" in text or "donate" in text or "dana" in text or "alms" in text or "pinketa" in text:
            return "donation"
        if "seettu" in text or "chitty" in text:
            return "seettu"
        if raw_tag and raw_tag.lower() not in {"fund", "funds"}:
            return raw_tag.lower()
        return "fund"

    # Subscription
    if category == "Subscription":
        if "aws" in text or "amazon web" in text:
            return "aws"
        if "gemini" in text:
            return "gemini"
        if "chatgpt" in text or "chat gpt" in text or "openai" in text:
            return "chatgpt"
        if "claude" in text or "anthropic" in text:
            return "claude"
        if "copilot" in text or "github" in text:
            return "github"
        if "cursor" in text:
            return "cursor"
        if "midjourney" in text:
            return "midjourney"
        if "perplexity" in text:
            return "perplexity"
        if "spotify" in text:
            return "spotify"
        if "netflix" in text:
            return "netflix"
        if "youtube" in text:
            return "youtube"
        if "prime" in text:
            return "prime"
        if "icloud" in text or "apple" in text:
            return "icloud"
        if "google" in text:
            return "google"
        if "adobe" in text:
            return "adobe"
        if "canva" in text:
            return "canva"
        if "figma" in text:
            return "figma"
        if "notion" in text:
            return "notion"
        if "dropbox" in text:
            return "dropbox"
        if "vpn" in text:
            return "vpn"
        if "hosting" in text or "domain" in text:
            return "hosting"
        if raw_tag and raw_tag.lower() not in {"sub", "subscription", "subscriptions"}:
            return raw_tag.lower()
        return "subscription"

    # Enjoy / Bodim / Loan
    if "party" in text:
        return "party"
    if "bday" in text or "birthday" in text:
        return "birthday"
    if "bodim" in text or "boarding" in text or "hostel" in text:
        return "bodim fee"
    if "loan" in text:
        return "loan"

    return raw_tag


def parse_receipt_date(raw_candidate: str | None = None, date_candidate: str | None = None) -> str:
    """
    Robust date parser for Sri Lankan receipts, bus tickets, bills, and POS slips.
    Prioritizes raw receipt text parsed with Day-Month-Year conventions.
    Rejects future dates (e.g. pharmacy medicine expiry dates).
    Guarantees returning a valid ISO YYYY-MM-DD string.
    """
    today = date.today()
    max_allowed = today + timedelta(days=1)  # Buffer for timezones

    sri_lankan_day_first_formats = [
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%d.%m.%Y",
        "%d/%m/%y",
        "%d-%m-%y",
        "%d.%m.%y",
        "%d/%b/%Y",
        "%d-%b-%Y",
        "%d %b %Y",
        "%d/%b/%y",
        "%d-%b-%y",
        "%d %b %y",
        "%d/%B/%Y",
        "%d-%B-%Y",
        "%d %B %Y",
        "%d/%B/%y",
        "%d-%B-%y",
        "%d %B %y",
        "%d.%b.%Y",
        "%d.%b.%y",
    ]

    iso_and_other_formats = [
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%Y.%m.%d",
        "%b %d, %Y",
        "%B %d, %Y",
        "%b %d %Y",
        "%B %d %Y",
        "%y/%m/%d",
        "%y-%m-%d",
        "%y.%m.%d",
    ]

    all_formats = sri_lankan_day_first_formats + iso_and_other_formats

    candidates = [c for c in [raw_candidate, date_candidate] if c and isinstance(c, str)]

    for cand in candidates:
        s = cand.strip()
        if not s or s.lower() in {"null", "none"}:
            continue

        # 1. Match full date patterns (e.g., '12/10/26', '12-OCT-2026', '13.10.2026')
        match = re.search(
            r"(\d{1,4}[-/\.]\d{1,2}[-/\.]\d{1,4}|\d{1,2}[-/\s][A-Za-z]{3,9}[-/\s]\d{2,4})",
            s,
        )
        date_str = match.group(1).strip() if match else None

        # 2. Check for Day/Month only (common on small thermal bus slips, e.g. "12/10 14:22")
        if not date_str:
            dm_match = re.search(r"\b(\d{1,2}[-/\.]\d{1,2})\b", s)
            if dm_match:
                date_str = f"{dm_match.group(1)}/{today.year}"

        if not date_str:
            date_str = s.split()[0].strip()

        for fmt in all_formats:
            try:
                dt = datetime.strptime(date_str, fmt)
                if dt.year < 100:
                    dt = dt.replace(year=dt.year + 2000)

                parsed_date = dt.date()

                # Safety check: Expenses cannot be in the future (avoids pharmacy medicine expiry dates like 2028-05-01)
                if parsed_date > max_allowed:
                    logger.warning("Ignoring future date candidate (likely expiry date): %s", parsed_date)
                    continue

                # Don't accept unreasonably old dates
                if parsed_date.year < 2020:
                    continue

                return parsed_date.isoformat()
            except ValueError:
                pass

    return today.isoformat()


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
        "📸 Receipt & Ticket Scanning:\n"
        "• Just send a photo of any supermarket receipt, bus ticket, or pharmacy bill!\n"
        "• Items and amounts are automatically extracted and categorized.\n\n"
        "🎯 Events & Trips:\n"
        "• start trip to Kandy (or start trip Galle)\n"
        "• start campus (or start go to campus)\n"
        "• start event Birthday Party\n"
        "• active event (check active event)\n"
        "• end event (finish & deactivate active event)\n\n"
        "💵 Record Expenses via Text:\n"
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
        "📸 Receipt & Bill Scanner:\n"
        "• Send a photo of any receipt, bus/train ticket, or bill.\n"
        "• Automatically extracts items (e.g., milk -> Food (milk), ticket -> Transport (bus), panadol -> Medicine (panadol)).\n\n"
        "🌴 Trips & Events:\n"
        "• start trip to <destination>\n"
        "• start campus\n"
        "• start event <event name>\n"
        "• active trip / active event\n"
        "• end trip / end event\n\n"
        "💸 Text Expenses (description amount):\n"
        "• bus 1000\n"
        "• lunch 800\n"
        "• drink coffee 250\n"
        "• bodim fee 15000\n"
        "• electricity 4500\n"
        "• buy shirt 2500\n"
        "• buy phone 40000\n"
        "• rent lens 2000\n"
        "• rent scooter 3500\n"
        "• gym fee 3500\n"
        "• batch fund 1000\n"
        "• aws 4500\n"
        "• gemini 6000\n"
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


async def handle_receipt_photo(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    user = update.effective_user
    message = update.effective_message

    # Only accept messages from the allowed Telegram account.
    if user is None or user.id != ALLOWED_USER_ID:
        await message.reply_text("Sorry, you are not authorized.")
        return

    if not ai_client:
        await message.reply_text(
            "⚠️ Scanning service is currently not available. Please check server settings."
        )
        return

    status_msg = await message.reply_text("🔍 Scanning document, please wait...")

    try:
        mime_type = "image/jpeg"
        if message.photo:
            photo_file = await message.photo[-1].get_file()
        elif message.document and message.document.mime_type and message.document.mime_type.startswith("image/"):
            photo_file = await message.document.get_file()
            mime_type = message.document.mime_type
        else:
            await status_msg.edit_text("Please send an image or photo of the receipt/bill.")
            return

        image_bytes = await photo_file.download_as_bytearray()

        today_iso = date.today().isoformat()
        current_year = date.today().year

        prompt_instruction = (
            f"You are an expert expense and receipt parser for Sri Lanka (currency: LKR). Today is {today_iso}.\n"
            "Analyze this supermarket receipt, bus ticket, train ticket, pharmacy bill, fuel slip, or utility bill image.\n"
            "Return ONLY a valid JSON object matching this schema:\n"
            "{\n"
            '  "merchant": string or null (name of the store, supermarket, bus company, pharmacy, clinic, or provider),\n'
            '  "date": "YYYY-MM-DD" or null (accurately extracted transaction date in ISO YYYY-MM-DD format),\n'
            '  "raw_date": string or null (the EXACT date/time characters printed on the receipt/ticket, e.g. "12/10/26 14:22", "12-OCT-2026", "13.10.2026", "දිනය: 12/10/26"),\n'
            '  "receipt_total": number or null (total amount),\n'
            '  "items": [\n'
            "    {\n"
            '      "name": string (item, ticket, or service description),\n'
            '      "amount": number (positive line total for this item, not unit price),\n'
            '      "category": string (MUST be one of: "Food", "Drink", "Transport", "Medicine", "Buy", "Rental", "Fitness", "Fund", "Subscription", "Utilities", "Enjoy", "Bodim Fee", "Other"),\n'
            '      "subcategory": string or null (MUST be a short name keyword tag, e.g. "bus", "train", "milk", "coffee", "tea", "banana", "bread", "medicine", "panadol", "petrol", "shirt", "camera", "lens", "phone", "scooter", "gym", "aws", "gemini", "batch fund", "electricity", "reload", "doctor", etc.)\n'
            "    }\n"
            "  ]\n"
            "}\n\n"
            "CRITICAL DATE RECOGNITION RULES (TOP PRIORITY):\n"
            "- Scan the ENTIRE document carefully for the transaction/issue date.\n"
            "- Look in all typical locations:\n"
            "  * BUS TICKETS: Top header line, next to bus route/trip/serial number, above or below fare, or next to 'Date:', 'DATE', 'D:', 'DT:', 'දිනය' (Sinhala for Date), or 'திகதி' (Tamil for Date).\n"
            "  * PHARMACY BILLS: The top invoice header next to Bill Date/Date. IMPORTANT: DO NOT mistake medicine batch expiry dates (EXP, BB, B.NO, EXP.DT) for the receipt date!\n"
            "  * SUPERMARKET & POS RECEIPTS: Top header under store name or bottom footer next to cashier/time stamp.\n"
            "  * TRAIN TICKETS: Printed date or stamped ink on the front/back.\n"
            "  * FUEL SLIPS: Header next to pump/nozzle or 'DATE:'.\n"
            "- REGIONAL DATE CONVENTION: In Sri Lanka, dates are ALWAYS in Day-Month-Year order (DD/MM/YYYY, DD-MM-YYYY, DD.MM.YYYY, DD/MM/YY, DD-MM-YY, DD.MM.YY, or DD-Mon-YYYY).\n"
            f"- Two-digit years like '26' mean {current_year} (e.g. '12/10/26' -> '2026-10-12', '13.10.26' -> '2026-10-13', '05/10/26' -> '2026-10-05'). Day is first!\n"
            f"- If year is omitted (e.g. '12/10 14:22'), assume year is {current_year}.\n"
            "- DO NOT guess or default to today's date if a printed date exists on the document! Extract the actual printed date.\n"
            "- Always place the exact text as seen on the receipt in 'raw_date' and the converted ISO format in 'date'.\n\n"
            "Categorization rules:\n"
            '- "Food": Supermarket food and groceries (banana, bread, vegetables, fruits, biscuits, rice, chicken), restaurant meals, snacks.\n'
            '- "Drink": Water, coffee, tea, fruit juices, milk drinks, soft drinks, energy drinks, soda, beverages.\n'
            '- "Transport": Bus tickets, train tickets, taxi, PickMe, Uber, petrol, fuel, parking, highway expressway toll.\n'
            '- "Medicine": Pharmacy bills, medicines, panadol, tablets, pills, clinic/hospital, doctor channeling.\n'
            '- "Buy": Clothing (shirt, pants, dress), shoes, electronics & accessories (phone, camera, lens, laptop, charger, headphones), stationery, books, household items.\n'
            '- "Rental": Item/equipment/vehicle rentals (rent lens, rent camera, rent scooter, rent bike, car hire, equipment rental).\n'
            '- "Fitness": Gym membership, gym fees, fitness workout, yoga, swimming, badminton, sports, protein supplements.\n'
            '- "Fund": Welfare fund, batch fund, class fund, department fund, society/club fund, donations, charity, seettu.\n'
            '- "Subscription": Digital/cloud subscriptions (AWS, Gemini, ChatGPT, Claude, GitHub, Spotify, Netflix, YouTube Premium, iCloud, Adobe).\n'
            '- "Utilities": Electricity bill, water bill, phone reload, mobile packages, internet/wifi (Dialog, Mobitel, SLT).\n'
            '- "Enjoy": Parties, movies, outings, club, entertainment.\n'
            '- "Bodim Fee": Room rent, boarding fee, hostel rent.\n'
            '- "Other": Anything not fitting above.\n\n'
            "Guidelines:\n"
            "- For supermarket receipts with itemized lines, list each item in 'items'. Exclude subtotal and grand total from 'items'.\n"
            "- For single tickets (e.g. bus ticket) or simple bills, return 1 item with the full ticket price, category 'Transport', and subcategory 'bus'.\n"
            "- For 'subcategory', always provide a clean short word (e.g., for bus ticket -> 'bus', for fresh milk -> 'milk', for panadol -> 'panadol').\n"
            "- Do not guess unreadable values. Use null for unknown values. Amounts must be positive numbers. Assume LKR."
        )

        models_to_try = list(dict.fromkeys([GEMINI_MODEL, "gemini-flash-latest", "gemini-3.5-flash"]))
        response = None
        last_error = None

        for model_name in models_to_try:
            for attempt in range(2):
                try:
                    # Guard with 25-second timeout so a single request never hangs indefinitely
                    response = await asyncio.wait_for(
                        asyncio.to_thread(
                            ai_client.models.generate_content,
                            model=model_name,
                            contents=[
                                prompt_instruction,
                                types.Part.from_bytes(
                                    data=bytes(image_bytes),
                                    mime_type=mime_type,
                                ),
                            ],
                            config=types.GenerateContentConfig(
                                response_mime_type="application/json",
                                temperature=0,
                            ),
                        ),
                        timeout=25.0,
                    )
                    if response and response.text:
                        break
                except asyncio.TimeoutError:
                    logger.warning("Model %s timed out after 25s. Trying next...", model_name)
                    break
                except Exception as exc:
                    last_error = exc
                    err_msg = str(exc)
                    if "503" in err_msg or "UNAVAILABLE" in err_msg or "high demand" in err_msg.lower():
                        logger.warning(
                            "Model %s busy (503). Retrying after brief pause... (attempt %d/2)",
                            model_name, attempt + 1
                        )
                        await asyncio.sleep(1.5)
                        continue
                    else:
                        logger.warning("Model %s failed: %s", model_name, exc)
                        break

            if response and response.text:
                break

        if not response or not response.text:
            logger.error("All document scanning models failed: %s", last_error)
            await status_msg.edit_text(
                "⚠️ The document scanner is temporarily busy. "
                "Please try again in a few moments, or enter your expense as text (e.g. 'bus 600')."
            )
            return

        content = response.text

        receipt = json.loads(content)

        items = receipt.get("items") or []
        merchant = receipt.get("merchant")
        raw_date_val = receipt.get("raw_date")
        date_val = receipt.get("date")

        # Parse date with multi-format fallback to guarantee exact ISO YYYY-MM-DD
        final_expense_date = parse_receipt_date(raw_candidate=raw_date_val, date_candidate=date_val)

        # Fallback if items list is empty but receipt_total is found (e.g. single ticket)
        if not items and receipt.get("receipt_total"):
            ticket_desc = merchant or "Ticket / Bill"
            is_bus = "bus" in ticket_desc.lower()
            is_train = "train" in ticket_desc.lower()
            items = [{
                "name": ticket_desc,
                "amount": float(receipt["receipt_total"]),
                "category": "Transport" if (is_bus or is_train) else "Other",
                "subcategory": "bus" if is_bus else ("train" if is_train else None),
            }]

        if not items:
            await status_msg.edit_text(
                "⚠️ Could not detect any items or amounts on this receipt.\n"
                "Please make sure the photo is clear and well-lit, or send text manually."
            )
            return

        saved_items = []
        failed_count = 0
        active_event_name = None

        async with httpx.AsyncClient(timeout=30) as client:
            for it in items:
                raw_name = (it.get("name") or "Item").strip()
                try:
                    amount = float(it.get("amount", 0))
                except (ValueError, TypeError):
                    continue

                if amount <= 0:
                    continue

                # Refine category using our local rules if matched
                local_cat, local_sub = detect_category_and_keyword(raw_name)
                if local_cat != "Other":
                    category = local_cat
                    raw_sub = local_sub or it.get("subcategory")
                else:
                    gemini_cat = it.get("category")
                    valid_cats = {
                        "Bodim Fee", "Medicine", "Loan", "Enjoy", "Utilities",
                        "Transport", "Food", "Drink", "Buy", "Rental", "Fitness", "Fund", "Subscription"
                    }
                    category = gemini_cat if gemini_cat in valid_cats else "Other"
                    raw_sub = it.get("subcategory")

                # Normalize subcategory to clean short tag (e.g. bus ticket -> bus)
                subcategory = clean_short_subcategory(category, raw_sub, raw_name)

                payload = {
                    "title": raw_name,
                    "amount": amount,
                    "category": category,
                    "subcategory": subcategory,
                    "merchant": merchant,
                    "expense_date": final_expense_date,
                    "source": "receipt",
                }

                try:
                    res = await client.post(f"{API_BASE_URL}/expenses", json=payload)
                    res.raise_for_status()
                    saved_data = res.json()
                    exp_obj = saved_data.get("expense", saved_data)
                    ev_name = exp_obj.get("event_name")
                    if ev_name and not active_event_name:
                        active_event_name = ev_name
                    elif exp_obj.get("event_id") and not active_event_name:
                        active_event_name = f"Event #{exp_obj.get('event_id')}"
                    saved_items.append({
                        "name": raw_name,
                        "amount": amount,
                        "category": category,
                        "subcategory": subcategory,
                    })
                except Exception as exc:
                    logger.exception("Error saving receipt item '%s': %s", raw_name, exc)
                    failed_count += 1

        if not saved_items:
            await status_msg.edit_text("⚠️ Failed to save extracted items to database. Check server logs.")
            return

        total_spent = sum(item["amount"] for item in saved_items)
        reply_lines = [
            "🧾 Receipt processed successfully!\n",
        ]
        if merchant:
            reply_lines.append(f"🏪 Merchant: {merchant}")
        reply_lines.append(f"📅 Date: {final_expense_date}")
        reply_lines.append("")

        for idx, item in enumerate(saved_items, 1):
            tag_str = f" ({item['subcategory']})" if item["subcategory"] else ""
            reply_lines.append(
                f"{idx}. {item['name']}\n"
                f"   • Amount: LKR {item['amount']:,.2f}\n"
                f"   • Category: {item['category']}{tag_str}\n"
            )

        reply_lines.append(f"\n💰 Total: LKR {total_spent:,.2f}")
        if active_event_name:
            reply_lines.append(f"Linked Event: {active_event_name}")
        if failed_count > 0:
            reply_lines.append(f"\n⚠️ {failed_count} item(s) could not be saved.")

        await status_msg.edit_text("\n".join(reply_lines))


    except Exception as exc:
        logger.exception("Error processing receipt photo: %s", exc)
        try:
            await status_msg.edit_text(
                "❌ Could not process this document right now. "
                "Please try again in a moment, or send your expense as text (e.g., 'lunch 600')."
            )
        except Exception:
            pass


async def global_error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Global fallback error handler: prevents unhandled errors from breaking the bot."""
    logger.error("Unhandled error in telegram bot: %s", context.error, exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text(
                "⚠️ Something went wrong processing your request. Please try again or send your expense as text."
            )
        except Exception:
            pass


def main():
    # concurrent_updates=True allows Telegram to process multiple messages, photos, and commands simultaneously
    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .concurrent_updates(True)
        .build()
    )

    # Register global error handler so unexpected errors never crash the bot
    application.add_error_handler(global_error_handler)

    # block=False ensures long-running tasks (e.g., scanning) do not block incoming text expenses or commands
    application.add_handler(CommandHandler("start", start, block=False))
    application.add_handler(CommandHandler("help", help_command, block=False))
    application.add_handler(
        MessageHandler(
            filters.PHOTO,
            handle_receipt_photo,
            block=False,
        )
    )
    application.add_handler(
        MessageHandler(
            filters.Document.IMAGE,
            handle_receipt_photo,
            block=False,
        )
    )
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message,
            block=False,
        )
    )

    print("Telegram expense bot is running (concurrent updates enabled)...")
    application.run_polling()


if __name__ == "__main__":
    main()