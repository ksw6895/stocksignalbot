#!/usr/bin/env python3
import os
import threading
import time
import logging
from flask import Flask, jsonify, request
from datetime import datetime
from stock_signal_bot import StockSignalBot
from config import RENDER_PORT

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

bot_instance = None
bot_thread = None
bot_status = {
    'running': False,
    'start_time': None,
    'last_scan': None,
    'total_scans': 0,
    'total_signals': 0,
    'last_error': None,
    'api_requests_remaining': 0
}


def run_bot():
    global bot_instance, bot_status
    try:
        logger.info("Starting Stock Signal Bot in background thread...")
        bot_instance = StockSignalBot()
        bot_status['running'] = True
        bot_status['start_time'] = datetime.now().isoformat()
        bot_instance.run()
    except Exception as e:
        logger.error(f"Bot crashed: {e}")
        bot_status['running'] = False
        bot_status['last_error'] = str(e)


@app.route('/health', methods=['GET'])
def health_check():
    if bot_status['running'] and bot_thread and bot_thread.is_alive():
        status = 'healthy'
        status_code = 200
    else:
        status = 'unhealthy'
        status_code = 503
    
    if bot_instance:
        bot_status['total_scans'] = bot_instance.total_scans
        bot_status['total_signals'] = bot_instance.total_signals
        if bot_instance.last_scan_time:
            bot_status['last_scan'] = bot_instance.last_scan_time.isoformat()
        bot_status['api_requests_remaining'] = bot_instance.data_fetcher.fmp_client.get_remaining_requests()
    
    return jsonify({
        'status': status,
        'timestamp': datetime.now().isoformat(),
        'bot_status': bot_status,
        'memory_usage_mb': get_memory_usage(),
        'uptime_seconds': get_uptime()
    }), status_code


@app.route('/status', methods=['GET'])
def status():
    if not bot_instance:
        return jsonify({'error': 'Bot not initialized'}), 503
    
    return jsonify({
        'running': bot_status['running'],
        'start_time': bot_status['start_time'],
        'last_scan': bot_status['last_scan'],
        'total_scans': bot_instance.total_scans,
        'total_signals': bot_instance.total_signals,
        'signals_sent_count': len(bot_instance.signals_sent),
        'cached_stocks': len(bot_instance.data_fetcher.cached_stocks),
        'api_requests_remaining': bot_instance.data_fetcher.fmp_client.get_remaining_requests(),
        'market_open': bot_instance.data_fetcher.is_market_open(),
        'memory_usage_mb': get_memory_usage()
    })


@app.route('/trigger-scan', methods=['POST'])
def trigger_scan():
    auth_token = request.headers.get('Authorization')
    expected_token = os.getenv('ADMIN_TOKEN')
    
    if expected_token and auth_token != f"Bearer {expected_token}":
        return jsonify({'error': 'Unauthorized'}), 401
    
    if not bot_instance or not bot_status['running']:
        return jsonify({'error': 'Bot not running'}), 503
    
    try:
        threading.Thread(target=bot_instance.scan_for_signals).start()
        return jsonify({
            'message': 'Scan triggered',
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/clear-cache', methods=['POST'])
def clear_cache():
    auth_token = request.headers.get('Authorization')
    expected_token = os.getenv('ADMIN_TOKEN')
    
    if expected_token and auth_token != f"Bearer {expected_token}":
        return jsonify({'error': 'Unauthorized'}), 401
    
    if not bot_instance:
        return jsonify({'error': 'Bot not initialized'}), 503
    
    try:
        bot_instance.data_fetcher.clear_cache()
        return jsonify({
            'message': 'Cache cleared',
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/metrics', methods=['GET'])
def metrics():
    metrics_text = f"""# HELP bot_running Bot running status
# TYPE bot_running gauge
bot_running {1 if bot_status['running'] else 0}

# HELP total_scans Total number of scans performed
# TYPE total_scans counter
total_scans {bot_status['total_scans']}

# HELP total_signals Total number of signals sent
# TYPE total_signals counter
total_signals {bot_status['total_signals']}

# HELP api_requests_remaining FMP API requests remaining
# TYPE api_requests_remaining gauge
api_requests_remaining {bot_status['api_requests_remaining']}

# HELP memory_usage_bytes Current memory usage in bytes
# TYPE memory_usage_bytes gauge
memory_usage_bytes {get_memory_usage() * 1024 * 1024}
"""
    return metrics_text, 200, {'Content-Type': 'text/plain; charset=utf-8'}


@app.route('/', methods=['GET'])
def index():
    return jsonify({
        'service': 'Stock Signal Bot',
        'version': '1.0.0',
        'endpoints': {
            '/health': 'Health check endpoint',
            '/status': 'Detailed bot status',
            '/metrics': 'Prometheus metrics',
            '/trigger-scan': 'Manually trigger a scan (requires auth)',
            '/clear-cache': 'Clear data cache (requires auth)'
        }
    })


def get_memory_usage():
    try:
        import psutil
        process = psutil.Process(os.getpid())
        return round(process.memory_info().rss / 1024 / 1024, 2)
    except:
        return 0


def get_uptime():
    if bot_status['start_time']:
        start = datetime.fromisoformat(bot_status['start_time'])
        return (datetime.now() - start).total_seconds()
    return 0


def initialize_bot():
    global bot_thread
    
    time.sleep(5)
    
    logger.info("Initializing Stock Signal Bot...")
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    logger.info("Bot thread started")


if __name__ == '__main__':
    port = RENDER_PORT
    logger.info(f"Starting Flask server on port {port}")
    
    init_thread = threading.Thread(target=initialize_bot, daemon=True)
    init_thread.start()
    
    app.run(host='0.0.0.0', port=port, debug=False)