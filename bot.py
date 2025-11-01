import os
import logging
import json
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    ChatJoinRequestHandler,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes
)
from flask import Flask, jsonify
import threading
import asyncio
BOT_TOKEN = "8514417883:AAEBpufXJ0NdXM0xzhzVT7NRLFJ9X_n4Boc"
ADMIN_IDS = 8275649347
LOG_FILE = "auto_approve_log.txt"
STATS_FILE = "bot_stats.json"
HEALTH_CHECK_PORT = int(os.environ.get("PORT", 8080))
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)
logging.getLogger('werkzeug').setLevel(logging.WARNING)
class BotStats:
    def __init__(self):
        self.start_time = datetime.now()
        self.total_requests = 0
        self.approved = 0
        self.failed = 0
        self.recent_users = []
        self.chat_stats = {}
        self.daily_stats = {}
        self.load_stats()
    
    def load_stats(self):
        try:
            if os.path.exists(STATS_FILE):
                with open(STATS_FILE, 'r') as f:
                    data = json.load(f)
                    self.total_requests = data.get('total_requests', 0)
                    self.approved = data.get('approved', 0)
                    self.failed = data.get('failed', 0)
                    self.chat_stats = data.get('chat_stats', {})
                    self.daily_stats = data.get('daily_stats', {})
                    logger.info("📂 Loaded existing statistics")
        except Exception as e:
            logger.error(f"Failed to load stats: {e}")
    
    def save_stats(self):
        try:
            data = {
                'total_requests': self.total_requests,
                'approved': self.approved,
                'failed': self.failed,
                'chat_stats': self.chat_stats,
                'daily_stats': self.daily_stats,
                'last_updated': datetime.now().isoformat()
            }
            with open(STATS_FILE, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save stats: {e}")
    
    def add_request(self, chat_id, chat_title, user_id, user_name, approved=True):
        self.total_requests += 1
        if approved:
            self.approved += 1
        else:
            self.failed += 1
        
        # Track per-chat statistics
        chat_key = str(chat_id)
        if chat_key not in self.chat_stats:
            self.chat_stats[chat_key] = {
                'title': chat_title,
                'total': 0,
                'approved': 0,
                'failed': 0
            }
        self.chat_stats[chat_key]['total'] += 1
        if approved:
            self.chat_stats[chat_key]['approved'] += 1
        else:
            self.chat_stats[chat_key]['failed'] += 1
        
        # Track daily statistics
        today = datetime.now().strftime('%Y-%m-%d')
        if today not in self.daily_stats:
            self.daily_stats[today] = {'requests': 0, 'approved': 0}
        self.daily_stats[today]['requests'] += 1
        if approved:
            self.daily_stats[today]['approved'] += 1
        
        # Keep recent users (last 50)
        self.recent_users.insert(0, {
            'user_id': user_id,
            'user_name': user_name,
            'chat_title': chat_title,
            'approved': approved,
            'timestamp': datetime.now().isoformat()
        })
        self.recent_users = self.recent_users[:50]
        
        self.save_stats()
    
    def get_uptime(self):
        """Get formatted uptime"""
        delta = datetime.now() - self.start_time
        days = delta.days
        hours, remainder = divmod(delta.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{days}d {hours}h {minutes}m {seconds}s"
    
    def get_success_rate(self):
        """Calculate success rate"""
        if self.total_requests == 0:
            return 0
        return (self.approved / self.total_requests * 100)
    
    def reset_stats(self):
        """Reset all statistics"""
        self.total_requests = 0
        self.approved = 0
        self.failed = 0
        self.recent_users = []
        self.chat_stats = {}
        self.daily_stats = {}
        self.save_stats()

stats = BotStats()
def is_admin(user_id: int) -> bool:
    """Check if user is an admin"""
    return user_id in ADMIN_IDS

def admin_only(func):
    """Decorator to restrict commands to admins only"""
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        if not is_admin(user_id):
            await update.message.reply_text(
                "❌ *Access Denied*\n\n"
                "This command is only available to bot administrators.",
                parse_mode="Markdown"
            )
            logger.warning(f"🚫 Unauthorized access attempt by {user_id}")
            return
        return await func(update, context)
    return wrapper

app = Flask(__name__)
app.logger.setLevel(logging.WARNING)

@app.route('/')
def home():
    """Root endpoint"""
    return jsonify({
        "status": "online",
        "service": "Telegram Auto-Approval Bot",
        "version": "2.0",
        "uptime": stats.get_uptime(),
        "timestamp": datetime.now().isoformat()
    })

@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({
        "status": "healthy",
        "uptime": stats.get_uptime(),
        "stats": {
            "total_requests": stats.total_requests,
            "approved": stats.approved,
            "failed": stats.failed,
            "success_rate": f"{stats.get_success_rate():.2f}%"
        }
    }), 200

@app.route('/stats')
def get_stats():
    """Detailed statistics endpoint"""
    return jsonify({
        "uptime": stats.get_uptime(),
        "start_time": stats.start_time.isoformat(),
        "total_join_requests": stats.total_requests,
        "approved": stats.approved,
        "failed": stats.failed,
        "success_rate": f"{stats.get_success_rate():.2f}%",
        "recent_users_count": len(stats.recent_users),
        "tracked_chats": len(stats.chat_stats)
    })

def run_flask():
    """Run Flask server in a separate thread"""
    logger.info("🌐 Starting health check server on port %s", HEALTH_CHECK_PORT)
    app.run(host='0.0.0.0', port=HEALTH_CHECK_PORT, debug=False, use_reloader=False)
async def handle_join_request(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle incoming join requests"""
    req = update.chat_join_request
    user = req.from_user
    chat = req.chat
    
    logger.info(
        "📥 Join request | User: %s (@%s, ID: %s) | Chat: %s (ID: %s)",
        user.first_name,
        user.username or "no_username",
        user.id,
        chat.title,
        chat.id
    )
    
    try:
        await context.bot.approve_chat_join_request(
            chat_id=chat.id,
            user_id=user.id
        )
        
        stats.add_request(chat.id, chat.title, user.id, user.first_name, approved=True)
        
        logger.info(
            "✅ APPROVED | User: %s (ID: %s) | Success rate: %.2f%%",
            user.first_name,
            user.id,
            stats.get_success_rate()
        )
        
        # Notify admins if enabled
        if context.bot_data.get('notify_admins', False):
            for admin_id in ADMIN_IDS:
                try:
                    await context.bot.send_message(
                        chat_id=admin_id,
                        text=f"✅ New approval\n👤 {user.first_name} (@{user.username or 'N/A'})\n💬 {chat.title}"
                    )
                except:
                    pass
        
    except Exception as e:
        stats.add_request(chat.id, chat.title, user.id, user.first_name, approved=False)
        logger.error(
            "❌ FAILED | User: %s (ID: %s) | Error: %s",
            user.first_name,
            user.id,
            str(e)
        )

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user_id = update.effective_user.id
    is_user_admin = is_admin(user_id)
    
    admin_text = "\n\n🔐 *Admin Commands:*\n/admin - Admin Panel" if is_user_admin else ""
    
    await update.message.reply_text(
        "🤖 *Auto-Approval Bot Active*\n\n"
        "✅ I automatically approve all join requests\n"
        "⚡ Fast & reliable approval system\n"
        "📊 Advanced statistics tracking\n\n"
        "*Commands:*\n"
        "/stats - View statistics\n"
        "/status - Bot status" 
        "Admin • @CastedSpel"+ admin_text,
        parse_mode="Markdown"
    )

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /stats command"""
    success_rate = stats.get_success_rate()
    
    # Get today's stats
    today = datetime.now().strftime('%Y-%m-%d')
    today_stats = stats.daily_stats.get(today, {'requests': 0, 'approved': 0})
    
    message = (
        f"📊 *Bot Statistics*\n\n"
        f"⏱ Uptime: `{stats.get_uptime()}`\n"
        f"📥 Total Requests: `{stats.total_requests:,}`\n"
        f"✅ Approved: `{stats.approved:,}`\n"
        f"❌ Failed: `{stats.failed:,}`\n"
        f"📈 Success Rate: `{success_rate:.2f}%`\n\n"
        f"📅 *Today's Activity:*\n"
        f"Requests: `{today_stats['requests']}`\n"
        f"Approved: `{today_stats['approved']}`\n\n"
        f"💬 Tracked Chats: `{len(stats.chat_stats)}`"
    )
    
    await update.message.reply_text(message, parse_mode="Markdown")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /status command"""
    await update.message.reply_text(
        f"🟢 *Bot Status: Online*\n\n"
        f"⏱ Uptime: `{stats.get_uptime()}`\n"
        f"📊 Success Rate: `{stats.get_success_rate():.2f}%`\n"
        f"⚡ Response: Fast\n"
        f"🔄 Auto-Approval: Active",
        parse_mode="Markdown"
    )

@admin_only
async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /admin command - Admin panel"""
    keyboard = [
        [
            InlineKeyboardButton("📊 Detailed Stats", callback_data="admin_stats"),
            InlineKeyboardButton("💬 Chat Stats", callback_data="admin_chats")
        ],
        [
            InlineKeyboardButton("👥 Recent Users", callback_data="admin_recent"),
            InlineKeyboardButton("📅 Daily Stats", callback_data="admin_daily")
        ],
        [
            InlineKeyboardButton("🔔 Notifications", callback_data="admin_notify"),
            InlineKeyboardButton("📝 Logs", callback_data="admin_logs")
        ],
        [
            InlineKeyboardButton("🗑️ Reset Stats", callback_data="admin_reset"),
            InlineKeyboardButton("🔄 Refresh", callback_data="admin_refresh")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "🔐 *Admin Control Panel*\n\n"
        "Select an option below:",
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle admin panel callbacks"""
    query = update.callback_query
    await query.answer()
    
    action = query.data
    
    if action == "admin_stats":
        success_rate = stats.get_success_rate()
        avg_per_day = stats.total_requests / max(len(stats.daily_stats), 1)
        
        text = (
            f"📊 *Detailed Statistics*\n\n"
            f"⏱ Uptime: `{stats.get_uptime()}`\n"
            f"📥 Total: `{stats.total_requests:,}`\n"
            f"✅ Approved: `{stats.approved:,}`\n"
            f"❌ Failed: `{stats.failed:,}`\n"
            f"📈 Success Rate: `{success_rate:.2f}%`\n"
            f"📊 Avg/Day: `{avg_per_day:.1f}`\n"
            f"💬 Tracked Chats: `{len(stats.chat_stats)}`\n"
            f"👥 Recent Users: `{len(stats.recent_users)}`"
        )
    
    elif action == "admin_chats":
        text = "💬 *Chat Statistics*\n\n"
        for chat_id, data in list(stats.chat_stats.items())[:10]:
            rate = (data['approved'] / max(data['total'], 1) * 100)
            text += f"📍 {data['title']}\n"
            text += f"   Total: {data['total']} | ✅ {data['approved']} | Rate: {rate:.1f}%\n\n"
        
        if len(stats.chat_stats) > 10:
            text += f"_...and {len(stats.chat_stats) - 10} more chats_"
    
    elif action == "admin_recent":
        text = "👥 *Recent Approvals* (Last 10)\n\n"
        for user in stats.recent_users[:10]:
            status = "✅" if user['approved'] else "❌"
            time = datetime.fromisoformat(user['timestamp']).strftime('%H:%M:%S')
            text += f"{status} {user['user_name']} | {time}\n"
            text += f"   💬 {user['chat_title']}\n\n"
    
    elif action == "admin_daily":
        text = "📅 *Daily Statistics* (Last 7 Days)\n\n"
        sorted_days = sorted(stats.daily_stats.items(), reverse=True)[:7]
        for date, data in sorted_days:
            rate = (data['approved'] / max(data['requests'], 1) * 100)
            text += f"📆 {date}\n"
            text += f"   Requests: {data['requests']} | Approved: {data['approved']} | Rate: {rate:.1f}%\n\n"
    
    elif action == "admin_notify":
        current = context.bot_data.get('notify_admins', False)
        context.bot_data['notify_admins'] = not current
        new_status = "Enabled" if not current else "Disabled"
        text = f"🔔 *Notifications*\n\nAdmin notifications: *{new_status}*"
    
    elif action == "admin_logs":
        try:
            with open(LOG_FILE, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                recent_logs = ''.join(lines[-20:])
                text = f"📝 *Recent Logs*\n\n```\n{recent_logs[-3000:]}```"
        except:
            text = "❌ Unable to read logs"
    
    elif action == "admin_reset":
        keyboard = [
            [
                InlineKeyboardButton("✅ Yes, Reset", callback_data="admin_reset_confirm"),
                InlineKeyboardButton("❌ Cancel", callback_data="admin_refresh")
            ]
        ]
        await query.edit_message_text(
            "⚠️ *Reset All Statistics?*\n\n"
            "This will delete all statistics data.\n"
            "This action cannot be undone!",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return
    
    elif action == "admin_reset_confirm":
        stats.reset_stats()
        text = "✅ *Statistics Reset*\n\nAll statistics have been cleared."
    
    elif action == "admin_refresh":
        keyboard = [
            [
                InlineKeyboardButton("📊 Detailed Stats", callback_data="admin_stats"),
                InlineKeyboardButton("💬 Chat Stats", callback_data="admin_chats")
            ],
            [
                InlineKeyboardButton("👥 Recent Users", callback_data="admin_recent"),
                InlineKeyboardButton("📅 Daily Stats", callback_data="admin_daily")
            ],
            [
                InlineKeyboardButton("🔔 Notifications", callback_data="admin_notify"),
                InlineKeyboardButton("📝 Logs", callback_data="admin_logs")
            ],
            [
                InlineKeyboardButton("🗑️ Reset Stats", callback_data="admin_reset"),
                InlineKeyboardButton("🔄 Refresh", callback_data="admin_refresh")
            ]
        ]
        await query.edit_message_text(
            "🔐 *Admin Control Panel*\n\n"
            "Select an option below:",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return
    
    # Add back button to all responses
    keyboard = [[InlineKeyboardButton("« Back to Admin Panel", callback_data="admin_refresh")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        text,
        reply_markup=reply_markup,
        parse_mode="Markdown"
    )

@admin_only
async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /broadcast command"""
    if not context.args:
        await update.message.reply_text(
            "📢 *Broadcast Message*\n\n"
            "Usage: `/broadcast Your message here`\n\n"
            "This will send a message to all tracked chats.",
            parse_mode="Markdown"
        )
        return
    
    message = ' '.join(context.args)
    success = 0
    failed = 0
    
    status_msg = await update.message.reply_text("📤 Broadcasting...")
    
    for chat_id in stats.chat_stats.keys():
        try:
            await context.bot.send_message(chat_id=int(chat_id), text=message)
            success += 1
        except:
            failed += 1
    
    await status_msg.edit_text(
        f"✅ *Broadcast Complete*\n\n"
        f"Sent: {success}\n"
        f"Failed: {failed}",
        parse_mode="Markdown"
    )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors"""
    logger.error(f"Update {update} caused error: {context.error}")

# ============================================================================
# MAIN APPLICATION
# ============================================================================

def main():
    """Main bot application"""
    if not BOT_TOKEN:
        raise SystemExit(
            "❌ ERROR: BOT_TOKEN environment variable not set!\n"
            "Set it using: export BOT_TOKEN='your_bot_token_here'"
        )
    
    if not ADMIN_IDS:
        logger.warning("⚠️  No admin IDs configured. Admin features will not be accessible.")
        logger.warning("Set ADMIN_IDS environment variable: export ADMIN_IDS='123456789,987654321'")
    else:
        logger.info(f"👨‍💼 Configured {len(ADMIN_IDS)} admin(s)")
    
    # Start Flask health check server in background thread
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    
    # Build Telegram bot
    application = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .concurrent_updates(True)
        .build()
    )
    
    # Add handlers
    application.add_handler(ChatJoinRequestHandler(handle_join_request))
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("admin", admin_command))
    application.add_handler(CommandHandler("broadcast", broadcast_command))
    application.add_handler(CallbackQueryHandler(admin_callback, pattern="^admin_"))
    application.add_error_handler(error_handler)
    
    logger.info("🚀 Auto-Approval Bot is now running!")
    logger.info("📊 Health check: http://0.0.0.0:%s/health", HEALTH_CHECK_PORT)
    logger.info("⚡ Fast response mode: ENABLED")
    logger.info("🔐 Admin panel: /admin")
    
    # Run bot with polling
    application.run_polling(
        drop_pending_updates=True,
        allowed_updates=Update.ALL_TYPES
    )

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("🛑 Bot stopped by user")
    except Exception as e:
        logger.critical("💥 Critical error: %s", e)
        raise
