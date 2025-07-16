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

# MODIFICATION: Added 'HEAD' to the methods list for UptimeRobot Free Tier
@app.route('/notify', methods=['POST', 'GET', 'HEAD'])
def notify():
"""
   API endpoint to receive notifications (POST), keep-alive pings (GET),
   or header-only keep-alive pings (HEAD for UptimeRobot Free Tier).
   Sends Discord messages for POST requests. Requires api-key header for POST.
   """
log.info(f"Received {request.method} request on /notify endpoint.") # Log method

try:
# --- Method-Specific Handling ---

# Handle GET requests (Useful for manual testing or other services)
if request.method == 'GET':
# No API Key check needed for GET
log.info("GET request received. Responding OK. No API Key required.")
return jsonify({"status": "Bot is awake and responding to GET."}), 200

# MODIFICATION: Handle HEAD requests specifically for UptimeRobot Free Tier
elif request.method == 'HEAD':
# No API Key check needed for HEAD
log.info("HEAD request received (likely UptimeRobot keep-alive). Responding OK (No Body). No API Key required.")
# For HEAD, we just need to return a success status code.
# Flask automatically ensures no body is sent for a HEAD request
# when you return like this. An empty string is conventional.
return "", 200 # Return empty body, 200 OK status

# Handle POST requests (original functionality)
elif request.method == 'POST':
log.info("Processing POST request...")

# --- Request Validation and Security (POST ONLY) ---

            # --- ⚠️🚧 API KEY CHECK TEMPORARILY DISABLED FOR DEBUGGING 🚧⚠️ ---
            # To re-enable security:
            # 1. UNCOMMENT the entire block below.
            # 2. DELETE the "log.warning(...)" line that follows it.

            # # 1. Check API Key - Essential ONLY for POST requests
            # api_key = request.headers.get("api-key")
            # log.info(f"Checking API Key for POST. Header: {'Present' if api_key else 'Missing'}")
            #
            # if api_key != API_SECRET:
            #     # Log the first few chars for debugging without exposing the whole key if it's wrong
            #     provided_key_snippet = str(api_key)[:5] + '...' if api_key else 'None'
            #     log.warning(f"Unauthorized POST request attempt. Provided key snippet: '{provided_key_snippet}'")
            #     return jsonify({"error": "Unauthorized"}), 401 # This line enforces security
            #
            # log.info("API Key validated successfully for POST request.")

            # This log confirms the check is disabled. DELETE THIS LINE when you re-enable the block above.
            log.warning("SECURITY BYPASS: API Key check is currently disabled. Allowing request to proceed.")
            
            # --- END OF DISABLED API KEY CHECK ---

# 2. Check for JSON body and parse it (POST only)
if not request.is_json:
log.warning("POST request received without 'Content-Type: application/json' header.")
return jsonify({"error": "Request must be JSON"}), 400
data = request.get_json()
if not data:
log.warning("POST request received with JSON Content-Type but empty or invalid body.")
return jsonify({"error": "Missing or invalid JSON body"}), 400
log.info(f"Received POST data: {data}")

# 3. Extract required data fields (POST only)
mode = data.get("mode")
message = data.get("message")

# 4. Validate required fields (POST only)
if not mode or not message:
log.warning(f"Missing 'mode' (got: '{mode}') or 'message' (got: '{message}') in POST request data")
return jsonify({"error": "Missing 'mode' or 'message' fields"}), 400

link = data.get("link", "") # Optional field
user_id_str = data.get("user_id") # Get as string for now
channel_id_str = data.get("channel_id") # Get as string for now

# --- Prepare Message (POST only) ---
full_message = f"{message}\n\n{link}" if link else message

# --- Define the Asynchronous Discord Task (POST only) ---
async def send_discord_message():
"""Coroutine to handle the actual Discord interaction."""
log.info("Waiting for bot to be ready before sending...")
await bot.wait_until_ready() # Crucial: wait until bot is fully connected
log.info("Bot is ready. Proceeding with send action.")

try:
# (Rest of the send_discord_message logic remains the same)
if mode == "dm":
if not user_id_str:
log.warning("DM mode specified but 'user_id' is missing in data.")
return # Don't proceed if ID is missing
try:
user_id = int(user_id_str)
except ValueError:
log.warning(f"Invalid 'user_id' format received: {user_id_str}. Must be an integer.")
return # Don't proceed if ID is invalid

log.info(f"Attempting to fetch user {user_id}")
user = await bot.fetch_user(user_id)
log.info(f"Attempting to send DM to {user.name} ({user_id})")
await user.send(full_message)
log.info(f"✅ DM sent successfully to user {user_id}")

elif mode == "channel":
if not channel_id_str:
log.warning("Channel mode specified but 'channel_id' is missing in data.")
return # Don't proceed if ID is missing
try:
channel_id = int(channel_id_str)
except ValueError:
log.warning(f"Invalid 'channel_id' format received: {channel_id_str}. Must be an integer.")
return # Don't proceed if ID is invalid

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
log.error(f"❌ Discord Error: Could not find the specified user/channel ({target_id}). Please check the ID.", exc_info=False) # exc_info=False for cleaner logs here
except discord.errors.Forbidden:
target_id = user_id_str if mode == 'dm' else channel_id_str
log.error(f"❌ Discord Error: Bot lacks permissions to send to the user/channel ({target_id}). Check bot's roles/permissions.", exc_info=False) # exc_info=False
# --- General Error Handling ---
except Exception as e:
log.error(f"❌ An unexpected error occurred within send_discord_message: {e}", exc_info=True) # Keep exc_info=True for unexpected errors

# --- Schedule the Discord Task onto the bot's event loop (POST only) ---
log.info("Attempting to schedule the send_discord_message task onto the bot's event loop.")
if bot.loop and bot.loop.is_running():
# Use asyncio.create_task before passing to call_soon_threadsafe
# Schedule the coroutine to run on the bot's event loop
# NOTE: Using create_task is generally preferred for starting background tasks
# within an async function defined in the same scope.
# call_soon_threadsafe is mainly for scheduling from *other threads*.
# Since we are already *in* the Flask request handler (likely a worker thread),
# scheduling onto the bot's loop (running in another thread) IS the correct
# use case for call_soon_threadsafe. However, we need to schedule the *coroutine object*
# execution itself using something the loop understands, like ensure_future or create_task.
# The most robust way is often to create the task first.

# Option 1: Create Task then schedule (More explicit)
# future = asyncio.run_coroutine_threadsafe(send_discord_message(), bot.loop)
# # Optional: Add a callback if you need to know when it finishes/errors, but maybe overkill here.
# # future.add_done_callback(lambda f: log.info(f"Discord send task completed: {f.result()} or exception: {f.exception()}"))

# Option 2: Simpler scheduling via create_task within call_soon_threadsafe's lambda (Common pattern)
#   This ensures create_task is called *within* the bot's loop thread.
bot.loop.call_soon_threadsafe(lambda: asyncio.create_task(send_discord_message()))

log.info("Task scheduling requested via call_soon_threadsafe.")
# Return success immediately after queuing
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
# Catch errors during initial request processing (e.g., reading request)
log.error(f"❌ Error processing /notify {request.method} request BEFORE specific logic: {e}", exc_info=True)
return jsonify({"error": "Internal server error processing request"}), 500


# --- Flask Server Execution ---

def run_flask():
"""Runs the Flask app."""
# Recommended: Use 'waitress' for production instead of Flask's dev server
# You would install it (`pip install waitress`) and run like:
# from waitress import serve
# serve(app, host="0.0.0.0", port=8080)
# But for simplicity/compatibility with current setup:
log.info("Starting Flask server thread on host 0.0.0.0, port 8080.")
try:
# Use Render's suggested port or 8080 common default
port = int(os.environ.get("PORT", 8080)) # Get port from env if available
app.run(host="0.0.0.0", port=port) # Use the dynamic port
except Exception as e:
log.error(f"Flask server thread failed: {e}", exc_info=True)

# Start Flask in a separate thread
log.info("Creating and starting Flask thread.")
# daemon=True allows main thread (bot) to exit even if flask thread is running
flask_thread = Thread(target=run_flask, daemon=True)
flask_thread.start()


# --- Discord Bot Execution ---
# This should be the main blocking call at the end of the script
try:
log.info("Starting Discord bot login and connection...")
bot.run(BOT_TOKEN)
except discord.LoginFailure:
log.error("FATAL: Improper token passed to bot.run(). Check BOT_TOKEN.", exc_info=False)
exit(1) # Exit if login fails
except discord.errors.PrivilegedIntentsRequired:
log.error("FATAL: Privileged intents (likely Server Members or Message Content) are not enabled in the Discord Developer Portal.", exc_info=False)
log.error("Please go to https://discord.com/developers/applications/ -> Your App -> Bot -> Privileged Gateway Intents and enable them.")
exit(1) # Exit if intents are missing
except Exception as e:
log.error(f"FATAL: An unexpected error occurred while running the bot: {e}", exc_info=True)
exit(1) # Exit on other fatal bot errors

# This line might not be reached if the bot runs indefinitely or exits via exit()
log.info("Bot process has exited.")
