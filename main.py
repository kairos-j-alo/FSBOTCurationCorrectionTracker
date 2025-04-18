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

@app.route('/notify', methods=['POST'])
def notify():
    """API endpoint to receive notifications and send Discord messages."""
    log.info("Received request on /notify endpoint.")
    try:
        # --- Request Validation and Security ---

        # 1. Check API Key
        api_key = request.headers.get("api-key")
        log.info(f"Received API Key header: {'Present' if api_key else 'Missing'}")
        if api_key != API_SECRET:
            log.warning(f"Unauthorized request attempt. Provided key (first 5 chars): '{str(api_key)[:5]}...'")
            return jsonify({"error": "Unauthorized"}), 401
        log.info("API Key validated successfully.")

        # 2. Check for JSON body and parse it
        if not request.is_json:
             log.warning("Request received without 'Content-Type: application/json' header.")
             return jsonify({"error": "Request must be JSON"}), 400
        data = request.get_json()
        if not data:
             log.warning("Request received with JSON Content-Type but empty or invalid body.")
             return jsonify({"error": "Missing or invalid JSON body"}), 400
        log.info(f"Received data: {data}")

        # 3. Extract required data fields
        mode = data.get("mode")
        message = data.get("message")

        # 4. Validate required fields
        if not mode or not message:
            log.warning(f"Missing 'mode' (got: '{mode}') or 'message' (got: '{message}') in request data")
            return jsonify({"error": "Missing 'mode' or 'message' fields"}), 400

        link = data.get("link", "") # Optional field
        user_id_str = data.get("user_id") # Get as string for now
        channel_id_str = data.get("channel_id") # Get as string for now

        # --- Prepare Message ---
        full_message = f"{message}\n\n{link}" if link else message

        # --- Define the Asynchronous Discord Task ---
        async def send_discord_message():
            """Coroutine to handle the actual Discord interaction."""
            log.info("Waiting for bot to be ready before sending...")
            await bot.wait_until_ready() # Crucial: wait until bot is fully connected
            log.info("Bot is ready. Proceeding with send action.")

            try:
                if mode == "dm":
                    if not user_id_str:
                        log.warning("DM mode specified but 'user_id' is missing in data.")
                        # Optionally return or just log, depending on desired strictness
                        return # Stop processing this task

                    try:
                        user_id = int(user_id_str) # Convert ID to integer
                    except ValueError:
                        log.warning(f"Invalid 'user_id' format received: {user_id_str}. Must be an integer.")
                        return # Stop processing this task

                    log.info(f"Attempting to fetch user {user_id}")
                    user = await bot.fetch_user(user_id)
                    log.info(f"Attempting to send DM to {user.name} ({user_id})")
                    await user.send(full_message)
                    log.info(f"✅ DM sent successfully to user {user_id}")

                elif mode == "channel":
                    if not channel_id_str:
                        log.warning("Channel mode specified but 'channel_id' is missing in data.")
                        return # Stop processing this task

                    try:
                        channel_id = int(channel_id_str) # Convert ID to integer
                    except ValueError:
                        log.warning(f"Invalid 'channel_id' format received: {channel_id_str}. Must be an integer.")
                        return # Stop processing this task

                    log.info(f"Attempting to fetch channel {channel_id}")
                    channel = bot.get_channel(channel_id) # Try cache first for efficiency
                    if not channel:
                        log.info(f"Channel {channel_id} not in cache, attempting direct fetch...")
                        channel = await bot.fetch_channel(channel_id) # Fetch if not cached

                    # Check if channel exists and is a standard text channel
                    if channel and isinstance(channel, discord.TextChannel):
                        log.info(f"Attempting to send message to channel #{channel.name} ({channel_id})")
                        await channel.send(full_message)
                        log.info(f"✅ Message sent successfully to channel {channel_id}")
                    elif channel:
                        log.warning(f"Fetched channel {channel_id} is not a TextChannel (Type: {type(channel)}). Cannot send message.")
                    else:
                        # fetch_channel raises NotFound/Forbidden if it fails, caught below
                        log.warning(f"Could not find channel {channel_id} after fetch attempt.")


                else:
                    log.warning(f"Invalid mode specified in request: '{mode}'. Must be 'dm' or 'channel'.")

            # --- Specific Discord Error Handling ---
            except discord.errors.NotFound:
                target_id = user_id_str if mode == 'dm' else channel_id_str
                log.error(f"❌ Discord Error: Could not find the specified user/channel ({target_id}). Please check the ID.", exc_info=False) # No need for traceback for NotFound
            except discord.errors.Forbidden:
                target_id = user_id_str if mode == 'dm' else channel_id_str
                log.error(f"❌ Discord Error: Bot lacks permissions to send to the user/channel ({target_id}). Check bot's roles/permissions.", exc_info=False) # No need for traceback for Forbidden
            # --- General Error Handling ---
            except Exception as e:
                # Log any other unexpected errors during Discord interaction
                log.error(f"❌ An unexpected error occurred within send_discord_message: {e}", exc_info=True) # Include traceback for unexpected errors

        # --- Schedule the Discord Task ---
        log.info("Scheduling the send_discord_message task using asyncio.create_task.")
        asyncio.create_task(send_discord_message())

        # --- Return Success Response to Caller ---
        # Respond immediately, don't wait for the Discord message to send
        return jsonify({"status": "Message queued for sending"}), 200

    except Exception as e:
        # Catch errors during initial request processing (before task scheduling)
        log.error(f"❌ Error processing /notify request BEFORE scheduling Discord task: {e}", exc_info=True)
        return jsonify({"error": "Internal server error processing request"}), 500


# --- Flask Server Execution ---

def run_flask():
    """Runs the Flask app."""
    # Host 0.0.0.0 makes it accessible externally (required by Render)
    # Port 8080 is a common default for Render web services (check your Render service settings)
    log.info("Starting Flask server thread on host 0.0.0.0, port 8080.")
    try:
        # Use Werkzeug's production server or just app.run for simplicity here
        app.run(host="0.0.0.0", port=8080)
    except Exception as e:
         # Log if the Flask server itself fails to start or crashes
         log.error(f"Flask server thread failed: {e}", exc_info=True)

# Start Flask in a separate thread so it doesn't block the bot
# Make it a daemon thread so it exits when the main bot process exits
log.info("Creating and starting Flask thread.")
flask_thread = Thread(target=run_flask, daemon=True)
flask_thread.start()


# --- Discord Bot Execution ---

# This should be the *last* thing executed in the main thread, as bot.run() is blocking.
try:
    log.info("Starting Discord bot login and connection...")
    bot.run(BOT_TOKEN)
except discord.LoginFailure:
    log.error("FATAL: Improper token passed to bot.run(). Check BOT_TOKEN.", exc_info=True)
except Exception as e:
     log.error(f"FATAL: An error occurred while running the bot: {e}", exc_info=True)

log.info("Bot process has exited.") # This line might only be reached if bot.run stops gracefully or fails
