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
# If you ever add text commands, uncomment the line below and enable in the portal
# intents.message_content = True

# Initialize the bot instance
bot = commands.Bot(command_prefix="!", intents=intents) # Using commands.Bot is fine

@bot.event
async def on_ready():
    """Event handler for when the bot logs in and is ready."""
    log.info(f'Bot logged in as {bot.user.name} ({bot.user.id})')
    log.info('Bot is ready and listening for API calls.')

# --- Flask Web Server Setup ---

# Initialize the Flask app
app = Flask(__name__)

# MODIFICATION: Added 'GET' to the methods list
@app.route('/notify', methods=['POST', 'GET'])
def notify():
    """
    API endpoint to receive notifications (POST) or keep-alive pings (GET).
    Sends Discord messages for POST requests.
    """
    log.info(f"Received {request.method} request on /notify endpoint.") # Log method

    try:
        # --- Request Validation and Security (Common for GET and POST) ---
        # 1. Check API Key - Essential for both methods
        api_key = request.headers.get("api-key")
        log.info(f"Received API Key header: {'Present' if api_key else 'Missing'}")
        if api_key != API_SECRET:
            log.warning(f"Unauthorized request attempt. Provided key (first 5 chars): '{str(api_key)[:5]}...'")
            return jsonify({"error": "Unauthorized"}), 401
        log.info("API Key validated successfully.")

        # --- Method-Specific Handling ---

        # MODIFICATION: Handle GET requests for UptimeRobot
        if request.method == 'GET':
            log.info("GET request received (likely UptimeRobot keep-alive). Responding OK.")
            return jsonify({"status": "Bot is awake and responding to GET."}), 200

        # MODIFICATION: Handle POST requests (original functionality)
        elif request.method == 'POST':
            log.info("Processing POST request...")
            # 2. Check for JSON body and parse it (POST only)
            if not request.is_json:
                log.warning("POST request received without 'Content-Type: application/json' header.")
                return jsonify({"error": "Request must be JSON"}), 400
            data = request.get_json()
            if not data:
                log.warning("POST request received with JSON Content-Type but empty or invalid body.")
                return jsonify({"error": "Missing or invalid JSON body"}), 400
            log.info(f"Received data: {data}")

            # 3. Extract required data fields (POST only)
            mode = data.get("mode")
            message = data.get("message")

            # 4. Validate required fields (POST only)
            if not mode or not message:
                log.warning(f"Missing 'mode' (got: '{mode}') or 'message' (got: '{message}') in request data")
                return jsonify({"error": "Missing 'mode' or 'message' fields"}), 400

            link = data.get("link", "") # Optional field
            user_id_str = data.get("user_id") # Get as string for now
            channel_id_str = data.get("channel_id") # Get as string for now

            # --- Prepare Message (POST only) ---
            full_message = f"{message}\n\n{link}" if link else message

            # --- Define the Asynchronous Discord Task (POST only) ---
            # This function remains nested as it uses variables from the outer scope
            async def send_discord_message():
                """Coroutine to handle the actual Discord interaction."""
                log.info("Waiting for bot to be ready before sending...")
                await bot.wait_until_ready() # Crucial: wait until bot is fully connected
                log.info("Bot is ready. Proceeding with send action.")

                try:
                    if mode == "dm":
                        if not user_id_str:
                            log.warning("DM mode specified but 'user_id' is missing in data.")
                            return
                        try:
                            user_id = int(user_id_str)
                        except ValueError:
                            log.warning(f"Invalid 'user_id' format received: {user_id_str}. Must be an integer.")
                            return

                        log.info(f"Attempting to fetch user {user_id}")
                        user = await bot.fetch_user(user_id)
                        log.info(f"Attempting to send DM to {user.name} ({user_id})")
                        await user.send(full_message)
                        log.info(f"✅ DM sent successfully to user {user_id}")

                    elif mode == "channel":
                        if not channel_id_str:
                            log.warning("Channel mode specified but 'channel_id' is missing in data.")
                            return
                        try:
                            channel_id = int(channel_id_str)
                        except ValueError:
                            log.warning(f"Invalid 'channel_id' format received: {channel_id_str}. Must be an integer.")
                            return

                        log.info(f"Attempting to fetch channel {channel_id}")
                        channel = bot.get_channel(channel_id)
                        if not channel:
                            log.info(f"Channel {channel_id} not in cache, attempting direct fetch...")
                            channel = await bot.fetch_channel(channel_id)

                        if channel and isinstance(channel, discord.TextChannel):
                            log.info(f"Attempting to send message to channel #{channel.name} ({channel_id})")
                            await channel.send(full_message)
                            log.info(f"✅ Message sent successfully to channel {channel_id}")
                        elif channel:
                            log.warning(f"Fetched channel {channel_id} is not a TextChannel (Type: {type(channel)}). Cannot send message.")
                        else:
                             log.warning(f"Could not find channel {channel_id} after fetch attempt.")


                    else:
                        log.warning(f"Invalid mode specified in request: '{mode}'. Must be 'dm' or 'channel'.")

                # --- Specific Discord Error Handling ---
                except discord.errors.NotFound:
                    target_id = user_id_str if mode == 'dm' else channel_id_str
                    log.error(f"❌ Discord Error: Could not find the specified user/channel ({target_id}). Please check the ID.", exc_info=False)
                except discord.errors.Forbidden:
                    target_id = user_id_str if mode == 'dm' else channel_id_str
                    log.error(f"❌ Discord Error: Bot lacks permissions to send to the user/channel ({target_id}). Check bot's roles/permissions.", exc_info=False)
                # --- General Error Handling ---
                except Exception as e:
                    log.error(f"❌ An unexpected error occurred within send_discord_message: {e}", exc_info=True)


            # --- Schedule the Discord Task onto the bot's event loop (POST only) ---
            log.info("Attempting to schedule the send_discord_message task onto the bot's event loop.")
            if bot.loop and bot.loop.is_running():
                bot.loop.call_soon_threadsafe(asyncio.create_task, send_discord_message())
                log.info("Task scheduling requested via call_soon_threadsafe.")
                return jsonify({"status": "Message queued for sending"}), 200
            else:
                log.error("Bot event loop is not available or not running to schedule task.")
                return jsonify({"error": "Internal server error: Bot not ready or loop unavailable"}), 503

        # Added for completeness, although Flask should handle this based on 'methods'
        else:
             log.warning(f"Received unexpected method: {request.method}")
             return jsonify({"error": "Method Not Allowed"}), 405

    # --- General Error Handling for the entire request ---
    except Exception as e:
        # Catch errors during initial request processing (e.g., API key check failure if API_SECRET is None)
        log.error(f"❌ Error processing /notify {request.method} request BEFORE method-specific logic: {e}", exc_info=True)
        return jsonify({"error": "Internal server error processing request"}), 500


# --- Flask Server Execution ---

def run_flask():
    """Runs the Flask app."""
    log.info("Starting Flask server thread on host 0.0.0.0, port 8080.")
    try:
        # Consider using waitress or gunicorn for production
        app.run(host="0.0.0.0", port=8080) # Use Render's suggested port or 8080
    except Exception as e:
         log.error(f"Flask server thread failed: {e}", exc_info=True)

# Start Flask in a separate thread
log.info("Creating and starting Flask thread.")
flask_thread = Thread(target=run_flask, daemon=True)
flask_thread.start()


# --- Discord Bot Execution ---
try:
    log.info("Starting Discord bot login and connection...")
    bot.run(BOT_TOKEN)
except discord.LoginFailure:
    log.error("FATAL: Improper token passed to bot.run(). Check BOT_TOKEN.", exc_info=False)
except discord.errors.PrivilegedIntentsRequired:
    log.error("FATAL: Privileged intents (likely Server Members or Message Content) are not enabled in the Discord Developer Portal.", exc_info=False)
    log.error("Please go to https://discord.com/developers/applications/ -> Your App -> Bot -> Privileged Gateway Intents and enable them.")
except Exception as e:
     log.error(f"FATAL: An unexpected error occurred while running the bot: {e}", exc_info=True)

log.info("Bot process has exited.")
