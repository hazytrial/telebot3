import os
import logging
import requests
from flask import Flask, jsonify
from threading import Thread
from telegram import Update, InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import Application, CommandHandler, InlineQueryHandler, ContextTypes
from uuid import uuid4

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# API Configuration
INDIA_POSTAL_API = "https://api.postalpincode.in/pincode"

# Get token from environment variable (for Render deployment)
TELEGRAM_BOT_TOKEN = "7966712011:AAFVVWlxWaXSOaxuEtxkIY73LKXkvZyVSoQ"

# Flask app for health monitoring
app = Flask(__name__)

@app.route('/')
def home():
    """Home endpoint"""
    return jsonify({
        "status": "online",
        "bot": "Indian Postal Info Bot - Inline Mode",
        "version": "2.0.0"
    })

@app.route('/health')
def health():
    """Health check endpoint for UptimeRobot/BetterStack"""
    return jsonify({
        "status": "healthy",
        "service": "telegram_bot_inline"
    }), 200

@app.route('/ping')
def ping():
    """Simple ping endpoint"""
    return "pong", 200


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send welcome message"""
    welcome_message = """
We provide Indian Postal Info through this Bot!

dev: @CastedSpel 
"""
    await update.message.reply_text(welcome_message)
    logger.info(f"User {update.effective_user.id} started the bot")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send help message"""
    help_text = """
📝 Example: 
@HazyPostalinfoBot <pincode>

📋 Information Provided:
• Post Office Names
• Branch Types
• Delivery Status
• District & State
• Division & Region
• Circle Information

✨ Benefits:
• Use in any chat or group
• No need to switch to bot chat
• Instant search results
• Share info with friends easily
• Always up-to-date data

Enjoy! 🐥
"""
    await update.message.reply_text(help_text)
    logger.info(f"User {update.effective_user.id} requested help")


async def inline_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline queries"""
    query = update.inline_query.query.strip()
    
    # If query is empty, show instructions
    if not query:
        results = [
            InlineQueryResultArticle(
                id=str(uuid4()),
                title="🐥 Indian Postal Info Bot",
                description="Type a 6-digit PIN code to search",
                input_message_content=InputTextMessageContent(
                    message_text="🇮🇳 Indian Postal Info Bot\n\n"
                    "Type @yourbotusername <pincode> to search!\n"
                    "Example: @yourbotusername 110001"
                )
            ),
            InlineQueryResultArticle(
                id=str(uuid4()),
                title="📝 Example: 110001",
                description="Search New Delhi postal info",
                input_message_content=InputTextMessageContent(
                    message_text="Try typing: @yourbotusername 110001"
                )
            ),
            InlineQueryResultArticle(
                id=str(uuid4()),
                title="📝 Example: 400001",
                description="Search Mumbai postal info",
                input_message_content=InputTextMessageContent(
                    message_text="Try typing: @yourbotusername 400001"
                )
            )
        ]
        await update.inline_query.answer(results, cache_time=30)
        return

    # Validate PIN code format
    pincode = query.replace(" ", "")
    
    if not pincode.isdigit():
        results = [
            InlineQueryResultArticle(
                id=str(uuid4()),
                title="❌ Invalid Input",
                description="PIN code must contain only numbers",
                input_message_content=InputTextMessageContent(
                    message_text="❌ Invalid PIN code!\n\nPlease enter only numbers (6 digits)."
                )
            )
        ]
        await update.inline_query.answer(results, cache_time=10)
        return
    
    if len(pincode) != 6:
        results = [
            InlineQueryResultArticle(
                id=str(uuid4()),
                title=f"⏳ Keep typing... ({len(pincode)}/6)",
                description="PIN code must be exactly 6 digits",
                input_message_content=InputTextMessageContent(
                    message_text=f"⏳ Incomplete PIN code: {pincode}\n\nPlease enter all 6 digits."
                )
            )
        ]
        await update.inline_query.answer(results, cache_time=10)
        return

    logger.info(f"Inline query for PIN code: {pincode}")

    try:
        # Fetch postal data
        url = f"{INDIA_POSTAL_API}/{pincode}"
        response = requests.get(url, timeout=10)

        if response.status_code == 200:
            data = response.json()
            
            if data[0]["Status"] == "Success":
                post_offices = data[0]["PostOffice"]
                results = []
                
                # Create summary result
                summary_text = f"📮 PIN Code: {pincode}\n"
                summary_text += f"📍 Total Post Offices: {len(post_offices)}\n"
                summary_text += f"{'='*35}\n\n"
                
                for i, po in enumerate(post_offices[:8], 1):
                    summary_text += f"🏤 {i}. {po.get('Name', 'N/A')}\n"
                    summary_text += f"   📌 Type: {po.get('BranchType', 'N/A')}\n"
                    summary_text += f"   📦 Delivery: {po.get('DeliveryStatus', 'N/A')}\n"
                    summary_text += f"   🏙️ District: {po.get('District', 'N/A')}\n"
                    summary_text += f"   🗺️ State: {po.get('State', 'N/A')}\n"
                    summary_text += f"   📮 Division: {po.get('Division', 'N/A')}\n"
                    summary_text += f"   🌐 Region: {po.get('Region', 'N/A')}\n\n"
                
                if len(post_offices) > 8:
                    summary_text += f"... and {len(post_offices) - 8} more\n\n"
                
                summary_text += "✅ Data from Indian Postal Service"
                
                # Add summary result
                first_po = post_offices[0]
                results.append(
                    InlineQueryResultArticle(
                        id=str(uuid4()),
                        title=f"📮 {pincode} - {first_po.get('District', 'N/A')}",
                        description=f"{len(post_offices)} post offices in {first_po.get('State', 'N/A')}",
                        input_message_content=InputTextMessageContent(
                            message_text=summary_text
                        )
                    )
                )
                
                # Add individual post office results (up to 9 more)
                for po in post_offices[:9]:
                    detail_text = f"📮 PIN Code: {pincode}\n\n"
                    detail_text += f"🏤 Post Office: {po.get('Name', 'N/A')}\n"
                    detail_text += f"📌 Type: {po.get('BranchType', 'N/A')}\n"
                    detail_text += f"📦 Delivery: {po.get('DeliveryStatus', 'N/A')}\n"
                    detail_text += f"🏙️ District: {po.get('District', 'N/A')}\n"
                    detail_text += f"🗺️ State: {po.get('State', 'N/A')}\n"
                    detail_text += f"📮 Division: {po.get('Division', 'N/A')}\n"
                    detail_text += f"🌐 Region: {po.get('Region', 'N/A')}\n"
                    
                    if po.get('Circle'):
                        detail_text += f"⭕ Circle: {po.get('Circle')}\n"
                    
                    detail_text += f"\n✅ Indian Postal Service"
                    
                    results.append(
                        InlineQueryResultArticle(
                            id=str(uuid4()),
                            title=f"🏤 {po.get('Name', 'N/A')}",
                            description=f"{po.get('BranchType', 'N/A')} - {po.get('District', 'N/A')}",
                            input_message_content=InputTextMessageContent(
                                message_text=detail_text
                            )
                        )
                    )
                
                await update.inline_query.answer(results, cache_time=300)
                logger.info(f"Returned {len(results)} results for PIN: {pincode}")
                
            else:
                # PIN code not found
                results = [
                    InlineQueryResultArticle(
                        id=str(uuid4()),
                        title=f"❌ PIN Code {pincode} Not Found",
                        description="Please verify the PIN code is correct",
                        input_message_content=InputTextMessageContent(
                            message_text=f"❌ PIN Code Not Found!\n\n"
                            f"PIN: {pincode}\n\n"
                            "Please verify:\n"
                            "• PIN code is correct\n"
                            "• It's a valid Indian PIN code\n\n"
                            "Try searching another PIN code."
                        )
                    )
                ]
                await update.inline_query.answer(results, cache_time=60)
                logger.warning(f"PIN code not found: {pincode}")
        else:
            # API error
            results = [
                InlineQueryResultArticle(
                    id=str(uuid4()),
                    title="❌ Service Unavailable",
                    description="Please try again in a moment",
                    input_message_content=InputTextMessageContent(
                        message_text="❌ Service temporarily unavailable.\n\nPlease try again in a moment."
                    )
                )
            ]
            await update.inline_query.answer(results, cache_time=10)
            logger.error(f"API error: {response.status_code}")

    except requests.exceptions.Timeout:
        results = [
            InlineQueryResultArticle(
                id=str(uuid4()),
                title="❌ Request Timeout",
                description="Server took too long to respond",
                input_message_content=InputTextMessageContent(
                    message_text="❌ Request timeout!\n\nPlease try again."
                )
            )
        ]
        await update.inline_query.answer(results, cache_time=10)
        logger.error(f"Timeout for PIN: {pincode}")
        
    except Exception as e:
        results = [
            InlineQueryResultArticle(
                id=str(uuid4()),
                title="❌ Error Occurred",
                description="Something went wrong",
                input_message_content=InputTextMessageContent(
                    message_text="❌ An error occurred!\n\nPlease try again later."
                )
            )
        ]
        await update.inline_query.answer(results, cache_time=10)
        logger.error(f"Error: {str(e)}")


def run_bot():
    """Run the Telegram bot"""
    try:
        # Create application
        application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

        # Register handlers
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("help", help_command))
        application.add_handler(InlineQueryHandler(inline_query))

        # Start the bot
        logger.info("🐥 Indian Postal Info Bot (Inline Mode) is starting...")
        application.run_polling(allowed_updates=Update.ALL_TYPES)
        
    except Exception as e:
        logger.error(f"Bot crashed: {str(e)}")
        raise


def run_flask():
    """Run Flask server for health monitoring"""
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)


if __name__ == "__main__":
    # Start Flask in a separate thread
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    logger.info("Flask health monitoring server started")
    
    # Run the bot in the main thread
    run_bot()
