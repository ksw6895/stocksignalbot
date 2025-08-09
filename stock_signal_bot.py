#!/usr/bin/env python3
import logging
import time
import schedule
import requests
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
        
        self.bot_token = TELEGRAM_BOT_TOKEN
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
        
        # Configuration
        self.scan_interval = 14400  # 4 hours
        self.min_market_cap = 500_000_000
        self.max_market_cap = 50_000_000_000
        self.is_scanning = False
        
        # Initialize last_update_id before starting thread
        self.last_update_id = None
        
        # Start command handler thread
        self.command_thread = threading.Thread(target=self.poll_commands, daemon=True)
        self.command_thread.start()
    
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
            cutoff_date = datetime.now() - timedelta(days=30)
            recent_signals = [
                s for s in self.signals_sent 
                if '_' in s and datetime.fromisoformat(s.split('_')[1]) > cutoff_date
            ]
            
            with open(self.signals_file, 'w') as f:
                json.dump({'signals': list(recent_signals)}, f)
            logger.info(f"Saved {len(recent_signals)} recent signals")
        except Exception as e:
            logger.error(f"Error saving signals history: {e}")
    
    def send_telegram_message(self, message: str, parse_mode: str = 'Markdown'):
        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            payload = {
                'chat_id': self.chat_id,
                'text': message,
                'parse_mode': parse_mode,
                'disable_web_page_preview': True
            }
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code == 200:
                logger.info("Telegram message sent successfully")
            else:
                logger.error(f"Failed to send Telegram message: {response.text}")
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
    
    def get_updates(self, offset: Optional[int] = None):
        """Get updates from Telegram"""
        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/getUpdates"
            params = {'timeout': 30}
            if offset:
                params['offset'] = offset
            
            response = requests.get(url, params=params, timeout=35)
            if response.status_code == 200:
                return response.json().get('result', [])
            return []
        except Exception as e:
            logger.error(f"Error getting updates: {e}")
            return []
    
    def poll_commands(self):
        """Poll for Telegram commands"""
        logger.info("Starting Telegram command polling...")
        
        while self.is_running:
            try:
                updates = self.get_updates(self.last_update_id)
                
                for update in updates:
                    update_id = update.get('update_id')
                    if update_id:
                        self.last_update_id = update_id + 1
                    
                    message = update.get('message', {})
                    text = message.get('text', '')
                    chat_id = message.get('chat', {}).get('id')
                    
                    if text.startswith('/'):
                        self.handle_command(text, chat_id)
                
                time.sleep(1)
                
            except Exception as e:
                logger.error(f"Error in command polling: {e}")
                time.sleep(5)
    
    def handle_command(self, text: str, chat_id: int):
        """Handle Telegram commands"""
        try:
            parts = text.split()
            command = parts[0].lower()
            args = parts[1:] if len(parts) > 1 else []
            
            # Only respond to commands from authorized chat
            if str(chat_id) != str(self.chat_id):
                return
            
            if command == '/start':
                message = "🚀 *Upper Section Strategy Bot*\n\n"
                message += "Welcome! This bot monitors NASDAQ stocks for Upper Section patterns.\n\n"
                message += "Type /help to see available commands."
                self.send_telegram_message(message)
            
            elif command == '/help':
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
                self.send_telegram_message(message)
            
            elif command == '/status':
                self.send_status_message()
            
            elif command == '/scan':
                if self.is_scanning:
                    self.send_telegram_message("⚠️ A scan is already in progress. Please wait...")
                else:
                    self.send_telegram_message("🔍 Starting immediate scan...")
                    thread = threading.Thread(target=self.scan_for_signals)
                    thread.start()
            
            elif command == '/caprange':
                self.handle_caprange(args)
            
            elif command == '/interval':
                self.handle_interval(args)
            
            elif command == '/history':
                self.show_history()
            
            elif command == '/clear':
                self.signals_sent.clear()
                self.save_signals_history()
                self.send_telegram_message("✅ Signal history cleared.")
            
        except Exception as e:
            logger.error(f"Error handling command: {e}")
    
    def send_status_message(self):
        """Send status message"""
        uptime = datetime.now() - self.start_time
        hours = uptime.total_seconds() / 3600
        days = hours / 24
        
        message = "📊 *Bot Status*\n\n"
        message += f"• Uptime: {days:.1f} days ({hours:.1f} hours)\n"
        message += f"• Total Scans: {self.total_scans}\n"
        message += f"• Signals Found: {self.total_signals}\n"
        message += f"• Stocks Monitored: NASDAQ\n"
        message += f"• API Requests: {self.data_fetcher.fmp_client.request_count}\n"
        message += f"• Scan Interval: {self.scan_interval/3600:.1f} hours\n"
        message += f"• Market Cap Range: ${self.min_market_cap/1e6:.0f}M - ${self.max_market_cap/1e9:.0f}B\n"
        
        if self.is_scanning:
            message += f"\n⚙️ *Currently scanning...*\n"
        
        if self.last_scan_time:
            next_scan = self.last_scan_time + timedelta(seconds=self.scan_interval)
            message += f"\n⏰ Last Scan: {self.last_scan_time.strftime('%Y-%m-%d %H:%M:%S')}"
            message += f"\n⏰ Next Scan: {next_scan.strftime('%Y-%m-%d %H:%M:%S')}"
        
        self.send_telegram_message(message)
    
    def handle_caprange(self, args):
        """Handle caprange command"""
        try:
            if len(args) != 2:
                self.send_telegram_message(
                    "Usage: /caprange [min_millions] [max_millions]\n"
                    "Example: /caprange 500 50000"
                )
                return
            
            min_cap = float(args[0]) * 1_000_000
            max_cap = float(args[1]) * 1_000_000
            
            if min_cap <= 0 or max_cap <= 0 or min_cap >= max_cap:
                self.send_telegram_message("❌ Invalid range. Min must be less than max and both must be positive.")
                return
            
            self.min_market_cap = min_cap
            self.max_market_cap = max_cap
            self.data_fetcher.min_market_cap = min_cap
            self.data_fetcher.max_market_cap = max_cap
            
            message = f"✅ Market cap range updated:\n"
            message += f"Min: ${min_cap/1e6:.0f}M\n"
            message += f"Max: ${max_cap/1e9:.1f}B"
            self.send_telegram_message(message)
            
        except ValueError:
            self.send_telegram_message("❌ Invalid input. Please use numbers only.")
        except Exception as e:
            self.send_telegram_message(f"❌ Error: {str(e)}")
    
    def handle_interval(self, args):
        """Handle interval command"""
        try:
            if len(args) != 1:
                self.send_telegram_message(
                    "Usage: /interval [hours]\n"
                    "Example: /interval 2"
                )
                return
            
            hours = float(args[0])
            if hours < 0.5 or hours > 24:
                self.send_telegram_message("❌ Interval must be between 0.5 and 24 hours.")
                return
            
            self.scan_interval = int(hours * 3600)
            
            message = f"✅ Scan interval updated to {hours:.1f} hours"
            self.send_telegram_message(message)
            
        except ValueError:
            self.send_telegram_message("❌ Invalid input. Please use a number.")
        except Exception as e:
            self.send_telegram_message(f"❌ Error: {str(e)}")
    
    def show_history(self):
        """Show signal history"""
        if not self.signals_sent:
            self.send_telegram_message("No signals in history yet.")
            return
        
        recent_signals = sorted(list(self.signals_sent))[-10:]
        
        message = "📜 *Recent Signals:*\n\n"
        for signal in recent_signals:
            parts = signal.split('_')
            if len(parts) >= 2:
                symbol = parts[0]
                date = parts[1][:10]
                message += f"• {symbol} - {date}\n"
        
        self.send_telegram_message(message)
    
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
                    
                    weekly_data = self.data_fetcher.fetch_weekly_candles(symbol)
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
            
            # Send all signals, but track which ones are repeated
            repeated_signals = []
            new_signals = []
            for signal in signals:
                if signal['symbol'] in [s.split('_')[0] for s in self.signals_sent]:
                    repeated_signals.append(signal)
                else:
                    new_signals.append(signal)
            
            # Process all signals (new and repeated)
            all_signals_to_send = signals  # Send everything
            
            if all_signals_to_send:
                logger.info(f"Found {len(all_signals_to_send)} total signals ({len(new_signals)} new, {len(repeated_signals)} repeated)")
                for signal in all_signals_to_send:
                    self.process_signal(signal)
            else:
                logger.info("No signals found in this scan")
            
            logger.info(f"Total API requests made: {self.data_fetcher.fmp_client.request_count}")
            
            # Send scan completion summary
            self.send_scan_summary(stocks, signals, new_signals)
            
        except Exception as e:
            logger.error(f"Error during scan: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            # Send error summary
            self.send_error_summary(str(e))
        finally:
            self.is_scanning = False
    
    def process_signal(self, signal: Dict):
        try:
            symbol = signal['symbol']
            signal_key = f"{symbol}_{datetime.now().isoformat()}"
            
            # Check if this is a repeated signal
            is_repeated = symbol in [s.split('_')[0] for s in self.signals_sent]
            
            # Format message with repeated indicator if applicable
            message = self.format_signal_message(signal, signal.get('stock_info'))
            if is_repeated:
                message = "🔄 *[반복 신호]*\n" + message
            
            self.send_telegram_message(message)
            
            # Still add to history for tracking
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
            message += f"• Stocks Monitored: NASDAQ\n"
            message += f"• API Requests: {self.data_fetcher.fmp_client.request_count}\n"
            
            market_hours = self.data_fetcher.get_market_hours()
            message += f"\n🏛️ *Market Status:*\n"
            message += f"• {'OPEN' if market_hours.get('isTheMarketOpen') else 'CLOSED'}\n"
            
            if self.last_scan_time:
                next_scan = self.last_scan_time + timedelta(seconds=self.scan_interval)
                message += f"\n⏰ Last Scan: {self.last_scan_time.strftime('%Y-%m-%d %H:%M:%S')}"
                message += f"\n⏰ Next Scan: {next_scan.strftime('%Y-%m-%d %H:%M:%S')}"
            
            self.send_telegram_message(message)
            
        except Exception as e:
            logger.error(f"Error sending status update: {e}")
    
    def send_scan_summary(self, stocks: List[Dict], all_signals: List[Dict], new_signals: List[Dict]):
        """Send comprehensive scan completion summary"""
        try:
            scan_end_time = datetime.now()
            scan_duration = (scan_end_time - self.last_scan_time).total_seconds() if self.last_scan_time else 0
            
            # Build summary message
            message = "📊 *스캔 완료 보고서*\n"
            message += "=" * 30 + "\n\n"
            
            # Scan statistics
            message += "📈 *스캔 통계*\n"
            message += f"• 분석한 주식: {len(stocks)}개\n"
            message += f"• 패턴 감지: {len(all_signals)}개\n"
            message += f"• 새로운 신호: {len(new_signals)}개\n"
            message += f"• 소요 시간: {scan_duration:.1f}초\n\n"
            
            # API usage
            api_requests = self.data_fetcher.fmp_client.request_count
            remaining_requests = self.data_fetcher.fmp_client.get_remaining_requests()
            daily_limit = self.data_fetcher.fmp_client.daily_limit
            
            message += "🔌 *API 사용량*\n"
            message += f"• 사용: {api_requests}회\n"
            message += f"• 남은 요청: {remaining_requests}/{daily_limit}회\n"
            usage_percent = ((daily_limit - remaining_requests) / daily_limit) * 100
            message += f"• 일일 사용률: {usage_percent:.1f}%\n\n"
            
            # Signal summary
            if new_signals:
                message += "🎯 *발견된 신호*\n"
                for signal in new_signals[:10]:  # Limit to 10 signals
                    symbol = signal.get('symbol', 'N/A')
                    pattern = signal.get('pattern', 'N/A')
                    ema_period = signal.get('ema_period', 'N/A')
                    entry = signal.get('entry', 0)
                    tp = signal.get('take_profit', 0)
                    message += f"• {symbol}: {pattern} (EMA{ema_period})\n"
                    message += f"  진입: ${entry:.2f} | TP: ${tp:.2f}\n"
                
                if len(new_signals) > 10:
                    message += f"\n... 외 {len(new_signals) - 10}개 신호\n"
            else:
                message += "ℹ️ *신호 없음*\n"
                message += "이번 스캔에서 새로운 매수 신호를 발견하지 못했습니다.\n\n"
            
            # Market status and next scan
            market_hours = self.data_fetcher.get_market_hours()
            is_market_open = market_hours.get('isTheMarketOpen', False)
            
            message += "⏰ *다음 스캔 예정*\n"
            next_scan = scan_end_time + timedelta(seconds=self.scan_interval)
            message += f"• 다음 스캔: {next_scan.strftime('%Y-%m-%d %H:%M:%S')}\n"
            message += f"• 주기: {self.scan_interval/3600:.1f}시간\n"
            message += f"• 시장 상태: {'🟢 개장' if is_market_open else '🔴 마감'}\n\n"
            
            # Performance summary
            if self.total_scans > 0:
                avg_signals_per_scan = self.total_signals / self.total_scans
                message += "📈 *누적 성과*\n"
                message += f"• 총 스캔: {self.total_scans}회\n"
                message += f"• 총 신호: {self.total_signals}개\n"
                message += f"• 평균 신호/스캔: {avg_signals_per_scan:.2f}개\n"
            
            message += "\n" + "=" * 30
            message += "\n_Upper Section Strategy Bot v1.0_"
            
            self.send_telegram_message(message)
            logger.info("Scan summary sent successfully")
            
        except Exception as e:
            logger.error(f"Error sending scan summary: {e}")
    
    def send_error_summary(self, error_msg: str):
        """Send error summary when scan fails"""
        try:
            message = "⚠️ *스캔 오류 발생*\n\n"
            message += f"오류: {error_msg[:200]}\n\n"
            message += "봇이 계속 실행 중이며 다음 스캔을 시도합니다.\n"
            
            if self.last_scan_time:
                next_scan = self.last_scan_time + timedelta(seconds=self.scan_interval)
                message += f"\n⏰ 다음 스캔: {next_scan.strftime('%Y-%m-%d %H:%M:%S')}"
            
            self.send_telegram_message(message)
            
        except Exception as e:
            logger.error(f"Error sending error summary: {e}")
    
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
        
        self.send_telegram_message(startup_message)
        
        # Run initial scan
        self.scan_for_signals()
        
        # Schedule scans
        schedule.every(self.scan_interval).seconds.do(self.scan_for_signals)
        
        # Send status update twice daily
        schedule.every().day.at("09:00").do(self.send_status_update)
        schedule.every().day.at("21:00").do(self.send_status_update)
        
        logger.info(f"Scheduled scans every {self.scan_interval/3600:.1f} hours")
        logger.info("Telegram command polling active. Send /help for commands.")
        
        while self.is_running:
            try:
                schedule.run_pending()
                time.sleep(60)
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