import logging
import requests
import os
from flask import Flask, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from datetime import datetime
import asyncio

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuration
BOT_TOKEN = "7966712011:AAGv5WhZmW2-c87qwjAyZY6aVtczfuNf9jM"
PORT = int(os.environ.get('PORT', 10000))
WEBHOOK_URL = os.environ.get('RENDER_EXTERNAL_URL', '').rstrip('/')

# Initialize Flask app for health checks
app = Flask(__name__)

# Health check metrics
bot_start_time = datetime.now()
total_requests = 0
successful_lookups = 0
bot_initialized = False

@app.route('/')
def home():
    return jsonify({
        "status": "Bot is running",
        "service": "Telegram Postal Pincode Bot",
        "timestamp": datetime.now().isoformat(),
        "bot_initialized": bot_initialized
    })

@app.route('/health')
def health_check():
    """Health check endpoint for UptimeRobot and BetterStack"""
    global total_requests, successful_lookups, bot_initialized
    
    bot_status = "healthy" if bot_initialized else "initializing"
    
    # Check API availability
    try:
        test_response = requests.get("https://api.postalpincode.in/pincode/110001", timeout=5)
        api_status = "up" if test_response.status_code == 200 else "down"
    except Exception as e:
        logger.warning(f"API health check failed: {e}")
        api_status = "down"
    
    uptime = datetime.now() - bot_start_time
    
    health_data = {
        "status": bot_status,
        "timestamp": datetime.now().isoformat(),
        "uptime_seconds": int(uptime.total_seconds()),
        "uptime_human": str(uptime).split('.')[0],
        "total_requests": total_requests,
        "successful_lookups": successful_lookups,
        "api_status": api_status,
        "version": "1.0.0",
        "webhook_configured": bool(WEBHOOK_URL)
    }
    
    # Return 200 if bot is healthy, 503 if not
    status_code = 200 if bot_status == "healthy" and api_status == "up" else 503
    return jsonify(health_data), status_code

@app.route('/metrics')
def metrics():
    """Prometheus-style metrics endpoint"""
    global total_requests, successful_lookups
    
    uptime = datetime.now() - bot_start_time
    error_rate = round((1 - successful_lookups / total_requests) * 100, 2) if total_requests > 0 else 0
    
    metrics_text = f"""# HELP bot_uptime_seconds Bot uptime in seconds
# TYPE bot_uptime_seconds gauge
bot_uptime_seconds {int(uptime.total_seconds())}

# HELP bot_total_requests Total number of requests
# TYPE bot_total_requests counter
bot_total_requests {total_requests}

# HELP bot_successful_lookups Successful lookup requests
# TYPE bot_successful_lookups counter
bot_successful_lookups {successful_lookups}

# HELP bot_error_rate Error rate percentage
# TYPE bot_error_rate gauge
bot_error_rate {error_rate}
"""
    
    return metrics_text, 200, {'Content-Type': 'text/plain; charset=utf-8'}

@app.route('/ready')
def ready_check():
    """Kubernetes-style readiness check"""
    global bot_initialized
    if bot_initialized:
        return jsonify({"status": "ready", "bot": "operational"}), 200
    else:
        return jsonify({"status": "not_ready", "bot": "initializing"}), 503

@app.route('/ping')
def ping():
    """Simple ping endpoint for uptime monitoring"""
    return "pong", 200

# API Functions
async def get_pincode_info(pincode):
    """Fetch pincode information from API"""
    global total_requests, successful_lookups
    total_requests += 1
    
    try:
        response = requests.get(f"https://api.postalpincode.in/pincode/{pincode}", timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data and data[0]['Status'] == 'Success':
                successful_lookups += 1
                return data[0]['PostOffice']
        return None
    except Exception as e:
        logger.error(f"API Error for pincode {pincode}: {e}")
        return None

async def search_by_branch(branch_name):
    """Search pincodes by branch name"""
    global total_requests, successful_lookups
    total_requests += 1
    
    try:
        response = requests.get(f"https://api.postalpincode.in/postoffice/{branch_name}", timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data and data[0]['Status'] == 'Success':
                successful_lookups += 1
                return data[0]['PostOffice']
        return None
    except Exception as e:
        logger.error(f"API Error for branch {branch_name}: {e}")
        return None

# Bot Handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Main menu with inline buttons"""
    keyboard = [
        [InlineKeyboardButton("🔍 Lookup by Pincode", callback_data="lookup_pincode")],
        [InlineKeyboardButton("🏢 Search by Branch", callback_data="search_branch")],
        [InlineKeyboardButton("ℹ️ Help", callback_data="help")],
        [InlineKeyboardButton("📊 Bot Status", callback_data="bot_status")]
    ]
    
    welcome_text = """
🌐 *Postal Pincode Lookup Bot By @Castedspel*

*Quick Actions:*
• 🔍 Lookup by 6-digit Pincode
• 🏢 Search by Branch/Post Office name
*Choose an option below:* 👇
    """
    
    await update.message.reply_text(
        welcome_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all inline button callbacks"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    
    if data == "lookup_pincode":
        await query.edit_message_text(
            "🔢 *Enter 6-digit Pincode:*\n\nExample: `110001`",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Back", callback_data="main_menu")]
            ])
        )
        context.user_data['awaiting'] = 'pincode'
        
    elif data == "search_branch":
        await query.edit_message_text(
            "🏢 *Enter Branch Name:*\n\nExample: `Connaught Place`",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Back", callback_data="main_menu")]
            ])
        )
        context.user_data['awaiting'] = 'branch'
        
    elif data == "help":
        help_text = """
🤖 *How to Use*

*Pincode Lookup:*
1. Click 'Lookup by Pincode'
2. Enter 6-digit pincode
3. Get complete details

*Branch Search:*
1. Click 'Search by Branch'  
2. Enter post office name
3. Find matching branches

*Examples:*
• Pincode: `110001`, `400001`
• Branch: `Connaught Place`, `Fort`

        """
        await query.edit_message_text(
            help_text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("⬅️ Back", callback_data="main_menu")]
            ])
        )
    
    elif data == "bot_status":
        uptime = datetime.now() - bot_start_time
        status_text = f"""
📊 *Bot Status Report*

• ✅ **Status:** Operational
• 📍 **Coverage:** All India
        """
        await query.edit_message_text(
            status_text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Refresh", callback_data="bot_status")],
                [InlineKeyboardButton("⬅️ Main Menu", callback_data="main_menu")]
            ])
        )
        
    elif data == "main_menu":
        keyboard = [
            [InlineKeyboardButton("🔍 Lookup Pincode", callback_data="lookup_pincode")],
            [InlineKeyboardButton("🏢 Search Branch", callback_data="search_branch")],
            [InlineKeyboardButton("ℹ️ Help", callback_data="help")],
            [InlineKeyboardButton("📊 Bot Status", callback_data="bot_status")]
        ]
        await query.edit_message_text(
            "🌐 *Postal Pincode Lookup Bot*\n\nChoose an option: 👇",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle user text input"""
    user_input = update.message.text.strip()
    user_data = context.user_data
    
    if 'awaiting' not in user_data:
        await start(update, context)
        return
    
    input_type = user_data['awaiting']
    
    if input_type == 'pincode':
        if not user_input.isdigit() or len(user_input) != 6:
            await update.message.reply_text(
                "❌ *Invalid Pincode!*\nPlease enter a valid 6-digit pincode.",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Try Again", callback_data="lookup_pincode")],
                    [InlineKeyboardButton("⬅️ Main Menu", callback_data="main_menu")]
                ])
            )
            return
            
        await update.message.reply_text("🔍 *Searching...*", parse_mode='Markdown')
        
        post_offices = await get_pincode_info(user_input)
        
        if not post_offices:
            await update.message.reply_text(
                f"❌ *No results found for* `{user_input}`",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Try Another", callback_data="lookup_pincode")],
                    [InlineKeyboardButton("🏢 Branch Search", callback_data="search_branch")],
                    [InlineKeyboardButton("⬅️ Main Menu", callback_data="main_menu")]
                ])
            )
            return
        
        response_text = f"📍 *Pincode: {user_input}*\n\n"
        response_text += f"*Found {len(post_offices)} post office(s):*\n\n"
        
        for office in post_offices[:5]:
            response_text += f"🏢 *{office['Name']}*\n"
            response_text += f"• 📍 District: {office['District']}\n"
            response_text += f"• 🏛️ State: {office['State']}\n"
            response_text += f"• 🌍 Country: {office['Country']}\n"
            response_text += f"• 🏷️ Type: {office['BranchType']}\n\n"
        
        if len(post_offices) > 5:
            response_text += f"*... and {len(post_offices) - 5} more*"
        
        keyboard = [
            [InlineKeyboardButton("🔍 New Pincode", callback_data="lookup_pincode")],
            [InlineKeyboardButton("🏢 Branch Search", callback_data="search_branch")],
            [InlineKeyboardButton("⬅️ Main Menu", callback_data="main_menu")]
        ]
        
        await update.message.reply_text(
            response_text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
    elif input_type == 'branch':
        if len(user_input) < 3:
            await update.message.reply_text(
                "❌ Please enter at least 3 characters",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Try Again", callback_data="search_branch")],
                    [InlineKeyboardButton("⬅️ Main Menu", callback_data="main_menu")]
                ])
            )
            return
            
        await update.message.reply_text("🔍 *Searching branches...*", parse_mode='Markdown')
        
        branches = await search_by_branch(user_input)
        
        if not branches:
            await update.message.reply_text(
                f"❌ *No branches found for* \"{user_input}\"",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Try Another", callback_data="search_branch")],
                    [InlineKeyboardButton("🔍 Pincode Lookup", callback_data="lookup_pincode")],
                    [InlineKeyboardButton("⬅️ Main Menu", callback_data="main_menu")]
                ])
            )
            return
        
        response_text = f"🏢 *Branch Search: {user_input}*\n\n"
        response_text += f"*Found {len(branches)} branch(es):*\n\n"
        
        for branch in branches[:5]:
            response_text += f"📍 *{branch['Name']}*\n"
            response_text += f"• 📮 Pincode: `{branch['Pincode']}`\n"
            response_text += f"• 🏛️ District: {branch['District']}\n"
            response_text += f"• 🌍 State: {branch['State']}\n\n"
        
        if len(branches) > 5:
            response_text += f"*... and {len(branches) - 5} more*"
        
        keyboard = [
            [InlineKeyboardButton("🏢 New Search", callback_data="search_branch")],
            [InlineKeyboardButton("🔍 Pincode Lookup", callback_data="lookup_pincode")],
            [InlineKeyboardButton("⬅️ Main Menu", callback_data="main_menu")]
        ]
        
        await update.message.reply_text(
            response_text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    user_data.pop('awaiting', None)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors gracefully"""
    logger.error(f"Error: {context.error}", exc_info=context.error)
    
    try:
        if update and update.effective_chat:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❌ An error occurred. Please try again!",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Restart", callback_data="main_menu")]
                ])
            )
    except Exception as e:
        logger.error(f"Error in error handler: {e}")

async def post_init(application: Application):
    """Post initialization callback"""
    global bot_initialized
    
    if WEBHOOK_URL:
        webhook_url = f"{WEBHOOK_URL}/{BOT_TOKEN}"
        await application.bot.set_webhook(
            url=webhook_url,
            allowed_updates=["message", "callback_query"],
            drop_pending_updates=True,
            secret_token='WEBHOOK_SECRET_TOKEN_12345'
        )
        logger.info(f"Webhook set: {webhook_url}")
    
    bot_initialized = True
    logger.info("Bot initialization complete")

def main():
    """Start the bot with webhook for 24/7 reliability"""
    global bot_initialized
    
    logger.info(f"Starting bot on port {PORT}")
    logger.info(f"Webhook URL: {WEBHOOK_URL}")
    
    # Build application
    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_error_handler(error_handler)
    
    # Start bot
    if WEBHOOK_URL:
        # Production mode with webhook
        logger.info("Starting in WEBHOOK mode")
        logger.info(f"Health endpoint: {WEBHOOK_URL}/health")
        logger.info(f"Metrics endpoint: {WEBHOOK_URL}/metrics")
        
        application.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=BOT_TOKEN,
            webhook_url=f"{WEBHOOK_URL}/{BOT_TOKEN}",
            allowed_updates=["message", "callback_query"],
            drop_pending_updates=True,
            secret_token='WEBHOOK_SECRET_TOKEN_12345'
        )
    else:
        # Development mode with polling
        logger.info("Starting in POLLING mode (development)")
        bot_initialized = True
        application.run_polling(allowed_updates=["message", "callback_query"])

if __name__ == '__main__':
    # Run Flask for health checks in main thread with bot
    from werkzeug.serving import run_simple
    from threading import Thread
    
    def run_bot():
        main()
    
    # Start bot in separate thread
    bot_thread = Thread(target=run_bot, daemon=False)
    bot_thread.start()
    
    # Run Flask in main thread
    logger.info(f"Starting Flask health server on port {PORT}")
    run_simple('0.0.0.0', PORT, app, use_reloader=False, use_debugger=False)
