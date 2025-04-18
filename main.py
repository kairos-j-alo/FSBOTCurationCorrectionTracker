import os
import discord
from discord.ext import commands
from flask import Flask, request, jsonify
from threading import Thread
# from keep_alive import keep_alive # Removed
from dotenv import load_dotenv
import logging
import asyncio # Added

# ... (rest of your imports and setup) ...

logging.basicConfig(level=logging.INFO)

# ... (load tokens, check variables) ...

intents = discord.Intents.default()
intents.members = True
# Consider adding message content intent if you plan command processing later
# intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

app = Flask(__name__)

@app.route('/notify', methods=['POST'])
def notify():
    # ... (get data, api key check) ...

    # Security check
    if api_key != API_SECRET:
        logging.warning(f"Unauthorized request from API key: {api_key}")
        return jsonify({"error": "Unauthorized"}), 401

    # ... (get mode, message, link, user_id, channel_id) ...

    if not mode or not message:
        # ... (error handling) ...

    full_message = f"{message}\n\n{link}" if link else message

    async def send_message():
        await bot.wait_until_ready() # Keep this safeguard
        try:
            if mode == "dm":
                # ... (your DM logic) ...
            elif mode == "channel":
                # ... (your channel logic) ...
            else:
                raise ValueError("Invalid mode specified")
        except Exception as e:
            logging.error(f"❌ Error in send_message: {e}", exc_info=True) # Keep exc_info

    # --- Use asyncio.create_task ---
    asyncio.create_task(send_message())
    # -------------------------------

    return jsonify({"status": "Message queued"}), 200


# Start Flask server in separate thread
def run_flask():
    # Make sure Render uses port 8080 (or match Render's setting)
    app.run(host="0.0.0.0", port=8080)

Thread(target=run_flask).start()
# keep_alive() # Removed

# Run the bot (this blocks the main thread)
bot.run(BOT_TOKEN)
