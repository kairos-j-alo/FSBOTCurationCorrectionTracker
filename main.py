import os
import time
import logging
import asyncio
from threading import Thread

import discord
from discord.ext import commands
from flask import Flask, request, jsonify
from dotenv import load_dotenv


# --- Configuration ---

# Load environment variables from .env file if it exists
load_dotenv()

# Setup logging
# Using a format makes logs clearer in Render
logging.basicConfig(level=logging.INFO, format='%(asctime)s:%(levelname)s:%(name)s: %(message)s')
log = logging.getLogger(__name__) # Use a named logger

# Load sensitive tokens from environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_SECRET = os.getenv("SECRET_API_KEY")

# --- Environment Variable Checks ---

# Ensure environment variables are actually set
if not BOT_TOKEN:
    log.error("FATAL: BOT_TOKEN environment variable is missing!")
    exit(1) # Exit if essential config is missing
if not API_SECRET:
    log.error("FATAL: SECRET_API_KEY environment variable is missing!")
    exit(1)

log.info("BOT_TOKEN and SECRET_API_KEY loaded successfully.")

# --- Discord Bot Setup ---

# Define necessary intents
intents = discord.Intents.default()
intents.members = True # Required for fetch_user/fetch_channel in some cases

# Initialize the bot instance
bot = commands.Bot(command_prefix="!", intents=intents)

# ✅ SOLUTION: Add a global flag to reliably track the bot's readiness.
BOT_IS_READY = False

@bot.event
async def on_ready():
    """Event handler for when the bot logs in and is fully ready."""
    global BOT_IS_READY # Use the global keyword to modify the flag
    log.info(f'Bot logged in as {bot.user.name} ({bot.user.id})')
    log.info('Bot is now fully ready and listening for API calls.')
    BOT_IS_READY = True # Set the flag to True once the bot is ready.


# --- Flask Web Server Setup ---

# Initialize the Flask app
app = Flask(__name__)

@app.route('/notify', methods=['POST', 'GET', 'HEAD'])
def notify():
    """
    API endpoint to receive notifications (POST), keep-alive pings (GET),
    or header-only keep-alive pings (HEAD).
    Sends Discord messages for POST requests. Requires X-API-Key header for POST.
    """
    log.info(f"Received {request.method} request on /notify endpoint from {request.remote_addr}.")

    try:
        # --- Method-Specific Handling ---

        # Handle GET/HEAD requests (for health checks and uptime monitoring)
        if request.method in ('GET', 'HEAD'):
            # Check the bot's ready status for a more informative health check
            if BOT_IS_READY:
                return jsonify({"status": "Bot is online and ready."}), 200
            else:
                return jsonify({"status": "Bot is running but not yet ready."}), 503 # Service Unavailable

        # Handle POST requests (the main functionality)
        elif request.method == 'POST':
            log.info("Processing POST request...")

            # 1. Check API Key
            api_key = request.headers.get("X-API-Key")
            if api_key != API_SECRET:
                provided_key_snippet = str(api_key)[:5] + '...' if api_key else 'None'
                log.warning(f"Unauthorized POST request attempt. Provided key: '{provided_key_snippet}'")
                return jsonify({"error": "Unauthorized"}), 401
            log.info("API Key validated successfully.")

            # 2. Check for JSON body
            if not request.is_json:
                log.warning("POST request lacks 'Content-Type: application/json' header.")
                return jsonify({"error": "Request must be JSON"}), 400
            data = request.get_json()
            if not data:
                log.warning("POST request has empty/invalid JSON body.")
                return jsonify({"error": "Missing or invalid JSON body"}), 400
            log.info(f"Received POST data: {data}")

            # 3. Extract and validate required data fields
            mode = data.get("mode")
            message = data.get("message")
            if not mode or not message:
                log.warning(f"Missing 'mode' or 'message' in POST data.")
                return jsonify({"error": "Missing 'mode' or 'message' fields"}), 400

            # 4. Extract optional fields
            link = data.get("link", "")
            user_id_str = data.get("user_id")
            channel_id_str = data.get("channel_id")
            full_message = f"{message}\n\n{link}" if link else message

            # --- Define the Asynchronous Discord Task ---
            async def send_discord_message():
                """Coroutine to handle the actual Discord interaction."""
                # The `await bot.wait_until_ready()` is still good practice inside the coroutine,
                # acting as a final safeguard.
                await bot.wait_until_ready()
                log.info("Coroutine started: Proceeding with send action.")

                try:
                    if mode == "dm":
                        if not user_id_str:
                            log.warning("DM mode specified but 'user_id' is missing.")
                            return
                        try:
                            user_id = int(user_id_str)
                            user = await bot.fetch_user(user_id)
                            await user.send(full_message)
                            log.info(f"✅ DM sent successfully to user {user_id}")
                        except ValueError:
                            log.warning(f"Invalid 'user_id' format: {user_id_str}.")
                        except discord.NotFound:
                            log.error(f"❌ Discord Error: User with ID {user_id_str} not found.")
                        except discord.Forbidden:
                            log.error(f"❌ Discord Error: Cannot send DM to user {user_id_str}. They may have DMs disabled.")

                    elif mode == "channel":
                        if not channel_id_str:
                            log.warning("Channel mode specified but 'channel_id' is missing.")
                            return
                        try:
                            channel_id = int(channel_id_str)
                            # Using `get_channel` with a fallback to `fetch_channel` is efficient
                            channel = bot.get_channel(channel_id) or await bot.fetch_channel(channel_id)
                            
                            if channel and hasattr(channel, 'send'):
                                await channel.send(full_message)
                                log.info(f"✅ Message sent successfully to channel {channel_id}")
                            elif channel:
                                log.warning(f"Fetched channel {channel_id} is not a sendable channel (Type: {type(channel)}).")
                            else:
                                 log.warning(f"Could not find channel {channel_id} after fetch attempt.")
                        except ValueError:
                             log.warning(f"Invalid 'channel_id' format: {channel_id_str}.")
                        except discord.NotFound:
                            log.error(f"❌ Discord Error: Channel with ID {channel_id_str} not found.")
                        except discord.Forbidden:
                            log.error(f"❌ Discord Error: Bot lacks permissions for channel {channel_id_str}.")
                    else:
                        log.warning(f"Invalid mode specified: '{mode}'.")

                except Exception as e:
                    log.error(f"❌ Unexpected error within send_discord_message: {e}", exc_info=True)

            # ✅ SOLUTION: Check the BOT_IS_READY flag before scheduling the task.
            log.info("Checking if bot is ready before scheduling message...")
            if not BOT_IS_READY:
                log.warning("API call received, but bot is not ready yet. Responding with 503.")
                return jsonify({"error": "Service Unavailable: Bot is still initializing"}), 503
            
            # If we get here, the bot is ready.
            log.info("Bot is ready. Scheduling the send_discord_message task.")
            bot.loop.call_soon_threadsafe(lambda: asyncio.create_task(send_discord_message()))

            # Return a 202 Accepted response to indicate the request was received and is being processed.
            return jsonify({"status": "Message queued for sending"}), 202

    except Exception as e:
        log.error(f"❌ Unhandled error processing {request.method} request: {e}", exc_info=True)
        return jsonify({"error": "Internal server error"}), 500


# --- Flask Server Execution ---

def run_flask():
     """Runs the Flask app."""
     log.info("Starting Flask server thread.")
     try:
         port = int(os.environ.get("PORT", 8080))
         # Use Flask's built-in server. For production, consider 'waitress'.
         app.run(host="0.0.0.0", port=port, debug=False)
     except Exception as e:
          log.error(f"Flask server thread failed: {e}", exc_info=True)

# Start Flask in a separate, daemonic thread
log.info("Creating and starting Flask thread.")
flask_thread = Thread(target=run_flask, daemon=True)
flask_thread.start()


# --- Discord Bot Execution ---

# ✅ SOLUTION: Use a resilient `while` loop to handle connection errors and prevent crash-loops.
RETRY_DELAY = 600 # Delay in seconds (600 seconds = 10 minutes)

while True:
    try:
        log.info("Attempting to start Discord bot...")
        # This call is blocking and will run until the bot disconnects or an error occurs.
        bot.run(BOT_TOKEN)

    except discord.errors.HTTPException as e:
        # This catches login errors like 429 Too Many Requests (Cloudflare ban).
        log.error(f"Discord HTTP Exception: {e.status} {e.text}")
        log.info(f"Retrying bot login in {RETRY_DELAY} seconds...")
        time.sleep(RETRY_DELAY) # Wait before trying again to allow the ban to lift.

    except discord.errors.LoginFailure:
        # This catches an invalid token. This is a permanent failure.
        log.error("FATAL: Improper token passed. The bot will not restart. Please check BOT_TOKEN.")
        break # Exit the loop and the script.

    except Exception as e:
        # Catch any other unexpected errors during the bot's runtime.
        log.error(f"An unexpected error occurred: {e}", exc_info=True)
        # We need to reset the ready flag if the bot crashes and restarts.
        BOT_IS_READY = False
        log.info(f"Restarting bot after crash in {RETRY_DELAY} seconds...")
        time.sleep(RETRY_DELAY)

log.info("Bot process has exited.")
