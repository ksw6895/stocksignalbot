#!/usr/bin/env python3
import logging
import time
import schedule
import telegram
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import json
import signal
import sys
import traceback

from config import (
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
    validate_config, format_number
)
from stocks import StockDataFetcher
from decision import UpperSectionStrategy

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class StockSignalBot:
    def __init__(self):
        validate_config()
        
        self.bot = telegram.Bot(token=TELEGRAM_BOT_TOKEN)
        self.chat_id = TELEGRAM_CHAT_ID
        self.data_fetcher = StockDataFetcher()
        self.strategy = UpperSectionStrategy()
        
        self.signals_sent = set()
        self.signals_file = "signals_sent.json"
        self.load_signals_history()
        
        self.last_scan_time = None
        self.total_scans = 0
        self.total_signals = 0
        self.start_time = datetime.now()
        
        self.is_running = True
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
        # Set scan interval to 4 hours (14400 seconds)
        self.scan_interval = 14400  # 4 hours
    
    def _signal_handler(self, signum, frame):
        logger.info(f"Received signal {signum}. Shutting down gracefully...")
        self.is_running = False
        self.save_signals_history()
        sys.exit(0)
    
    def load_signals_history(self):
        try:
            with open(self.signals_file, 'r') as f:
                data = json.load(f)
                self.signals_sent = set(data.get('signals', []))
                logger.info(f"Loaded {len(self.signals_sent)} historical signals")
        except FileNotFoundError:
            logger.info("No signals history file found, starting fresh")
        except Exception as e:
            logger.error(f"Error loading signals history: {e}")
    
    def save_signals_history(self):
        try:
            cutoff_date = datetime.now() - timedelta(days=30)  # Keep 30 days of history
            recent_signals = [
                s for s in self.signals_sent 
                if '_' in s and datetime.fromisoformat(s.split('_')[1]) > cutoff_date
            ]
            
            with open(self.signals_file, 'w') as f:
                json.dump({'signals': list(recent_signals)}, f)
            logger.info(f"Saved {len(recent_signals)} recent signals")
        except Exception as e:
            logger.error(f"Error saving signals history: {e}")
    
    async def send_telegram_message(self, message: str, parse_mode: str = 'Markdown'):
        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=message,
                parse_mode=parse_mode,
                disable_web_page_preview=True
            )
            logger.info("Telegram message sent successfully")
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
    
    def format_signal_message(self, signal: Dict, stock_info: Optional[Dict] = None) -> str:
        symbol = signal['symbol']
        
        message = f"🎯 *UPPER SECTION SIGNAL*\n\n"
        message += f"*Symbol:* {symbol}\n"
        
        if stock_info:
            message += f"*Company:* {stock_info.get('name', 'N/A')}\n"
            message += f"*Sector:* {stock_info.get('sector', 'N/A')}\n"
            message += f"*Market Cap:* {format_number(stock_info.get('marketCap', 0))}\n"
        
        message += f"\n📊 *Signal Details:*\n"
        message += f"• Pattern: {signal.get('pattern', 'N/A').upper()}\n"
        message += f"• Decision: {signal.get('decision', 'N/A')}\n"
        message += f"• Current Price: ${signal['current_price']}\n"
        message += f"• Entry Price (EMA{signal['ema_period']}): ${signal['entry_price']}\n"
        message += f"• Take Profit: ${signal['tp_price']} (+10%)\n"
        message += f"• Stop Loss: ${signal['sl_price']} (-5%)\n"
        
        message += f"\n📈 *Technical Analysis:*\n"
        message += f"• Peak High: ${signal.get('peak_high', 0)}\n"
        message += f"• Pullback from Peak: {signal.get('price_from_peak', 0)}%\n"
        message += f"• Current Low: ${signal.get('current_low', 0)}\n"
        message += f"• Current High: ${signal.get('current_high', 0)}\n"
        message += f"• Risk/Reward: {signal['risk_reward']}:1\n"
        
        if signal.get('volume', 0) > 0:
            message += f"• Volume: {format_number(signal['volume'])}\n"
        
        message += f"\n⏰ *Time:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC"
        message += f"\n📅 *Timeframe:* Weekly (1W)"
        
        return message
    
    def scan_for_signals(self):
        if not self.is_running:
            return
        
        try:
            logger.info("=" * 50)
            logger.info("Starting Upper Section Strategy scan (Weekly)...")
            self.total_scans += 1
            
            stocks = self.data_fetcher.get_filtered_stocks()
            
            if not stocks:
                logger.warning("No stocks found matching criteria")
                return
            
            logger.info(f"Analyzing {len(stocks)} NASDAQ stocks with weekly data...")
            
            signals_found = []
            
            def process_stock(stock):
                symbol = stock['symbol']
                
                # Fetch weekly candles (52 weeks = 1 year)
                candles = self.data_fetcher.fetch_weekly_candles(symbol, 52)
                if not candles or len(candles) < 35:
                    logger.debug(f"{symbol}: Insufficient weekly data")
                    return None
                
                # Analyze with Upper Section Strategy using weekly interval
                signal = self.strategy.analyze(candles, symbol, interval="1w")
                
                if signal and self.strategy.validate_signal(signal):
                    signal_key = f"{symbol}_{datetime.now().date().isoformat()}"
                    
                    if signal_key not in self.signals_sent:
                        stock_info = self.data_fetcher.get_stock_info(symbol)
                        signal['stock_info'] = stock_info
                        return signal
                
                return None
            
            # Process stocks in batches to manage memory
            results = self.data_fetcher.process_stocks_in_batches(
                stocks, process_stock, batch_size=20
            )
            
            for signal in results:
                if signal:
                    signals_found.append(signal)
            
            if signals_found:
                logger.info(f"Found {len(signals_found)} new signals!")
                for signal in signals_found:
                    self._process_signal(signal)
            else:
                logger.info("No new signals found in this scan")
            
            self.last_scan_time = datetime.now()
            
            logger.info(f"Total API requests made: {self.data_fetcher.fmp_client.request_count}")
            
        except Exception as e:
            logger.error(f"Error during scan: {e}")
            logger.error(traceback.format_exc())
    
    def _process_signal(self, signal: Dict):
        try:
            symbol = signal['symbol']
            signal_key = f"{symbol}_{datetime.now().date().isoformat()}"
            
            if signal_key in self.signals_sent:
                return
            
            message = self.format_signal_message(signal, signal.get('stock_info'))
            
            import asyncio
            asyncio.run(self.send_telegram_message(message))
            
            self.signals_sent.add(signal_key)
            self.total_signals += 1
            
            logger.info(f"Signal sent for {symbol} - Pattern: {signal.get('pattern')} - EMA{signal.get('ema_period')}")
            
            # Save history after every 5 signals
            if len(self.signals_sent) % 5 == 0:
                self.save_signals_history()
            
        except Exception as e:
            logger.error(f"Error processing signal for {signal.get('symbol', 'unknown')}: {e}")
    
    def send_status_update(self):
        try:
            uptime = datetime.now() - self.start_time
            hours = uptime.total_seconds() / 3600
            days = hours / 24
            
            message = "📊 *Upper Section Strategy Status*\n\n"
            message += f"• Uptime: {days:.1f} days ({hours:.1f} hours)\n"
            message += f"• Total Scans: {self.total_scans}\n"
            message += f"• Signals Found: {self.total_signals}\n"
            message += f"• Stocks Monitored: ~{len(self.data_fetcher.cached_stocks)}\n"
            message += f"• API Requests: {self.data_fetcher.fmp_client.request_count}\n"
            
            market_hours = self.data_fetcher.get_market_hours()
            message += f"\n🏛️ *Market Status:*\n"
            message += f"• {'OPEN' if market_hours.get('isTheMarketOpen') else 'CLOSED'}\n"
            
            if self.last_scan_time:
                next_scan = self.last_scan_time + timedelta(seconds=self.scan_interval)
                message += f"\n⏰ Last Scan: {self.last_scan_time.strftime('%Y-%m-%d %H:%M:%S')}"
                message += f"\n⏰ Next Scan: {next_scan.strftime('%Y-%m-%d %H:%M:%S')}"
            
            import asyncio
            asyncio.run(self.send_telegram_message(message))
            
        except Exception as e:
            logger.error(f"Error sending status update: {e}")
    
    def run(self):
        logger.info("=" * 50)
        logger.info("Upper Section Strategy Bot Started")
        logger.info("=" * 50)
        
        startup_message = "🚀 *Upper Section Strategy Bot Started*\n\n"
        startup_message += "Monitoring NASDAQ stocks for Upper Section patterns using weekly data.\n"
        startup_message += f"• Strategy: Single Peak + Bearish Pattern + EMA Entry\n"
        startup_message += f"• Timeframe: Weekly (1W)\n"
        startup_message += f"• Scan Interval: Every 4 hours\n"
        startup_message += f"• TP/SL: +10% / -5%\n"
        
        import asyncio
        asyncio.run(self.send_telegram_message(startup_message))
        
        # Run initial scan
        self.scan_for_signals()
        
        # Schedule scans every 4 hours
        schedule.every(self.scan_interval).seconds.do(self.scan_for_signals)
        
        # Send status update twice daily (at 9 AM and 9 PM UTC)
        schedule.every().day.at("09:00").do(self.send_status_update)
        schedule.every().day.at("21:00").do(self.send_status_update)
        
        logger.info(f"Scheduled scans every 4 hours ({self.scan_interval} seconds)")
        
        while self.is_running:
            try:
                schedule.run_pending()
                time.sleep(60)  # Check every minute
            except KeyboardInterrupt:
                logger.info("Received keyboard interrupt")
                break
            except Exception as e:
                logger.error(f"Unexpected error in main loop: {e}")
                time.sleep(60)
        
        self.save_signals_history()
        logger.info("Upper Section Strategy Bot stopped")


if __name__ == "__main__":
    bot = StockSignalBot()
    bot.run()