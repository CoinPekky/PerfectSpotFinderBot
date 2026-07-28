import json
import logging
import os
import re
from pathlib import Path

from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove, Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN environment variable is not set. "
        "Add it in Railway -> Variables before deploying."
    )

DATA_PATH = Path(__file__).parent / "data.json"
with open(DATA_PATH, "r", encoding="utf-8") as f:
    SPOTS_DB = json.load(f)

LOCATION, OCCASION = range(2)

OCCASION_KEYWORDS = {
    "date": ["date", "first date", "hangout", "casual"],
    "anniversary": ["anniversary", "anni"],
    "proposal": ["proposal", "propose", "engagement"],
    "birthday": ["birthday", "bday"],
    "casual": ["casual", "chill", "hangout"],
}


def normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", text.lower()).strip()


def match_occasion_tag(occasion_text: str) -> str:
    norm = normalize(occasion_text)
    for tag, keywords in OCCASION_KEYWORDS.items():
        for kw in keywords:
            if kw in norm:
                return tag
    return "date"  # sensible default


def find_location_spots(location_text: str):
    """
    Walks the nested data.json (country -> state -> lga/city -> [spots])
    and returns the best matching list of spots based on substring match.
    """
    norm_location = normalize(location_text)
    words = set(norm_location.split())

    best_match = None
    best_score = 0

    def walk(node, path):
        nonlocal best_match, best_score
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "default":
                    continue
                walk(value, path + [key])
        elif isinstance(node, list):
            place_key = " ".join(path)
            score = 0
            for p in path:
                if p in norm_location:
                    score += len(p)
            for w in words:
                if w and w in place_key:
                    score += 1
            if score > best_score:
                best_score = score
                best_match = node

    walk(SPOTS_DB, [])

    if best_match and best_score > 0:
        return best_match
    return SPOTS_DB.get("default", [])


def format_recommendations(spots, occasion_tag: str, location_text: str) -> str:
    filtered = [s for s in spots if occasion_tag in s.get("tags", [])]
    if not filtered:
        filtered = spots[:3]

    lines = [f"📍 Top picks near *{location_text.title()}* for a *{occasion_tag}*:\n"]
    for s in filtered[:3]:
        lines.append(
            f"🍽 *{s['name']}*\n"
            f"   Type: {s['type']}\n"
            f"   {s['description']}\n"
        )
    lines.append("Want another location? Just type /recommend to search again.")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "👋 Welcome to *SpotFinder NG*!\n\n"
        "I recommend the best dating spots and fancy restaurants near you.\n\n"
        "First, tell me your *location* (e.g. Lekki Lagos, Wuse Abuja, or your city/state).",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove(),
    )
    return LOCATION


async def recommend(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "📍 Sure — what's your location? (city, state, or LGA)",
        reply_markup=ReplyKeyboardRemove(),
    )
    return LOCATION


async def receive_location(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["location"] = update.message.text

    keyboard = [["First Date", "Anniversary"], ["Proposal", "Birthday"], ["Casual Hangout"]]
    await update.message.reply_text(
        "🎉 Got it! What's the *occasion*?",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True, resize_keyboard=True),
    )
    return OCCASION


async def receive_occasion(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    location_text = context.user_data.get("location", "")
    occasion_text = update.message.text

    occasion_tag = match_occasion_tag(occasion_text)
    spots = find_location_spots(location_text)
    reply = format_recommendations(spots, occasion_tag, location_text)

    await update.message.reply_text(
        reply, parse_mode="Markdown", reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await update.message.reply_text(
        "Okay, cancelled. Type /recommend anytime to start again.",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ConversationHandler.END


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Commands:\n"
        "/start - Begin\n"
        "/recommend - Get a new recommendation\n"
        "/cancel - Cancel current search"
    )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Update %s caused error %s", update, context.error)


# ---------------------------------------------------------------------------
# App entry point
# ---------------------------------------------------------------------------

def main() -> None:
    application = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("start", start),
            CommandHandler("recommend", recommend),
        ],
        states={
            LOCATION: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_location)],
            OCCASION: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_occasion)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )

    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("help", help_command))
    application.add_error_handler(error_handler)

    logger.info("Bot starting with polling...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
