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
    SCAN_INTERVAL, SCAN_DURING_MARKET_HOURS_ONLY,
    validate_config, format_number
)
from stocks import StockDataFetcher
from decision import StockKwonStrategy

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
        self.strategy = StockKwonStrategy()
        
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
            cutoff_date = datetime.now() - timedelta(days=7)
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
        
        message = f"🎯 *STOCK BUY SIGNAL*\n\n"
        message += f"*Symbol:* {symbol}\n"
        
        if stock_info:
            message += f"*Company:* {stock_info.get('name', 'N/A')}\n"
            message += f"*Sector:* {stock_info.get('sector', 'N/A')}\n"
            message += f"*Market Cap:* {format_number(stock_info.get('marketCap', 0))}\n"
        
        message += f"\n📊 *Signal Details:*\n"
        message += f"• Current Price: ${signal['current_price']}\n"
        message += f"• Entry Price: ${signal['entry_price']}\n"
        message += f"• Take Profit: ${signal['tp_price']} (+{signal['tp_price']/signal['entry_price']*100-100:.1f}%)\n"
        message += f"• Stop Loss: ${signal['sl_price']} (-{100-signal['sl_price']/signal['entry_price']*100:.1f}%)\n"
        
        message += f"\n📈 *Technical Analysis:*\n"
        message += f"• Peak Price: ${signal['peak_price']} ({signal['peak_weeks_ago']} weeks ago)\n"
        message += f"• Pullback: {signal['price_from_peak']}%\n"
        message += f"• EMA{signal['ema_type']}: ${signal[f'ema_{\"short\" if signal[\"ema_type\"] == 20 else \"long\"}']}\n"
        message += f"• Volume Ratio: {signal['volume_ratio']}x avg\n"
        message += f"• Signal Strength: {signal['signal_strength']}\n"
        message += f"• Risk/Reward: {signal['risk_reward']}:1\n"
        
        message += f"\n⏰ *Time:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} EST"
        
        return message
    
    def scan_for_signals(self):
        if not self.is_running:
            return
        
        try:
            if SCAN_DURING_MARKET_HOURS_ONLY and not self.data_fetcher.is_market_open():
                logger.info("Market is closed, skipping scan")
                return
            
            logger.info("=" * 50)
            logger.info("Starting stock market scan...")
            self.total_scans += 1
            
            stocks = self.data_fetcher.get_filtered_stocks()
            
            if not stocks:
                logger.warning("No stocks found matching criteria")
                return
            
            logger.info(f"Analyzing {len(stocks)} NASDAQ stocks...")
            
            signals_found = []
            
            def process_stock(stock):
                symbol = stock['symbol']
                
                candles = self.data_fetcher.fetch_weekly_candles(symbol, 52)
                if not candles:
                    return None
                
                signal = self.strategy.analyze(candles, symbol)
                
                if signal and self.strategy.validate_signal(signal):
                    signal_key = f"{symbol}_{datetime.now().date().isoformat()}"
                    
                    if signal_key not in self.signals_sent:
                        stock_info = self.data_fetcher.get_stock_info(symbol)
                        signal['stock_info'] = stock_info
                        return signal
                
                return None
            
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
            
            remaining = self.data_fetcher.fmp_client.get_remaining_requests()
            logger.info(f"API requests remaining today: {remaining}")
            
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
            
            logger.info(f"Signal sent for {symbol}")
            
            if len(self.signals_sent) % 10 == 0:
                self.save_signals_history()
            
        except Exception as e:
            logger.error(f"Error processing signal for {signal.get('symbol', 'unknown')}: {e}")
    
    def send_daily_summary(self):
        try:
            uptime = datetime.now() - self.start_time
            hours = uptime.total_seconds() / 3600
            
            message = "📊 *Daily Stock Bot Summary*\n\n"
            message += f"• Uptime: {hours:.1f} hours\n"
            message += f"• Total Scans: {self.total_scans}\n"
            message += f"• Signals Sent: {self.total_signals}\n"
            message += f"• Stocks Monitored: ~{len(self.data_fetcher.cached_stocks)}\n"
            
            remaining = self.data_fetcher.fmp_client.get_remaining_requests()
            message += f"• API Requests Remaining: {remaining}\n"
            
            market_hours = self.data_fetcher.get_market_hours()
            message += f"\n🏛️ *Market Status:*\n"
            message += f"• {'OPEN' if market_hours.get('isTheMarketOpen') else 'CLOSED'}\n"
            message += f"• Hours: {market_hours.get('marketOpen', 'N/A')} - {market_hours.get('marketClose', 'N/A')} EST\n"
            
            if self.last_scan_time:
                message += f"\n⏰ Last Scan: {self.last_scan_time.strftime('%H:%M:%S')}"
            
            import asyncio
            asyncio.run(self.send_telegram_message(message))
            
        except Exception as e:
            logger.error(f"Error sending daily summary: {e}")
    
    def run(self):
        logger.info("=" * 50)
        logger.info("Stock Signal Bot Started")
        logger.info("=" * 50)
        
        startup_message = "🚀 *Stock Signal Bot Started*\n\n"
        startup_message += "Monitoring NASDAQ stocks for buy signals using Kwon Strategy.\n"
        startup_message += f"Scan interval: Every {SCAN_INTERVAL//60} minutes"
        if SCAN_DURING_MARKET_HOURS_ONLY:
            startup_message += " (market hours only)"
        
        import asyncio
        asyncio.run(self.send_telegram_message(startup_message))
        
        self.scan_for_signals()
        
        schedule.every(SCAN_INTERVAL).seconds.do(self.scan_for_signals)
        
        schedule.every().day.at("16:30").do(self.send_daily_summary)
        
        logger.info(f"Scheduled scans every {SCAN_INTERVAL} seconds")
        
        while self.is_running:
            try:
                schedule.run_pending()
                time.sleep(1)
            except KeyboardInterrupt:
                logger.info("Received keyboard interrupt")
                break
            except Exception as e:
                logger.error(f"Unexpected error in main loop: {e}")
                time.sleep(60)
        
        self.save_signals_history()
        logger.info("Stock Signal Bot stopped")


if __name__ == "__main__":
    bot = StockSignalBot()
    bot.run()