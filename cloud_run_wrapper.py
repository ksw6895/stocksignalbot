#!/usr/bin/env python3
"""
Cloud Run wrapper for the crypto signal bot
Provides HTTP health check endpoint while running the bot
"""

import os
import threading
import logging
from flask import Flask, jsonify
import crypto_signal_bot

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Global variable to track bot status
bot_status = {"running": False, "last_scan": None, "error": None}

@app.route('/')
def home():
    return jsonify({
        "service": "Crypto Signal Bot",
        "status": "running" if bot_status["running"] else "stopped",
        "last_scan": bot_status["last_scan"],
        "error": bot_status["error"]
    })

@app.route('/health')
def health():
    return jsonify({"status": "healthy"}), 200

def run_bot():
    """Run the crypto signal bot in a separate thread"""
    global bot_status
    try:
        logger.info("Starting crypto signal bot...")
        bot_status["running"] = True
        bot_status["error"] = None
        
        # Import and run the main bot
        if __name__ == "__main__":
            import sys
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            
        from crypto_signal_bot import main
        main()
        
    except Exception as e:
        logger.error(f"Bot error: {e}")
        bot_status["error"] = str(e)
        bot_status["running"] = False

if __name__ == '__main__':
    # Start the bot in a separate thread
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    # Run Flask app
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)