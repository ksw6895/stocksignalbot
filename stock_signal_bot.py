#!/usr/bin/env python3
import logging
import time
import schedule
import asyncio
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, ContextTypes
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import json
import signal
import sys
import traceback
import threading

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
        
        self.chat_id = TELEGRAM_CHAT_ID
        self.data_fetcher = StockDataFetcher()
        self.strategy = UpperSectionStrategy()
        
        # Initialize Telegram application
        self.application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        self.bot = self.application.bot
        
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
        
        # Configuration
        self.scan_interval = 14400  # 4 hours
        self.min_market_cap = 500_000_000
        self.max_market_cap = 50_000_000_000
        self.is_scanning = False
        
        # Setup command handlers
        self.setup_handlers()
    
    def setup_handlers(self):
        """Setup Telegram command handlers"""
        self.application.add_handler(CommandHandler("start", self.cmd_start))
        self.application.add_handler(CommandHandler("help", self.cmd_help))
        self.application.add_handler(CommandHandler("status", self.cmd_status))
        self.application.add_handler(CommandHandler("scan", self.cmd_scan))
        self.application.add_handler(CommandHandler("caprange", self.cmd_caprange))
        self.application.add_handler(CommandHandler("interval", self.cmd_interval))
        self.application.add_handler(CommandHandler("history", self.cmd_history))
        self.application.add_handler(CommandHandler("clear", self.cmd_clear))
    
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        message = "🚀 *Upper Section Strategy Bot*\n\n"
        message += "Welcome! This bot monitors NASDAQ stocks for Upper Section patterns.\n\n"
        message += "Type /help to see available commands."
        await update.message.reply_text(message, parse_mode='Markdown')
    
    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        message = "📚 *Available Commands:*\n\n"
        message += "/start - Start the bot\n"
        message += "/help - Show this help message\n"
        message += "/status - Show bot status and statistics\n"
        message += "/scan - Trigger an immediate scan\n"
        message += "/caprange [min] [max] - Set market cap range (in millions)\n"
        message += "  Example: /caprange 500 50000\n"
        message += "/interval [hours] - Set scan interval\n"
        message += "  Example: /interval 2\n"
        message += "/history - Show recent signals\n"
        message += "/clear - Clear signal history\n"
        await update.message.reply_text(message, parse_mode='Markdown')
    
    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command"""
        uptime = datetime.now() - self.start_time
        hours = uptime.total_seconds() / 3600
        days = hours / 24
        
        message = "📊 *Bot Status*\n\n"
        message += f"• Uptime: {days:.1f} days ({hours:.1f} hours)\n"
        message += f"• Total Scans: {self.total_scans}\n"
        message += f"• Signals Found: {self.total_signals}\n"
        message += f"• Stocks Monitored: ~{len(self.data_fetcher.cached_stocks)}\n"
        message += f"• API Requests: {self.data_fetcher.fmp_client.request_count}\n"
        message += f"• Scan Interval: {self.scan_interval/3600:.1f} hours\n"
        message += f"• Market Cap Range: ${self.min_market_cap/1e6:.0f}M - ${self.max_market_cap/1e9:.0f}B\n"
        
        if self.is_scanning:
            message += f"\n⚙️ *Currently scanning...*\n"
        
        if self.last_scan_time:
            next_scan = self.last_scan_time + timedelta(seconds=self.scan_interval)
            message += f"\n⏰ Last Scan: {self.last_scan_time.strftime('%Y-%m-%d %H:%M:%S')}"
            message += f"\n⏰ Next Scan: {next_scan.strftime('%Y-%m-%d %H:%M:%S')}"
        
        await update.message.reply_text(message, parse_mode='Markdown')
    
    async def cmd_scan(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /scan command - trigger immediate scan"""
        if self.is_scanning:
            await update.message.reply_text("⚠️ A scan is already in progress. Please wait...")
            return
        
        await update.message.reply_text("🔍 Starting immediate scan...")
        
        # Run scan in background thread
        thread = threading.Thread(target=self.scan_for_signals)
        thread.start()
    
    async def cmd_caprange(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /caprange command - set market cap range"""
        try:
            if len(context.args) != 2:
                await update.message.reply_text(
                    "Usage: /caprange [min_millions] [max_millions]\n"
                    "Example: /caprange 500 50000"
                )
                return
            
            min_cap = float(context.args[0]) * 1_000_000
            max_cap = float(context.args[1]) * 1_000_000
            
            if min_cap <= 0 or max_cap <= 0 or min_cap >= max_cap:
                await update.message.reply_text("❌ Invalid range. Min must be less than max and both must be positive.")
                return
            
            self.min_market_cap = min_cap
            self.max_market_cap = max_cap
            self.data_fetcher.min_market_cap = min_cap
            self.data_fetcher.max_market_cap = max_cap
            
            message = f"✅ Market cap range updated:\n"
            message += f"Min: ${min_cap/1e6:.0f}M\n"
            message += f"Max: ${max_cap/1e9:.1f}B"
            await update.message.reply_text(message)
            
        except ValueError:
            await update.message.reply_text("❌ Invalid input. Please use numbers only.")
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)}")
    
    async def cmd_interval(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /interval command - set scan interval"""
        try:
            if len(context.args) != 1:
                await update.message.reply_text(
                    "Usage: /interval [hours]\n"
                    "Example: /interval 2"
                )
                return
            
            hours = float(context.args[0])
            if hours < 0.5 or hours > 24:
                await update.message.reply_text("❌ Interval must be between 0.5 and 24 hours.")
                return
            
            self.scan_interval = int(hours * 3600)
            
            message = f"✅ Scan interval updated to {hours:.1f} hours"
            await update.message.reply_text(message)
            
        except ValueError:
            await update.message.reply_text("❌ Invalid input. Please use a number.")
        except Exception as e:
            await update.message.reply_text(f"❌ Error: {str(e)}")
    
    async def cmd_history(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /history command - show recent signals"""
        if not self.signals_sent:
            await update.message.reply_text("No signals in history yet.")
            return
        
        recent_signals = sorted(list(self.signals_sent))[-10:]  # Last 10 signals
        
        message = "📜 *Recent Signals:*\n\n"
        for signal in recent_signals:
            parts = signal.split('_')
            if len(parts) >= 2:
                symbol = parts[0]
                date = parts[1][:10]
                message += f"• {symbol} - {date}\n"
        
        await update.message.reply_text(message, parse_mode='Markdown')
    
    async def cmd_clear(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /clear command - clear signal history"""
        self.signals_sent.clear()
        self.save_signals_history()
        await update.message.reply_text("✅ Signal history cleared.")
    
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
            message += f"*Company:* {stock_info.get('companyName', 'N/A')}\n"
            message += f"*Sector:* {stock_info.get('sector', 'N/A')}\n"
            
            if stock_info.get('marketCap'):
                market_cap = stock_info['marketCap']
                if market_cap >= 1e9:
                    message += f"*Market Cap:* ${market_cap/1e9:.1f}B\n"
                else:
                    message += f"*Market Cap:* ${market_cap/1e6:.0f}M\n"
        
        message += f"\n📊 *Entry Setup:*\n"
        message += f"• Entry Price: ${signal['entry_price']:.2f}\n"
        message += f"• Take Profit: ${signal['tp_price']:.2f} (+{(signal['tp_ratio']*100):.0f}%)\n"
        message += f"• Stop Loss: ${signal['sl_price']:.2f} (-{(signal['sl_ratio']*100):.0f}%)\n"
        
        message += f"\n📈 *Signal Details:*\n"
        message += f"• Pattern: {signal.get('pattern', 'N/A')}\n"
        message += f"• Peak Date: {signal.get('peak_date', 'N/A')}\n"
        message += f"• EMA Period: {signal.get('ema_period', 'N/A')}\n"
        message += f"• Current Price: ${signal.get('current_price', 0):.2f}\n"
        
        message += f"\n⏰ Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC"
        
        return message
    
    def scan_for_signals(self):
        if self.is_scanning:
            logger.warning("Scan already in progress, skipping...")
            return
        
        self.is_scanning = True
        logger.info("=" * 50)
        logger.info("Starting Upper Section Strategy scan (Weekly)...")
        
        try:
            self.last_scan_time = datetime.now()
            self.total_scans += 1
            
            stocks = self.data_fetcher.get_nasdaq_stocks(
                min_market_cap=self.min_market_cap,
                max_market_cap=self.max_market_cap
            )
            
            if not stocks:
                logger.warning("No stocks found to analyze")
                return
            
            logger.info(f"Analyzing {len(stocks)} NASDAQ stocks with weekly data...")
            
            def process_stock(stock: Dict) -> Optional[Dict]:
                try:
                    symbol = stock['symbol']
                    
                    weekly_data = self.data_fetcher.get_historical_weekly(symbol)
                    if not weekly_data:
                        return None
                    
                    signal = self.strategy.analyze(weekly_data, symbol)
                    
                    if signal:
                        stock_info = self.data_fetcher.get_company_profile(symbol)
                        signal['stock_info'] = stock_info
                        signal['current_price'] = stock.get('price', 0)
                        return signal
                    
                    return None
                    
                except Exception as e:
                    logger.error(f"Error processing {stock.get('symbol', 'unknown')}: {e}")
                    return None
            
            results = self.data_fetcher.process_stocks_in_batches(
                stocks, process_stock, batch_size=20
            )
            
            signals = [r for r in results if r is not None]
            
            new_signals = []
            for signal in signals:
                signal_key = f"{signal['symbol']}_{datetime.now().isoformat()}"
                if signal['symbol'] not in [s.split('_')[0] for s in self.signals_sent]:
                    new_signals.append(signal)
            
            if new_signals:
                logger.info(f"Found {len(new_signals)} new signals!")
                for signal in new_signals:
                    self.process_signal(signal)
            else:
                logger.info("No new signals found in this scan")
            
            logger.info(f"Total API requests made: {self.data_fetcher.fmp_client.request_count}")
            
        except Exception as e:
            logger.error(f"Error during scan: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
        finally:
            self.is_scanning = False
    
    def process_signal(self, signal: Dict):
        try:
            symbol = signal['symbol']
            signal_key = f"{symbol}_{datetime.now().isoformat()}"
            
            if signal_key in self.signals_sent:
                return
            
            message = self.format_signal_message(signal, signal.get('stock_info'))
            
            # Send message synchronously
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
            
            asyncio.run(self.send_telegram_message(message))
            
        except Exception as e:
            logger.error(f"Error sending status update: {e}")
    
    async def run_bot(self):
        """Run the Telegram bot"""
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()
        
        logger.info("Telegram bot started, listening for commands...")
        
        # Keep the bot running
        while self.is_running:
            await asyncio.sleep(1)
        
        await self.application.updater.stop()
        await self.application.stop()
        await self.application.shutdown()
    
    def run_scheduler(self):
        """Run the scheduler in a separate thread"""
        # Run initial scan
        self.scan_for_signals()
        
        # Schedule scans
        schedule.every(self.scan_interval).seconds.do(self.scan_for_signals)
        
        # Send status update twice daily
        schedule.every().day.at("09:00").do(self.send_status_update)
        schedule.every().day.at("21:00").do(self.send_status_update)
        
        logger.info(f"Scheduled scans every {self.scan_interval/3600:.1f} hours")
        
        while self.is_running:
            try:
                schedule.run_pending()
                time.sleep(60)
            except Exception as e:
                logger.error(f"Error in scheduler: {e}")
                time.sleep(60)
    
    def run(self):
        logger.info("=" * 50)
        logger.info("Upper Section Strategy Bot Started")
        logger.info("=" * 50)
        
        startup_message = "🚀 *Upper Section Strategy Bot Started*\n\n"
        startup_message += "Monitoring NASDAQ stocks for Upper Section patterns using weekly data.\n"
        startup_message += f"• Strategy: Single Peak + Bearish Pattern + EMA Entry\n"
        startup_message += f"• Timeframe: Weekly (1W)\n"
        startup_message += f"• Scan Interval: Every {self.scan_interval/3600:.1f} hours\n"
        startup_message += f"• TP/SL: +10% / -5%\n"
        startup_message += "\nType /help to see available commands."
        
        asyncio.run(self.send_telegram_message(startup_message))
        
        # Start scheduler in background thread
        scheduler_thread = threading.Thread(target=self.run_scheduler)
        scheduler_thread.daemon = True
        scheduler_thread.start()
        
        # Run Telegram bot in main thread
        try:
            asyncio.run(self.run_bot())
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt")
        finally:
            self.save_signals_history()
            logger.info("Upper Section Strategy Bot stopped")


if __name__ == "__main__":
    bot = StockSignalBot()
    bot.run()