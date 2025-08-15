#!/usr/bin/env python3
import logging
import time
import schedule
import requests
from datetime import datetime, timedelta, timezone, time as dtime
from zoneinfo import ZoneInfo
from typing import List, Dict, Optional
import json
import signal
import sys
import traceback
import threading

from config import (
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID,
    validate_config, format_number, get_chat_ids
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
        self.chat_ids = get_chat_ids()  # Get list of chat IDs
        self.chat_id = self.chat_ids[0] if self.chat_ids else None  # Primary chat ID for commands
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
    
    def send_telegram_message(self, message: str, parse_mode: str = 'Markdown', chat_id: str = None):
        """Send message to specific chat ID or all configured chat IDs"""
        if not self.chat_ids:
            logger.error("No chat IDs configured")
            return
        
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        
        # If specific chat_id provided, send only to that chat
        target_chats = [chat_id] if chat_id else self.chat_ids
        
        for target_id in target_chats:
            try:
                # Ensure chat_id is a string
                target_id_str = str(target_id)
                
                # Check if bot has been added to the chat first
                # Try to get chat info to verify bot has access
                check_url = f"https://api.telegram.org/bot{self.bot_token}/getChat"
                check_response = requests.post(check_url, json={'chat_id': target_id_str}, timeout=5)
                
                if check_response.status_code != 200:
                    logger.error(f"Bot doesn't have access to chat {target_id_str}. User needs to start conversation with bot first.")
                    continue
                
                payload = {
                    'chat_id': target_id_str,
                    'text': message,
                    'parse_mode': parse_mode,
                    'disable_web_page_preview': True
                }
                response = requests.post(url, json=payload, timeout=10)
                if response.status_code == 200:
                    logger.info(f"Telegram message sent successfully to {target_id_str}")
                else:
                    logger.error(f"Failed to send Telegram message to {target_id_str}: {response.text}")
            except Exception as e:
                logger.error(f"Failed to send Telegram message to {target_id}: {e}")
    
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
            
            # Only respond to commands from authorized chats
            if str(chat_id) not in [str(cid) for cid in self.chat_ids]:
                return
            
            if command == '/start':
                message = "🚀 *Upper Section Strategy Bot*\n\n"
                message += "Welcome! This bot monitors NASDAQ stocks for Upper Section patterns.\n\n"
                message += "Type /help to see available commands."
                self.send_telegram_message(message, chat_id=str(chat_id))
            
            elif command == '/help':
                message = "📚 *Available Commands:*\n\n"
                message += "/start - Start the bot\n"
                message += "/help - Show this help message\n"
                message += "/status - Show bot status and statistics\n"
                message += "/scan - Trigger an immediate scan\n"
                message += "/caprange [min] [max] - Set market cap range (in millions)\n"
                message += "  Example: /caprange 500 50000\n"
                # Show ET and local schedule and deprecation note
                local_times = self._today_local_schedule_times()
                message += "(i) Scans run 06:45 / 12:45 / 18:00 ET (fixed).\n"
                if len(local_times) == 3:
                    message += f"    Local times today: {local_times[0]} / {local_times[1]} / {local_times[2]}\n"
                message += "(i) /interval is deprecated.\n"
                message += "/history - Show recent signals\n"
                message += "/clear - Clear signal history\n"
                self.send_telegram_message(message, chat_id=str(chat_id))
            
            elif command == '/status':
                self.send_status_message(chat_id=str(chat_id))
            
            elif command == '/scan':
                if self.is_scanning:
                    self.send_telegram_message("⚠️ A scan is already in progress. Please wait...", chat_id=str(chat_id))
                else:
                    self.send_telegram_message("🔍 Starting immediate scan...", chat_id=str(chat_id))
                    thread = threading.Thread(target=lambda: self.scan_for_signals(requester_chat_id=str(chat_id)))
                    thread.start()
            
            elif command == '/caprange':
                self.handle_caprange(args, chat_id=str(chat_id))
            
            elif command == '/interval':
                self.handle_interval(args, chat_id=str(chat_id))
            
            elif command == '/history':
                self.show_history(chat_id=str(chat_id))
            
            elif command == '/clear':
                self.signals_sent.clear()
                self.save_signals_history()
                self.send_telegram_message("✅ Signal history cleared.", chat_id=str(chat_id))
            
        except Exception as e:
            logger.error(f"Error handling command: {e}")
    
    def send_status_message(self, chat_id=None):
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
        # Show ET and today's local equivalents
        local_times = self._today_local_schedule_times()
        message += "• Scan Times (ET): 06:45, 12:45, 18:00\n"
        if len(local_times) == 3:
            message += f"• Scan Times (Local): {local_times[0]}, {local_times[1]}, {local_times[2]}\n"
        message += f"• Market Cap Range: ${self.min_market_cap/1e6:.0f}M - ${self.max_market_cap/1e9:.0f}B\n"
        
        if self.is_scanning:
            message += f"\n⚙️ *Currently scanning...*\n"
        
        if self.last_scan_time:
            message += f"\n⏰ Last Scan: {self.last_scan_time.strftime('%Y-%m-%d %H:%M:%S')}"
        message += f"\n⏰ Next Scan: {self._format_next_scan_info()}"
        # Also show the next 3 upcoming scans
        upcoming = self._upcoming_scans_info(3)
        if upcoming:
            message += "\n🗓️ Upcoming:"
            for s in upcoming:
                message += f"\n• {s}"
        
        self.send_telegram_message(message, chat_id=chat_id)
    
    def handle_caprange(self, args, chat_id=None):
        """Handle caprange command"""
        try:
            if len(args) != 2:
                self.send_telegram_message(
                    "Usage: /caprange [min_millions] [max_millions]\n"
                    "Example: /caprange 500 50000",
                    chat_id=chat_id
                )
                return
            
            min_cap = float(args[0]) * 1_000_000
            max_cap = float(args[1]) * 1_000_000
            
            if min_cap <= 0 or max_cap <= 0 or min_cap >= max_cap:
                self.send_telegram_message("❌ Invalid range. Min must be less than max and both must be positive.", chat_id=chat_id)
                return
            
            self.min_market_cap = min_cap
            self.max_market_cap = max_cap
            self.data_fetcher.min_market_cap = min_cap
            self.data_fetcher.max_market_cap = max_cap
            
            message = f"✅ Market cap range updated:\n"
            message += f"Min: ${min_cap/1e6:.0f}M\n"
            message += f"Max: ${max_cap/1e9:.1f}B"
            self.send_telegram_message(message, chat_id=chat_id)
            
        except ValueError:
            self.send_telegram_message("❌ Invalid input. Please use numbers only.")
        except Exception as e:
            self.send_telegram_message(f"❌ Error: {str(e)}")
    
    def handle_interval(self, args, chat_id: str = None):
        """Handle interval command (deprecated)."""
        try:
            message = (
                "ℹ️ 스캔 주기 설정은 더 이상 지원하지 않습니다.\n"
                "이제 스캔은 미국 시장(ET) 기준 세 번 실행됩니다:\n"
                "• 프리마켓 중간 06:45 ET\n"
                "• 본장 중간 12:45 ET\n"
                "• 애프터마켓 중간 18:00 ET"
            )
            self.send_telegram_message(message, chat_id=chat_id)
        except Exception as e:
            self.send_telegram_message(f"❌ Error: {str(e)}", chat_id=chat_id)

    # --- Scheduling helpers (US market midpoints in ET) ---
    def _is_weekday(self, dt_et: datetime) -> bool:
        return dt_et.weekday() < 5

    def _session_midpoints_et(self, date_et: datetime) -> List[datetime]:
        tz = ZoneInfo("America/New_York")
        Y, M, D = date_et.year, date_et.month, date_et.day
        return [
            datetime(Y, M, D, 6, 45, tzinfo=tz),  # Pre-market midpoint (04:00-09:30)
            datetime(Y, M, D, 12, 45, tzinfo=tz), # Regular session midpoint (09:30-16:00)
            datetime(Y, M, D, 18, 0, tzinfo=tz),  # After-hours midpoint (16:00-20:00)
        ]

    def _next_scheduled_scan_utc(self, now_utc: Optional[datetime] = None) -> datetime:
        if now_utc is None:
            now_utc = datetime.now(timezone.utc)
        tz = ZoneInfo("America/New_York")
        now_et = now_utc.astimezone(tz)

        # Search today and up to 7 days ahead
        for add_days in range(0, 8):
            day_et = now_et + timedelta(days=add_days)
            date_et = datetime(day_et.year, day_et.month, day_et.day, tzinfo=tz)
            if not self._is_weekday(date_et):
                continue
            for target_et in self._session_midpoints_et(date_et):
                target_utc = target_et.astimezone(timezone.utc)
                if target_utc > now_utc:
                    return target_utc
        # Fallback
        return now_utc + timedelta(hours=1)

    def _format_next_scan_info(self) -> str:
        """Return next scan time formatted with ET and Local."""
        nxt = self._next_scheduled_scan_utc()
        et_tz = ZoneInfo("America/New_York")
        nxt_et = nxt.astimezone(et_tz)
        local_tz = datetime.now().astimezone().tzinfo
        nxt_local = nxt.astimezone(local_tz)
        local_tzname = nxt_local.tzname() or "Local"
        return (
            f"{nxt_et.strftime('%Y-%m-%d %H:%M:%S')} ET | "
            f"Local: {nxt_local.strftime('%Y-%m-%d %H:%M:%S')} {local_tzname}"
        )

    def _upcoming_scans_info(self, count: int = 3) -> List[str]:
        """Return a list of the next N scan times as strings with ET and Local."""
        res = []
        now_utc = datetime.now(timezone.utc)
        next_utc = self._next_scheduled_scan_utc(now_utc)
        et_tz = ZoneInfo("America/New_York")
        local_tz = datetime.now().astimezone().tzinfo
        local_tzname = datetime.now().astimezone().tzname() or "Local"
        collected = 0
        cursor = next_utc
        while collected < count:
            et_str = cursor.astimezone(et_tz).strftime('%Y-%m-%d %H:%M:%S') + " ET"
            loc_dt = cursor.astimezone(local_tz)
            loc_str = loc_dt.strftime('%Y-%m-%d %H:%M:%S') + f" {local_tzname}"
            res.append(f"{et_str} | Local: {loc_str}")
            # Advance cursor to just after this time to find the next
            cursor = self._next_scheduled_scan_utc(cursor + timedelta(seconds=1))
            collected += 1
        return res

    def _today_local_schedule_times(self) -> List[str]:
        """Return today's ET schedule times converted to local HH:MM strings."""
        et_tz = ZoneInfo("America/New_York")
        local_tz = datetime.now().astimezone().tzinfo
        now_et = datetime.now(timezone.utc).astimezone(et_tz)
        today_et_date = datetime(now_et.year, now_et.month, now_et.day, tzinfo=et_tz)
        local_times = []
        for t in self._session_midpoints_et(today_et_date):
            local_times.append(t.astimezone(local_tz).strftime('%H:%M'))
        return local_times
    
    def show_history(self, chat_id: str = None):
        """Show signal history"""
        if not self.signals_sent:
            self.send_telegram_message("No signals in history yet.", chat_id=chat_id)
            return
        
        recent_signals = sorted(list(self.signals_sent))[-10:]
        
        message = "📜 *Recent Signals:*\n\n"
        for signal in recent_signals:
            parts = signal.split('_')
            if len(parts) >= 2:
                symbol = parts[0]
                date = parts[1][:10]
                message += f"• {symbol} - {date}\n"
        
        self.send_telegram_message(message, chat_id=chat_id)
    
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
    
    def scan_for_signals(self, requester_chat_id: str = None):
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
            
            # Process all signals but don't send individual messages
            if signals:
                logger.info(f"Found {len(signals)} total signals ({len(new_signals)} new, {len(repeated_signals)} repeated)")
                # Just track signals without sending individual messages
                for signal in signals:
                    symbol = signal['symbol']
                    signal_key = f"{symbol}_{datetime.now().isoformat()}"
                    self.signals_sent.add(signal_key)
                    self.total_signals += 1
                    logger.info(f"Signal found for {symbol} - Pattern: {signal.get('pattern')} - EMA{signal.get('ema_period')}")
            else:
                logger.info("No signals found in this scan")
            
            logger.info(f"Total API requests made: {self.data_fetcher.fmp_client.request_count}")
            
            # Send scan completion summary
            self.send_scan_summary(stocks, signals, new_signals, requester_chat_id)
            
        except Exception as e:
            logger.error(f"Error during scan: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            # Send error summary
            self.send_error_summary(str(e), requester_chat_id)
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
            # Include ET and today's local schedule
            local_times = self._today_local_schedule_times()
            message += "• Scan Times (ET): 06:45, 12:45, 18:00\n"
            if len(local_times) == 3:
                message += f"• Scan Times (Local): {local_times[0]}, {local_times[1]}, {local_times[2]}\n"
            
            market_hours = self.data_fetcher.get_market_hours()
            message += f"\n🏛️ *Market Status:*\n"
            message += f"• {'OPEN' if market_hours.get('isTheMarketOpen') else 'CLOSED'}\n"
            
            if self.last_scan_time:
                message += f"\n⏰ Last Scan: {self.last_scan_time.strftime('%Y-%m-%d %H:%M:%S')}"
            message += f"\n⏰ Next Scan: {self._format_next_scan_info()}"
            # Upcoming list
            upcoming = self._upcoming_scans_info(3)
            if upcoming:
                message += "\n🗓️ Upcoming:"
                for s in upcoming:
                    message += f"\n• {s}"
            
            self.send_telegram_message(message)
            
        except Exception as e:
            logger.error(f"Error sending status update: {e}")
    
    def send_scan_summary(self, stocks: List[Dict], all_signals: List[Dict], new_signals: List[Dict], requester_chat_id: str = None):
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
            
            # Signal summary - EMA 기간별로 종목 코드 구분하여 표시
            if all_signals:
                message += "🎯 *포착된 신호 종목*\n"
                
                # EMA 기간별로 신호 분류
                ema15_signals = [s for s in all_signals if s.get('ema_period') == 15]
                ema33_signals = [s for s in all_signals if s.get('ema_period') == 33]
                
                # EMA15 신호
                if ema15_signals:
                    ema15_new = [s.get('symbol', 'N/A') for s in ema15_signals if s in new_signals]
                    ema15_repeat = [s.get('symbol', 'N/A') for s in ema15_signals if s not in new_signals]
                    
                    message += f"📊 *EMA15 신호:*\n"
                    if ema15_new:
                        message += f"  🆕 새로운: {', '.join(ema15_new)}\n"
                    if ema15_repeat:
                        message += f"  🔄 반복: {', '.join(ema15_repeat)}\n"
                
                # EMA33 신호
                if ema33_signals:
                    ema33_new = [s.get('symbol', 'N/A') for s in ema33_signals if s in new_signals]
                    ema33_repeat = [s.get('symbol', 'N/A') for s in ema33_signals if s not in new_signals]
                    
                    message += f"📈 *EMA33 신호:*\n"
                    if ema33_new:
                        message += f"  🆕 새로운: {', '.join(ema33_new)}\n"
                    if ema33_repeat:
                        message += f"  🔄 반복: {', '.join(ema33_repeat)}\n"
                
                message += "\n"
            else:
                message += "ℹ️ *신호 없음*\n"
                message += "이번 스캔에서 매수 신호를 발견하지 못했습니다.\n\n"
            
            # Market status and next scan
            market_hours = self.data_fetcher.get_market_hours()
            is_market_open = market_hours.get('isTheMarketOpen', False)
            
            message += "⏰ *다음 스캔 예정*\n"
            message += f"• 다음 스캔: {self._format_next_scan_info()}\n"
            message += f"• 주기: 고정 스케줄 (ET)\n"
            # Show next few upcoming slots
            upcoming = self._upcoming_scans_info(3)
            if upcoming:
                message += "• 다음 일정: " + "; ".join(upcoming) + "\n"
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
            
            # Send to requester only if this was a manual scan, otherwise send to all
            if requester_chat_id:
                self.send_telegram_message(message, chat_id=requester_chat_id)
            else:
                self.send_telegram_message(message)  # Send to all for scheduled scans
            logger.info("Scan summary sent successfully")
            
        except Exception as e:
            logger.error(f"Error sending scan summary: {e}")
    
    def send_error_summary(self, error_msg: str, requester_chat_id: str = None):
        """Send error summary when scan fails"""
        try:
            message = "⚠️ *스캔 오류 발생*\n\n"
            message += f"오류: {error_msg[:200]}\n\n"
            message += "봇이 계속 실행 중이며 다음 스캔을 시도합니다.\n"
            
            message += f"\n⏰ 다음 스캔: {self._format_next_scan_info()}"
            
            if requester_chat_id:
                self.send_telegram_message(message, chat_id=requester_chat_id)
            else:
                self.send_telegram_message(message)
            
        except Exception as e:
            logger.error(f"Error sending error summary: {e}")

    def _scheduled_scan_loop(self):
        """Background loop to trigger scans at ET session midpoints.
        Ensures immediate scans do not affect this schedule."""
        logger.info("Starting fixed-time scheduled scan loop (ET midpoints)")
        while self.is_running:
            try:
                now_utc = datetime.now(timezone.utc)
                next_utc = self._next_scheduled_scan_utc(now_utc)
                sleep_seconds = max(1, int((next_utc - now_utc).total_seconds()))
                # Sleep in chunks to allow graceful shutdown
                while self.is_running and sleep_seconds > 0:
                    chunk = min(60, sleep_seconds)
                    time.sleep(chunk)
                    sleep_seconds -= chunk
                if not self.is_running:
                    break
                if not self.is_scanning:
                    logger.info(f"Triggering scheduled scan at {datetime.now().isoformat()}")
                    self.scan_for_signals()
                else:
                    logger.info("Scheduled time reached but a scan is in progress; skipping this slot.")
            except Exception as e:
                logger.error(f"Error in scheduled scan loop: {e}")
                time.sleep(30)
    
    def run(self):
        logger.info("=" * 50)
        logger.info("Upper Section Strategy Bot Started")
        logger.info("=" * 50)
        
        startup_message = "🚀 *Upper Section Strategy Bot Started*\n\n"
        startup_message += "Monitoring NASDAQ stocks for Upper Section patterns using weekly data.\n"
        startup_message += f"• Strategy: Single Peak + Bearish Pattern + EMA Entry\n"
        startup_message += f"• Timeframe: Weekly (1W)\n"
        # Include ET and local schedule times for clarity
        local_times = self._today_local_schedule_times()
        startup_message += "• Scan Times (ET): 06:45 / 12:45 / 18:00\n"
        if len(local_times) == 3:
            startup_message += f"• Scan Times (Local): {local_times[0]} / {local_times[1]} / {local_times[2]}\n"
        # Next scan in ET and local
        startup_message += f"• Next Scan: {self._format_next_scan_info()}\n"
        startup_message += f"• TP/SL: +10% / -5%\n"
        startup_message += "\nType /help to see available commands."
        
        self.send_telegram_message(startup_message)
        
        # Run initial scan
        self.scan_for_signals()
        
        # Start fixed-time scheduled scan loop (ET midpoints)
        scheduler_thread = threading.Thread(target=self._scheduled_scan_loop, daemon=True)
        scheduler_thread.start()
        
        # Send status update twice daily
        schedule.every().day.at("09:00").do(self.send_status_update)
        schedule.every().day.at("21:00").do(self.send_status_update)
        
        logger.info("Scheduled scans at ET midpoints: 06:45, 12:45, 18:00")
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
