import os
import discord
from discord.ext import commands
from flask import Flask, request, jsonify
from threading import Thread
from keep_alive import keep_alive
from dotenv import load_dotenv
import logging

# Load environment variables
load_dotenv()

# Setup logging for better error tracking
logging.basicConfig(level=logging.INFO)

# Load tokens
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_SECRET = os.getenv("SECRET_API_KEY")

# Ensure environment variables are set
if not BOT_TOKEN or not API_SECRET:
    logging.error("Bot token or API secret is missing!")
    exit(1)

# Setup Discord bot
intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

app = Flask(__name__)

@app.route('/notify', methods=['POST'])
def notify():
    data = request.json
    api_key = request.headers.get("api-key")

    # Security check
    if api_key != API_SECRET:
        logging.warning(f"Unauthorized request from API key: {api_key}")
        return jsonify({"error": "Unauthorized"}), 401

    mode = data.get("mode")
    message = data.get("message")
    link = data.get("link", "")
    user_id = data.get("user_id")
    channel_id = data.get("channel_id")

    if not mode or not message:
        logging.warning("Missing 'mode' or 'message' in request data")
        return jsonify({"error": "Missing 'mode' or 'message'"}), 400

    full_message = f"{message}\n\n{link}" if link else message

    async def send_message():
        try:
            if mode == "dm":
                if not user_id:
                    raise ValueError("Missing 'user_id' for DM mode")
                user = await bot.fetch_user(int(user_id))
                await user.send(full_message)
                logging.info(f"✅ DM sent to user {user_id}")
            elif mode == "channel":
                if not channel_id:
                    raise ValueError("Missing 'channel_id' for channel mode")
                channel = await bot.fetch_channel(int(channel_id))
                await channel.send(full_message)
                logging.info(f"✅ Message sent to channel {channel_id}")
            else:
                raise ValueError("Invalid mode specified")
        except Exception as e:
            logging.error(f"❌ Error: {e}")

    bot.loop.create_task(send_message())

    return jsonify({"status": "Message queued"}), 200


# Start Flask server in separate thread
def run_flask():
    app.run(host="0.0.0.0", port=8080)


Thread(target=run_flask).start()
keep_alive()

# Run the bot
bot.run(BOT_TOKEN)
