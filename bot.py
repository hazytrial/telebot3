import logging
import requests
import os
from flask import Flask, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from datetime import datetime
from threading import Thread

# Logging
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuration
BOT_TOKEN = os.environ.get('BOT_TOKEN', "7966712011:AAGv5WhZmW2-c87qwjAyZY6aVtczfuNf9jM")
PORT = int(os.environ.get('PORT', 10000))
WEBHOOK_URL = os.environ.get('RENDER_EXTERNAL_URL', '').rstrip('/')

# Flask app
app = Flask(__name__)
bot_start_time = datetime.now()
total_requests = 0
successful_lookups = 0

@app.route('/')
def home():
    return jsonify({"status": "running", "service": "Telegram Pincode Bot"})

@app.route('/health')
def health():
    uptime = datetime.now() - bot_start_time
    return jsonify({
        "status": "healthy",
        "uptime": str(uptime).split('.')[0],
        "total_requests": total_requests,
        "successful_lookups": successful_lookups
    }), 200

@app.route('/ping')
def ping():
    return "pong", 200

# API Functions
async def get_pincode_info(pincode):
    global total_requests, successful_lookups
    total_requests += 1
    try:
        response = requests.get(f"https://api.postalpincode.in/pincode/{pincode}", timeout=10)
        data = response.json()
        if data and data[0]['Status'] == 'Success':
            successful_lookups += 1
            return data[0]['PostOffice']
        return None
    except:
        return None

async def search_by_branch(branch_name):
    global total_requests, successful_lookups
    total_requests += 1
    try:
        response = requests.get(f"https://api.postalpincode.in/postoffice/{branch_name}", timeout=10)
        data = response.json()
        if data and data[0]['Status'] == 'Success':
            successful_lookups += 1
            return data[0]['PostOffice']
        return None
    except:
        return None

# Bot Handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🔍 Search by Pincode", callback_data="lookup_pincode")],
        [InlineKeyboardButton("🏢 Search by Branch Name", callback_data="search_branch")],
        [InlineKeyboardButton("ℹ️ Help & Instructions", callback_data="help")]
    ]
    
    welcome_text = """
*Welcome to Indian Postal Code Lookup Service* 🇮🇳

This bot provides instant access to postal information across India.

*Available Services:*
• Search by 6-digit PIN code
• Search by Post Office branch name
• Get detailed address information
• District, State & Branch type details

*Please select a service below to continue.*
    """
    
    await update.message.reply_text(
        welcome_text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "lookup_pincode":
        await query.edit_message_text(
            "*PIN Code Lookup*\n\nPlease enter a 6-digit PIN code.\n\nExample: `110001`",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Back to Menu", callback_data="main_menu")]])
        )
        context.user_data['awaiting'] = 'pincode'
        
    elif query.data == "search_branch":
        await query.edit_message_text(
            "*Branch Name Search*\n\nPlease enter the Post Office branch name.\n\nExample: `Connaught Place`",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Back to Menu", callback_data="main_menu")]])
        )
        context.user_data['awaiting'] = 'branch'
        
    elif query.data == "help":
        help_text = """
*How to Use This Service*

*PIN Code Lookup:*
1. Select "Search by Pincode"
2. Enter any valid 6-digit Indian PIN code
3. Receive complete postal details

*Branch Name Search:*
1. Select "Search by Branch Name"
2. Enter the Post Office name
3. Get matching branches with PIN codes

*Information Provided:*
• Post Office name and type
• PIN code
• District and State
• Country information

*Examples:*
PIN Code: `110001`, `400001`, `560001`
Branch: `Connaught Place`, `Andheri`, `Koramangala`

For any assistance, please contact support.
        """
        await query.edit_message_text(
            help_text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Back to Menu", callback_data="main_menu")]])
        )
    
    elif query.data == "main_menu":
        keyboard = [
            [InlineKeyboardButton("🔍 Search by Pincode", callback_data="lookup_pincode")],
            [InlineKeyboardButton("🏢 Search by Branch Name", callback_data="search_branch")],
            [InlineKeyboardButton("ℹ️ Help & Instructions", callback_data="help")]
        ]
        await query.edit_message_text(
            "*Welcome to Indian Postal Code Lookup Service* 🇮🇳\n\nPlease select a service:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
        context.user_data.pop('awaiting', None)

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text.strip()
    
    if 'awaiting' not in context.user_data:
        await start(update, context)
        return
    
    input_type = context.user_data['awaiting']
    
    if input_type == 'pincode':
        # Validate pincode
        if not user_input.isdigit() or len(user_input) != 6:
            await update.message.reply_text(
                "*Invalid PIN Code*\n\nPlease enter a valid 6-digit PIN code.",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Try Again", callback_data="lookup_pincode")],
                    [InlineKeyboardButton("← Main Menu", callback_data="main_menu")]
                ])
            )
            return
        
        await update.message.reply_text("*Searching postal database...*", parse_mode='Markdown')
        
        post_offices = await get_pincode_info(user_input)
        
        if not post_offices:
            await update.message.reply_text(
                f"*No Results Found*\n\nNo postal information available for PIN code: `{user_input}`",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Try Another PIN", callback_data="lookup_pincode")],
                    [InlineKeyboardButton("← Main Menu", callback_data="main_menu")]
                ])
            )
            return
        
        # Format results
        response = f"*PIN Code: {user_input}*\n\n"
        response += f"*Total Post Offices: {len(post_offices)}*\n\n"
        
        for i, office in enumerate(post_offices[:5], 1):
            response += f"*{i}. {office['Name']}*\n"
            response += f"   • District: {office['District']}\n"
            response += f"   • State: {office['State']}\n"
            response += f"   • Type: {office['BranchType']}\n"
            response += f"   • Country: {office['Country']}\n\n"
        
        if len(post_offices) > 5:
            response += f"_...and {len(post_offices) - 5} more post offices_\n\n"
        
        response += "_Data provided by India Post_"
        
        await update.message.reply_text(
            response,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔍 New Search", callback_data="lookup_pincode")],
                [InlineKeyboardButton("← Main Menu", callback_data="main_menu")]
            ])
        )
        
    elif input_type == 'branch':
        # Validate branch name
        if len(user_input) < 3:
            await update.message.reply_text(
                "*Invalid Input*\n\nPlease enter at least 3 characters.",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Try Again", callback_data="search_branch")],
                    [InlineKeyboardButton("← Main Menu", callback_data="main_menu")]
                ])
            )
            return
        
        await update.message.reply_text("*Searching postal database...*", parse_mode='Markdown')
        
        branches = await search_by_branch(user_input)
        
        if not branches:
            await update.message.reply_text(
                f"*No Results Found*\n\nNo branches found matching: \"{user_input}\"",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔄 Try Another Search", callback_data="search_branch")],
                    [InlineKeyboardButton("← Main Menu", callback_data="main_menu")]
                ])
            )
            return
        
        # Format results
        response = f"*Search Results for: {user_input}*\n\n"
        response += f"*Total Branches Found: {len(branches)}*\n\n"
        
        for i, branch in enumerate(branches[:5], 1):
            response += f"*{i}. {branch['Name']}*\n"
            response += f"   • PIN Code: `{branch['Pincode']}`\n"
            response += f"   • District: {branch['District']}\n"
            response += f"   • State: {branch['State']}\n\n"
        
        if len(branches) > 5:
            response += f"_...and {len(branches) - 5} more branches_\n\n"
        
        response += "_Data provided by India Post_"
        
        await update.message.reply_text(
            response,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🏢 New Search", callback_data="search_branch")],
                [InlineKeyboardButton("← Main Menu", callback_data="main_menu")]
            ])
        )
    
    context.user_data.pop('awaiting', None)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Error: {context.error}")
    try:
        if update and update.effective_chat:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="*Service Error*\n\nAn error occurred. Please try again.",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("← Main Menu", callback_data="main_menu")]])
            )
    except:
        pass

def run_bot():
    logger.info("Starting Telegram Bot")
    
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_error_handler(error_handler)
    
    if WEBHOOK_URL:
        logger.info(f"Webhook mode: {WEBHOOK_URL}")
        application.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=BOT_TOKEN,
            webhook_url=f"{WEBHOOK_URL}/{BOT_TOKEN}"
        )
    else:
        logger.info("Polling mode")
        application.run_polling()

def main():
    # Start bot thread
    bot_thread = Thread(target=run_bot, daemon=False)
    bot_thread.start()
    
    # Run Flask
    from werkzeug.serving import run_simple
    logger.info(f"Flask server on port {PORT}")
    run_simple('0.0.0.0', PORT, app, use_reloader=False, use_debugger=False)

if __name__ == '__main__':
    main()
