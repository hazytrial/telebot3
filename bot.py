import os
import logging
import json
import tempfile
import asyncio
from urllib.parse import urlparse
from functools import wraps
from flask import Flask, request

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters
import yt_dlp

# ===== Logging Setup =====
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# ===== Flask App for Render/UptimeRobot =====
app = Flask(__name__)

@app.route("/", methods=["GET"])
def health_check():
    """UptimeRobot/BetterStack health monitor"""
    return {"status": "ok", "service": "Video Downloader Bot"}, 200


# ===== Async Timeout Decorator =====
def async_timeout(seconds):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            try:
                return await asyncio.wait_for(func(*args, **kwargs), timeout=seconds)
            except asyncio.TimeoutError:
                raise TimeoutError(f"Operation timed out after {seconds} seconds")
        return wrapper
    return decorator


# ===== Bot Class =====
class VideoDownloaderBot:
    def __init__(self, token: str, base_url: str):
        self.token = token
        self.base_url = base_url
        self.stats_file = "bot_stats.json"
        self.download_timeout = 180
        self.admins = [8275649347,8177229129]
        self.bot_owner = "Hazy"
        self.bot_telegram = "@Hazypy"
        self.load_stats()

    # --- Stats ---
    def load_stats(self):
        try:
            with open(self.stats_file, "r") as f:
                self.stats = json.load(f)
        except FileNotFoundError:
            self.stats = {
                "total_downloads": 0,
                "users": {},
                "platforms": {},
                "failed_downloads": 0,
                "admin_broadcasts": 0,
            }
            self.save_stats()

    def save_stats(self):
        try:
            with open(self.stats_file, "w") as f:
                json.dump(self.stats, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save stats: {e}")

    def update_stats(self, user_id: int, platform: str, success=True):
        if success:
            self.stats["total_downloads"] += 1
            self.stats["users"].setdefault(str(user_id), 0)
            self.stats["users"][str(user_id)] += 1
            self.stats["platforms"][platform] = self.stats["platforms"].get(platform, 0) + 1
        else:
            self.stats["failed_downloads"] += 1
        self.save_stats()

    # --- Command Handlers ---
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = (
            "🎥 **Welcome to Video Downloader Bot!**\n\n"
            "Just send me a **video link** and I’ll download it for you!\n\n"
            "Supported: YouTube, Instagram, TikTok, Twitter, Facebook, Pinterest & more.\n\n"
            "⚠️ **Use responsibly — respect copyright laws.**"
        )
        await update.message.reply_text(text)

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        text = (
            "🤖 **How to Use:**\n\n"
            "1️⃣ Send a valid video link.\n"
            "2️⃣ Wait for the bot to fetch it.\n"
            "3️⃣ Receive your downloaded file!\n\n"
            "**Supported Platforms:** YouTube, Instagram, TikTok, Twitter, Facebook, Pinterest, and more."
        )
        await update.message.reply_text(text)

    async def about_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            f"👑 **Video Downloader Bot**\n\nBuilt with ❤️ by {self.bot_owner}\nTelegram: {self.bot_telegram}"
        )

    # --- Downloading Logic ---
    @async_timeout(180)
    async def download_video(self, url: str, platform: str):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._download_sync, url, platform)

    def _download_sync(self, url: str, platform: str):
        ydl_opts = {
            "format": "best[height<=720]/best",
            "outtmpl": os.path.join(tempfile.gettempdir(), f"{platform}_%(title)s.%(ext)s"),
            "quiet": True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            return ydl.prepare_filename(info)

    def get_platform(self, url: str):
        domain = urlparse(url.lower()).netloc
        if "youtube" in domain or "youtu.be" in domain:
            return "youtube"
        elif "instagram" in domain:
            return "instagram"
        elif "tiktok" in domain:
            return "tiktok"
        elif "twitter" in domain or "x.com" in domain:
            return "twitter"
        elif "facebook" in domain:
            return "facebook"
        elif "pinterest" in domain:
            return "pinterest"
        return "generic"

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        url = update.message.text.strip()
        user_id = update.effective_user.id

        if not url.startswith(("http://", "https://")):
            await update.message.reply_text("⚠️ Please send a valid link starting with http:// or https://")
            return

        platform = self.get_platform(url)
        msg = await update.message.reply_text(f"🔄 Downloading from {platform.capitalize()}... Please wait.")

        try:
            path = await self.download_video(url, platform)
            size = os.path.getsize(path) / (1024 * 1024)
            if size > 49:
                await msg.edit_text("❌ File too large for Telegram (max 50MB).")
                self.update_stats(user_id, platform, success=False)
                return

            self.update_stats(user_id, platform, success=True)
            caption = f"✅ Downloaded successfully from {platform.capitalize()}!"
            with open(path, "rb") as f:
                if path.endswith((".mp4", ".webm", ".mov", ".avi")):
                    await update.message.reply_video(video=f, caption=caption)
                else:
                    await update.message.reply_document(document=f, caption=caption)

            await msg.delete()
        except Exception as e:
            logger.error(f"Error: {e}")
            await msg.edit_text("❌ Download failed. Try again later.")
            self.update_stats(user_id, platform, success=False)
        finally:
            if os.path.exists(path):
                os.remove(path)

    # --- Start Bot ---
    async def run(self):
        application = (
            Application.builder()
            .token(self.token)
            .concurrent_updates(True)
            .build()
        )

        application.add_handler(CommandHandler("start", self.start))
        application.add_handler(CommandHandler("help", self.help_command))
        application.add_handler(CommandHandler("about", self.about_command))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))

        # Webhook URL
        webhook_url = f"{self.base_url}/{self.token}"
        await application.bot.set_webhook(webhook_url)
        logger.info(f"Webhook set: {webhook_url}")

        async with application:
            await application.start()
            await application.updater.start_webhook(listen="0.0.0.0", port=5000, webhook_url=webhook_url)
            await application.idle()


# ===== Run Server =====
if __name__ == "__main__":
    TOKEN = "8408389849:AAFWJe7ljfbaHmhmauc00BBZQtP7HD2ibSU"
    BASE_URL = os.getenv("RENDER_EXTERNAL_URL", "https://your-render-app.onrender.com")

    bot = VideoDownloaderBot(TOKEN, BASE_URL)
    asyncio.run(bot.run())
