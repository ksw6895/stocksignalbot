#!/usr/bin/env python3
"""
Cryptocurrency Real-time Signal Bot
Monitors crypto pairs for buy signals using the kwon_strategy and sends Telegram notifications
"""

import os
import time
import logging
import asyncio
import schedule
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import pandas as pd
from dotenv import load_dotenv
import telegram
from telegram import Bot
from config import ANALYSIS_SYMBOLS
from symbols import fetch_candles, fetch_coinmarketcap_coins_multi_pages, get_valid_binance_symbols
from decision import kwon_strategy_decision

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('crypto_signal_bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Log startup configuration
logger.info("Starting Crypto Signal Bot...")

class CryptoSignalBot:
    def __init__(self):
        """Initialize the crypto signal bot"""
        # Telegram bot configuration
        self.telegram_token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.telegram_chat_id = os.getenv('TELEGRAM_CHAT_ID')
        
        if not self.telegram_token or not self.telegram_chat_id:
            raise ValueError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set in .env file")
        
        self.bot = Bot(token=self.telegram_token)
        
        # Log deployment environment
        logger.info(f"Bot initialized on platform: {os.environ.get('RENDER', 'local')}")
        logger.info(f"Python version: {os.sys.version}")
        logger.info(f"Working directory: {os.getcwd()}")
        
        # Trading parameters
        self.interval = "1w"  # Weekly candles as requested
        self.tp_ratio = float(os.getenv('TP_RATIO', '0.1'))  # 10% default
        self.sl_ratio = float(os.getenv('SL_RATIO', '0.05'))  # 5% default
        
        # Market cap filter parameters
        self.min_market_cap = float(os.getenv('MIN_MARKET_CAP', '150000000'))  # 150M default
        self.max_market_cap = float(os.getenv('MAX_MARKET_CAP', '20000000000'))  # 20B default
        self.cmc_max_pages = int(os.getenv('CMC_MAX_PAGES', '5'))  # Number of pages to fetch from CMC
        
        # Track sent signals to avoid duplicates
        self.sent_signals = {}
        self.signal_expiry_hours = 168  # 1 week for weekly signals
        
        # API rate limit tracking
        self.api_ban_until = None  # Timestamp until which API is banned
        self.consecutive_api_errors = 0
        self.max_retries = 10
        
        logger.info("CryptoSignalBot initialized successfully")
    
    def handle_api_error(self, error_msg: str) -> int:
        """Handle API errors with exponential backoff"""
        self.consecutive_api_errors += 1
        
        # Check if it's a ban (usually 418 or 429 with longer ban)
        if "418" in str(error_msg) or "banned" in error_msg.lower():
            # API ban detected - wait 1 hour
            self.api_ban_until = datetime.now() + timedelta(hours=1)
            logger.error(f"API ban detected. Will retry after {self.api_ban_until}")
            return 3600  # 1 hour in seconds
        
        # Exponential backoff for rate limits
        wait_time = min(2 ** self.consecutive_api_errors, 600)  # Max 10 minutes
        logger.warning(f"API error #{self.consecutive_api_errors}. Waiting {wait_time} seconds...")
        return wait_time
    
    def reset_error_counter(self):
        """Reset error counter on successful API call"""
        if self.consecutive_api_errors > 0:
            logger.info("API calls successful, resetting error counter")
            self.consecutive_api_errors = 0
    
    async def wait_if_banned(self) -> bool:
        """Check if API is banned and wait if necessary"""
        if self.api_ban_until and datetime.now() < self.api_ban_until:
            wait_seconds = (self.api_ban_until - datetime.now()).total_seconds()
            logger.warning(f"API is banned. Waiting {wait_seconds:.0f} seconds...")
            await asyncio.sleep(wait_seconds)
            self.api_ban_until = None
            return True
        return False
    
    def get_filtered_symbols(self) -> List[str]:
        """Get symbols filtered by market cap in real-time with retry logic"""
        logger.info("Fetching real-time market cap data...")
        
        # Always try to get fresh data from CoinMarketCap
        for attempt in range(self.max_retries):
            try:
                # Fetch coins from CoinMarketCap
                coins = fetch_coinmarketcap_coins_multi_pages(
                    min_cap=self.min_market_cap,
                    max_cap=self.max_market_cap,
                    max_pages=self.cmc_max_pages
                )
                
                if not coins:
                    logger.warning("No coins found with specified market cap criteria")
                    continue
                
                # Convert to Binance symbols
                symbols = []
                for coin in coins:
                    cmc_symbol = coin.get("symbol", "")
                    if cmc_symbol:
                        binance_symbol = cmc_symbol.upper() + "USDT"
                        symbols.append(binance_symbol)
                
                # Try to get valid Binance trading pairs
                try:
                    valid_binance = get_valid_binance_symbols()
                    if valid_binance:  # Only filter if we got valid symbols
                        filtered_symbols = [sym for sym in symbols if sym in valid_binance]
                        logger.info(f"Found {len(filtered_symbols)} symbols after Binance filtering")
                        self.reset_error_counter()
                        return filtered_symbols
                    else:
                        # If Binance API is blocked, use all CMC symbols
                        logger.warning("Cannot verify Binance pairs, using all CMC symbols")
                        return symbols[:100]  # Limit to top 100 to avoid too many requests
                except Exception as binance_error:
                    logger.warning(f"Binance API error: {binance_error}, using CMC symbols only")
                    return symbols[:100]  # Use top 100 CMC symbols
                    
            except Exception as e:
                wait_time = self.handle_api_error(str(e))
                
                if attempt < self.max_retries - 1:
                    time.sleep(wait_time)
                else:
                    logger.error(f"CMC API failed after {self.max_retries} attempts: {e}")
        
        # If everything fails, use a hardcoded list of major coins
        logger.warning("All APIs failed, using hardcoded major coins")
        return [
            "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
            "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "DOTUSDT", "MATICUSDT",
            "LINKUSDT", "UNIUSDT", "ATOMUSDT", "LTCUSDT", "ETCUSDT",
            "XLMUSDT", "NEARUSDT", "ALGOUSDT", "FILUSDT", "VETUSDT"
        ]
    
    async def send_telegram_message(self, message: str, parse_mode: str = 'Markdown'):
        """Send message to Telegram"""
        try:
            await self.bot.send_message(
                chat_id=self.telegram_chat_id,
                text=message,
                parse_mode=parse_mode
            )
            logger.info(f"Telegram message sent: {message[:50]}...")
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
    
    def check_single_symbol(self, symbol: str) -> Optional[Dict]:
        """Check a single symbol for buy signals with retry logic"""
        for attempt in range(3):  # Retry up to 3 times per symbol
            try:
                # Fetch candles (need at least 35 for EMA calculation + analysis window)
                df = fetch_candles(symbol, self.interval, limit=60)
                
                if df.empty or len(df) < 35:
                    logger.warning(f"Insufficient data for {symbol}")
                    return None
                
                # Check for signal using the kwon strategy
                signal = kwon_strategy_decision(df, self.interval, self.tp_ratio, self.sl_ratio)
                
                if signal['signal'] == 'BUY':
                    logger.info(f"BUY signal detected for {symbol}")
                    return {
                        'symbol': symbol,
                        'entry_price': signal['entry_price'],
                        'tp_price': signal['tp_price'],
                        'sl_price': signal['sl_price'],
                        'ema_period': signal['ema_period'],
                        'current_price': df['close'].iloc[-1],
                        'timestamp': datetime.now()
                    }
                
                return None
                
            except Exception as e:
                if "429" in str(e) or "418" in str(e):
                    wait_time = self.handle_api_error(str(e))
                    if attempt < 2:
                        logger.warning(f"Rate limit hit for {symbol}, waiting {wait_time}s...")
                        time.sleep(wait_time)
                        continue
                logger.error(f"Error checking {symbol}: {e}")
                return None
        
        return None
    
    async def scan_all_symbols(self):
        """Scan all symbols for buy signals"""
        # Check if API is banned before starting
        await self.wait_if_banned()
        
        # Get real-time filtered symbols
        symbols_to_scan = self.get_filtered_symbols()
        
        if not symbols_to_scan:
            logger.error("No symbols to scan. Check API connection.")
            return
        
        logger.info(f"Starting scan of {len(symbols_to_scan)} symbols (filtered by market cap)...")
        
        signals_found = []
        
        for i, symbol in enumerate(symbols_to_scan):
            # Check if API got banned during scan
            if await self.wait_if_banned():
                logger.info("Resuming scan after API ban wait...")
            
            # Check if we've already sent a signal for this symbol recently
            if symbol in self.sent_signals:
                last_sent = self.sent_signals[symbol]
                hours_passed = (datetime.now() - last_sent).total_seconds() / 3600
                if hours_passed < self.signal_expiry_hours:
                    continue
            
            # Check for signal
            signal = self.check_single_symbol(symbol)
            
            if signal:
                signals_found.append(signal)
                self.sent_signals[symbol] = datetime.now()
                
                # Send individual signal notification
                await self.send_signal_notification(signal)
            
            # Adaptive delay based on error rate
            if self.consecutive_api_errors > 5:
                await asyncio.sleep(2.0)  # Slower when hitting limits
            elif self.consecutive_api_errors > 0:
                await asyncio.sleep(1.0)
            else:
                await asyncio.sleep(0.5)  # Normal speed
            
            # Progress update every 20 symbols
            if (i + 1) % 20 == 0:
                logger.info(f"Progress: {i + 1}/{len(symbols_to_scan)} symbols scanned")
        
        logger.info(f"Scan complete. Found {len(signals_found)} signals.")
        
        # Send summary if multiple signals found
        if len(signals_found) > 1:
            await self.send_summary_notification(signals_found)
    
    async def send_signal_notification(self, signal: Dict):
        """Send formatted signal notification to Telegram"""
        message = f"""
🚨 *CRYPTO BUY SIGNAL* 🚨

📊 *Symbol:* {signal['symbol']}
📅 *Timeframe:* Weekly (1W)
💹 *Strategy:* Kwon Strategy (EMA {signal['ema_period']})

💰 *Entry Price:* ${signal['entry_price']:.8f}
📈 *Current Price:* ${signal['current_price']:.8f}
🎯 *Take Profit:* ${signal['tp_price']:.8f} (+{self.tp_ratio*100:.1f}%)
🛑 *Stop Loss:* ${signal['sl_price']:.8f} (-{self.sl_ratio*100:.1f}%)

⏰ *Signal Time:* {signal['timestamp'].strftime('%Y-%m-%d %H:%M:%S')} UTC

⚠️ *Note:* This is an automated signal. Always do your own research before trading.
        """
        
        await self.send_telegram_message(message)
    
    async def send_summary_notification(self, signals: List[Dict]):
        """Send summary of multiple signals"""
        message = f"""
📊 *SIGNAL SUMMARY* 📊

Found *{len(signals)}* buy signals in this scan:

"""
        for signal in signals:
            message += f"• {signal['symbol']} - Entry: ${signal['entry_price']:.8f}\n"
        
        message += "\n_Check individual messages for detailed information._"
        
        await self.send_telegram_message(message)
    
    async def send_startup_notification(self):
        """Send notification when bot starts"""
        # Get initial symbol count
        initial_symbols = self.get_filtered_symbols()
        
        message = f"""
🤖 *Crypto Signal Bot Started* 🤖

✅ Bot is now active with real-time market cap filtering
📊 Timeframe: Weekly (1W)
🎯 TP: {self.tp_ratio*100:.1f}% | SL: {self.sl_ratio*100:.1f}%
💰 Market Cap Range: ${self.min_market_cap/1e6:.0f}M - ${self.max_market_cap/1e9:.1f}B
📈 Initial symbols found: {len(initial_symbols)}

The bot will check for signals every hour with fresh market cap data.
        """
        await self.send_telegram_message(message)
    
    async def send_daily_status(self):
        """Send daily status update"""
        # Get current symbol count
        current_symbols = self.get_filtered_symbols()
        
        message = f"""
📅 *Daily Status Update* 📅

✅ Bot is running normally
📊 Currently monitoring: {len(current_symbols)} pairs
💰 Market Cap Filter: ${self.min_market_cap/1e6:.0f}M - ${self.max_market_cap/1e9:.1f}B
🕐 Last scan: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC
📈 Active signals: {len(self.sent_signals)}
        """
        await self.send_telegram_message(message)
    
    def run_async_task(self, coro):
        """Helper to run async tasks in sync context"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()
    
    def scheduled_scan(self):
        """Wrapper for scheduled scanning"""
        self.run_async_task(self.scan_all_symbols())
    
    def scheduled_daily_status(self):
        """Wrapper for scheduled daily status"""
        self.run_async_task(self.send_daily_status())
    
    def run(self):
        """Main bot loop"""
        logger.info("Starting Crypto Signal Bot...")
        
        # Send startup notification
        self.run_async_task(self.send_startup_notification())
        
        # Initial scan
        self.run_async_task(self.scan_all_symbols())
        
        # Schedule regular scans
        # Since we're using weekly candles, hourly checks are sufficient
        schedule.every().hour.do(self.scheduled_scan)
        
        # Daily status update at 12:00 UTC
        schedule.every().day.at("12:00").do(self.scheduled_daily_status)
        
        logger.info("Bot is running. Press Ctrl+C to stop.")
        
        # Main loop
        while True:
            try:
                schedule.run_pending()
                time.sleep(60)  # Check schedule every minute
            except KeyboardInterrupt:
                logger.info("Bot stopped by user")
                break
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                
                # If we're banned, wait appropriately
                if self.api_ban_until and datetime.now() < self.api_ban_until:
                    wait_seconds = (self.api_ban_until - datetime.now()).total_seconds()
                    logger.info(f"API banned, waiting {wait_seconds:.0f} seconds...")
                    time.sleep(max(wait_seconds, 300))
                else:
                    time.sleep(300)  # Wait 5 minutes before retrying

def main():
    """Main entry point"""
    try:
        bot = CryptoSignalBot()
        bot.run()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        raise

if __name__ == "__main__":
    main()