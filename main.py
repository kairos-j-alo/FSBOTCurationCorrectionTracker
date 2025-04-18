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
        # Indentation: This entire async def block must be indented inside the notify function
        async def send_discord_message():
            """Coroutine to handle the actual Discord interaction."""
            # Indentation: This block must be indented inside send_discord_message
            log.info("Waiting for bot to be ready before sending...")
            await bot.wait_until_ready() # Crucial: wait until bot is fully connected
            log.info("Bot is ready. Proceeding with send action.")

            try:
                # Indentation: This block must be indented inside the try
                if mode == "dm":
                    # Indentation: This block must be indented inside the if mode == 'dm'
                    if not user_id_str:
                        log.warning("DM mode specified but 'user_id' is missing in data.")
                        return # Stop processing this task

                    try:
                        # Indentation: Inside the try block
                        user_id = int(user_id_str) # Convert ID to integer
                    except ValueError:
                        # Indentation: Inside the except block
                        log.warning(f"Invalid 'user_id' format received: {user_id_str}. Must be an integer.")
                        return # Stop processing this task

                    log.info(f"Attempting to fetch user {user_id}")
                    user = await bot.fetch_user(user_id)
                    log.info(f"Attempting to send DM to {user.name} ({user_id})")
                    await user.send(full_message)
                    log.info(f"✅ DM sent successfully to user {user_id}")

                elif mode == "channel":
                    # Indentation: This block must be indented inside the elif mode == 'channel'
                    if not channel_id_str:
                        log.warning("Channel mode specified but 'channel_id' is missing in data.")
                        return # Stop processing this task

                    try:
                        # Indentation: Inside the try block
                        channel_id = int(channel_id_str) # Convert ID to integer
                    except ValueError:
                        # Indentation: Inside the except block
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
                        # This log might not be reached if fetch_channel raises, but good for completeness
                        log.warning(f"Could not find channel {channel_id} after fetch attempt.")


                else:
                    # Indentation: Inside the main try block, aligned with the if/elif
                    log.warning(f"Invalid mode specified in request: '{mode}'. Must be 'dm' or 'channel'.")

            # --- Specific Discord Error Handling ---
            # Indentation: Aligned with the try block above
            except discord.errors.NotFound:
                target_id = user_id_str if mode == 'dm' else channel_id_str
                log.error(f"❌ Discord Error: Could not find the specified user/channel ({target_id}). Please check the ID.", exc_info=False)
            except discord.errors.Forbidden:
                target_id = user_id_str if mode == 'dm' else channel_id_str
                log.error(f"❌ Discord Error: Bot lacks permissions to send to the user/channel ({target_id}). Check bot's roles/permissions.", exc_info=False)
            # --- General Error Handling ---
            except Exception as e:
                log.error(f"❌ An unexpected error occurred within send_discord_message: {e}", exc_info=True)


        # --- Schedule the Discord Task onto the bot's event loop ---
        # Indentation: Back to the main level inside the notify function's try block
        log.info("Attempting to schedule the send_discord_message task onto the bot's event loop.")

        # Check if the bot's loop is available and running
        if bot.loop and bot.loop.is_running():
            # Indentation: Inside the if bot.loop check
            # Use call_soon_threadsafe to schedule the task creation onto the bot's loop
            bot.loop.call_soon_threadsafe(asyncio.create_task, send_discord_message())
            log.info("Task scheduling requested via call_soon_threadsafe.")
            # Respond immediately
            return jsonify({"status": "Message queued for sending"}), 200
        else:
            # Indentation: Inside the else corresponding to if bot.loop check
            log.error("Bot event loop is not available or not running to schedule task.")
            return jsonify({"error": "Internal server error: Bot not ready or loop unavailable"}), 503 # 503 Service Unavailable

    # Indentation: Aligned with the main try block of the notify function
    except Exception as e:
        # Catch errors during initial request processing (e.g., JSON parsing issues before scheduling)
        log.error(f"❌ Error processing /notify request BEFORE scheduling Discord task: {e}", exc_info=True)
        return jsonify({"error": "Internal server error processing request"}), 500


# --- Flask Server Execution ---

def run_flask():
    """Runs the Flask app."""
    # Host 0.0.0.0 makes it accessible externally (required by Render)
    # Port 8080 is a common default for Render web services (check your Render service settings)
    log.info("Starting Flask server thread on host 0.0.0.0, port 8080.")
    try:
        # Consider using a production WSGI server like gunicorn or waitress for real deployments
        # For Render, app.run() is often sufficient for simple cases
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
    log.error("FATAL: Improper token passed to bot.run(). Check BOT_TOKEN.", exc_info=False) # No need for traceback here
except discord.errors.PrivilegedIntentsRequired:
    log.error("FATAL: Privileged intents (likely Server Members or Message Content) are not enabled in the Discord Developer Portal.", exc_info=False)
    log.error("Please go to https://discord.com/developers/applications/ -> Your App -> Bot -> Privileged Gateway Intents and enable them.")
except Exception as e:
     log.error(f"FATAL: An unexpected error occurred while running the bot: {e}", exc_info=True)

log.info("Bot process has exited.")
