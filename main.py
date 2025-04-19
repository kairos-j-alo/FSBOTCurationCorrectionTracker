# --- Flask Web Server Setup ---

# Initialize the Flask app
app = Flask(__name__)

# MODIFICATION: Added 'GET' to the methods list (already done, good)
@app.route('/notify', methods=['POST', 'GET'])
def notify():
    """
    API endpoint to receive notifications (POST) or keep-alive pings (GET).
    Sends Discord messages for POST requests. Requires api-key header for POST.
    """
    log.info(f"Received {request.method} request on /notify endpoint.") # Log method

    try:
        # --- Method-Specific Handling ---

        # MODIFICATION: Handle GET requests for UptimeRobot FIRST
        if request.method == 'GET':
            # No API Key check needed for GET
            log.info("GET request received (likely UptimeRobot keep-alive). Responding OK. No API Key required.")
            return jsonify({"status": "Bot is awake and responding to GET."}), 200

        # MODIFICATION: Handle POST requests (original functionality)
        elif request.method == 'POST':
            log.info("Processing POST request...")

            # --- Request Validation and Security (POST ONLY) --- <<< MOVED HERE
            # 1. Check API Key - Essential ONLY for POST requests
            api_key = request.headers.get("api-key")
            log.info(f"Checking API Key for POST. Header: {'Present' if api_key else 'Missing'}")
            if api_key != API_SECRET:
                # Log the first few chars for debugging without exposing the whole key if wrong
                provided_key_snippet = str(api_key)[:5] + '...' if api_key else 'None'
                log.warning(f"Unauthorized POST request attempt. Provided key snippet: '{provided_key_snippet}'")
                return jsonify({"error": "Unauthorized"}), 401
            log.info("API Key validated successfully for POST request.")
            # --- End API Key Check ---

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
                        # ... (DM sending logic) ...
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
                        # ... (Channel sending logic) ...
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
                # Use asyncio.create_task before passing to call_soon_threadsafe
                task = asyncio.create_task(send_discord_message())
                bot.loop.call_soon_threadsafe(lambda: None) # Ensure loop processes the task
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
        # Catch errors during initial request processing
        log.error(f"❌ Error processing /notify {request.method} request: {e}", exc_info=True)
        return jsonify({"error": "Internal server error processing request"}), 500

# --- (Rest of your bot code: run_flask, bot.run, etc. remains the same) ---
