import os
import discord
from discord.ext import commands
from flask import Flask, request, jsonify
from threading import Thread
from dotenv import load_dotenv
import logging
import asyncio

# --- Configuration ---

# Load environment variables from .env file if it exists
load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s:%(levelname)s:%(name)s: %(message)s')
log = logging.getLogger(__name__)

# Load sensitive tokens from environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_SECRET = os.getenv("SECRET_API_KEY")

# --- Environment Variable Checks ---

# Ensure environment variables are actually set
if not BOT_TOKEN:
    # This block is now correctly indented
    log.error("FATAL: BOT_TOKEN environment variable is missing!")
    exit(1)
if not API_SECRET:
    # This block is now correctly indented
    log.error("FATAL: SECRET_API_KEY environment variable is missing!")
    exit(1)

log.info("BOT_TOKEN and SECRET_API_KEY loaded successfully.")

# --- Discord Bot Setup ---

intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    # This block is now correctly indented
    log.info(f'Bot logged in as {bot.user.name} ({bot.user.id})')
    log.info('Bot is ready and listening for API calls.')

# --- Flask Web Server Setup ---

app = Flask(__name__)

@app.route('/notify', methods=['POST', 'GET', 'HEAD'])
def notify():
    # Everything inside this function is now correctly indented
    log.info(f"Received {request.method} request on /notify endpoint.")

    try:
        if request.method == 'GET':
            log.info("GET request received. Responding OK.")
            return jsonify({"status": "Bot is awake and responding to GET."}), 200

        elif request.method == 'HEAD':
            log.info("HEAD request received (likely UptimeRobot). Responding OK.")
            return "", 200

        elif request.method == 'POST':
            log.info("Processing POST request...")

            # --- ⚠️🚧 API KEY CHECK TEMPORARILY DISABLED FOR DEBUGGING 🚧⚠️ ---
            log.warning("SECURITY BYPASS: API Key check is currently disabled.")
            # --- END OF DISABLED API KEY CHECK ---

            if not request.is_json:
                log.warning("POST request received without 'Content-Type: application/json'.")
                return jsonify({"error": "Request must be JSON"}), 400
            
            data = request.get_json()
            if not data:
                log.warning("POST request with JSON Content-Type but empty/invalid body.")
                return jsonify({"error": "Missing or invalid JSON body"}), 400
            
            log.info(f"Received POST data: {data}")

            mode = data.get("mode")
            message = data.get("message")

            if not mode or not message:
                log.warning(f"Missing 'mode' or 'message' in POST data.")
                return jsonify({"error": "Missing 'mode' or 'message' fields"}), 400

            link = data.get("link", "")
            user_id_str = data.get("user_id")
            channel_id_str = data.get("channel_id")
            full_message = f"{message}\n\n{link}" if link else message

            async def send_discord_message():
                await bot.wait_until_ready()
                log.info("Bot is ready. Proceeding with send action.")

                try:
                    if mode == "dm":
                        if not user_id_str:
                            log.warning("DM mode specified but 'user_id' is missing.")
                            return
                        try:
                            user_id = int(user_id_str)
                        except ValueError:
                            log.warning(f"Invalid 'user_id' format: {user_id_str}.")
                            return
                        
                        user = await bot.fetch_user(user_id)
                        await user.send(full_message)
                        log.info(f"✅ DM sent successfully to user {user_id}")

                    elif mode == "channel":
                        if not channel_id_str:
                            log.warning("Channel mode specified but 'channel_id' is missing.")
                            return
                        try:
                            channel_id = int(channel_id_str)
                        except ValueError:
                            log.warning(f"Invalid 'channel_id' format: {channel_id_str}.")
                            return

                        channel = await bot.fetch_channel(channel_id)
                        if isinstance(channel, discord.TextChannel):
                            await channel.send(full_message)
                            log.info(f"✅ Message sent successfully to channel {channel_id}")
                        else:
                            log.warning(f"Could not find TextChannel {channel_id}.")
                    else:
                        log.warning(f"Invalid mode specified: '{mode}'.")

                except discord.errors.NotFound as e:
                    log.error(f"❌ Discord Error (NotFound): {e}", exc_info=False)
                except discord.errors.Forbidden as e:
                    log.error(f"❌ Discord Error (Forbidden): {e}", exc_info=False)
                except Exception as e:
                    log.error(f"❌ Unexpected error in send_discord_message: {e}", exc_info=True)

            if bot.loop and bot.loop.is_running():
                bot.loop.call_soon_threadsafe(lambda: asyncio.create_task(send_discord_message()))
                log.info("Task scheduling requested via call_soon_threadsafe.")
                return jsonify({"status": "Message queued for sending"}), 200
            else:
                log.error("Bot event loop is not available.")
                return jsonify({"error": "Internal server error: Bot not ready"}), 503
        else:
            log.warning(f"Received unexpected method: {request.method}")
            return jsonify({"error": "Method Not Allowed"}), 405

    except Exception as e:
        log.error(f"❌ Error processing /notify request: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500

# --- Flask Server Execution ---

def run_flask():
    try:
        port = int(os.environ.get("PORT", 8080))
        app.run(host="0.0.0.0", port=port)
    except Exception as e:
        log.error(f"Flask server thread failed: {e}", exc_info=True)

log.info("Creating and starting Flask thread.")
flask_thread = Thread(target=run_flask, daemon=True)
flask_thread.start()

# --- Discord Bot Execution ---

try:
    log.info("Starting Discord bot...")
    bot.run(BOT_TOKEN)
except discord.LoginFailure:
    log.error("FATAL: Improper token. Check BOT_TOKEN.", exc_info=False)
    exit(1)
except discord.errors.PrivilegedIntentsRequired:
    log.error("FATAL: Privileged intents are not enabled in the Discord Developer Portal.", exc_info=False)
    exit(1)
except Exception as e:
    log.error(f"FATAL: An unexpected error occurred running the bot: {e}", exc_info=True)
    exit(1)

log.info("Bot process has exited.")
