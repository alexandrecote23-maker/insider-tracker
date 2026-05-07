"""Main orchestrator for the insider activity monitoring agent"""

import schedule
import time
from datetime import datetime
import sys
import os

from config.settings import (
    EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECIPIENT,
    TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM_NUMBER, TWILIO_TO_NUMBER,
    MIN_TRANSACTION_AMOUNT, MIN_INSIDERS,
    MEDIUM_TERM_DAYS_MIN, MEDIUM_TERM_DAYS_MAX, CHECK_INTERVAL,
    SELL_ALERT_TICKERS
)
from src.data_fetcher import DataFetcher
from src.detector import ClusterDetector
from src.alerter import AlertManager, EmailAlerter, SMSAlerter


class InsiderTrackerAgent:
    """Main agent for monitoring insider activity"""
    
    def __init__(self, tickers: list = None, daily_time: str = None):
        self.tickers = tickers or []
        self.daily_time = daily_time or "09:00"  # Default 9:00 AM
        
        # Initialize components
        self.data_fetcher = DataFetcher()
        self.detector = ClusterDetector(
            min_amount=MIN_TRANSACTION_AMOUNT,
            min_insiders=MIN_INSIDERS,
            medium_term_min=MEDIUM_TERM_DAYS_MIN,
            medium_term_max=MEDIUM_TERM_DAYS_MAX,
            sell_alert_tickers=SELL_ALERT_TICKERS
        )
        
        # Initialize alert manager
        email_alerter = None
        sms_alerter = None
        
        if EMAIL_SENDER and EMAIL_PASSWORD:
            email_alerter = EmailAlerter(EMAIL_SENDER, EMAIL_PASSWORD)
        
        if TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN:
            sms_alerter = SMSAlerter(
                TWILIO_ACCOUNT_SID,
                TWILIO_AUTH_TOKEN,
                TWILIO_FROM_NUMBER
            )
        
        self.alert_manager = AlertManager(email_alerter, sms_alerter)
        
        print("[START] Insider Tracker Agent initialized")
        print(f"   Email: {EMAIL_RECIPIENT}")
        print(f"   SMS: {TWILIO_TO_NUMBER if TWILIO_TO_NUMBER else 'Disabled'}")
        print(f"   Min Amount: ${MIN_TRANSACTION_AMOUNT:,.0f}")
        print(f"   Tickers: {len(self.tickers)} symbols")
        print(f"   Daily check at: {self.daily_time}")
        print(f"   SELL Alerts enabled for: {', '.join(SELL_ALERT_TICKERS) if SELL_ALERT_TICKERS else 'All tickers'}")
    
    def check_for_clusters(self):
        """Check for clustered insider moves"""
        print(f"\n[DATA] Checking for clusters at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        if not self.tickers:
            print("[WARNING] No tickers configured")
            return
        
        try:
            # Fetch all transactions (with automatic fallback between sources)
            transactions = self.data_fetcher.fetch_all_transactions(self.tickers)
            
            # Check data source health
            health_status = self.data_fetcher.get_health_status()
            
            # Send alert if all sources failed
            if not transactions:
                print("[ERROR] All data sources failed!")
                print("[ALERT] Sending system health alert...")
                self.alert_manager.send_health_alert(health_status, EMAIL_RECIPIENT)
                return
            
            # Send alert if we have very few transactions (possible degradation)
            if transactions and len(transactions) < 15:
                print(f"[WARNING] Only {len(transactions)} transactions (possible service degradation)")
                print("[ALERT] Sending degradation notice...")
                health_status['degraded'] = True
                health_status['warning'] = f"Only {len(transactions)} transactions fetched - service may be degraded"
                self.alert_manager.send_health_alert(health_status, EMAIL_RECIPIENT)
            
            print(f"[UP] Analyzing {len(transactions)} transactions (source: {health_status.get('source', 'unknown')})")
            
            # Detect patterns
            patterns = self.detector.detect_patterns(transactions)
            
            if patterns:
                print(f"[TARGET] Detected {len(patterns)} cluster patterns")
                
                # Filter to only NEW (unsent) patterns before building the email
                new_patterns = self.alert_manager.filter_new_patterns(patterns)
                
                if new_patterns:
                    print(f"[ALERT] Sending email for {len(new_patterns)} new alerts...")
                    # Build message with ONLY the new patterns
                    combined_message = self._combine_alerts(new_patterns)
                    self.alert_manager.send_cluster_alert(
                        combined_message,
                        new_patterns,
                        EMAIL_RECIPIENT,
                        None  # No SMS for combined alerts
                    )
                else:
                    print(f"[INFO] No new alerts (all {len(patterns)} already sent)")
            else:
                print("[OK] No clusters detected")
        
        except Exception as e:
            print(f"[ERROR] Error during check: {e}")
            import traceback
            traceback.print_exc()
            
            # Send health alert on critical error
            self.alert_manager.send_health_alert({
                'success': False,
                'source': None,
                'error': str(e),
                'timestamp': datetime.now(),
                'count': 0
            }, EMAIL_RECIPIENT)
    
    def _combine_alerts(self, patterns) -> str:
        """Combine multiple alert patterns into one message, BUY section first then SELL"""
        lines = []
        
        lines.append("INSIDER TRACKER - CLUSTERED ACTIVITY ALERTS")
        lines.append("")
        
        # Filter to only MEDIUM_TERM patterns (exclude SAME_WEEK)
        medium_term_patterns = [p for p in patterns if "MEDIUM_TERM" in p.pattern_type]
        
        if not medium_term_patterns:
            lines.append("No clusters detected in the 14-21 day window.")
            return "\n".join(lines)
        
        # Separate into BUY and SELL
        buy_patterns = [p for p in medium_term_patterns if "BUY" in p.pattern_type]
        sell_patterns = [p for p in medium_term_patterns if "SELL" in p.pattern_type]
        
        def append_section(section_patterns, move_type):
            lines.append("=" * 80)
            lines.append(f"  {move_type} ACTIVITY  ({len(section_patterns)} alerts)")
            lines.append("=" * 80)
            lines.append("")
            
            for pattern in sorted(section_patterns, key=lambda p: p.ticker):
                total_amount = sum(t.amount for t in pattern.transactions)
                dates = sorted(set(t.transaction_date.strftime('%Y-%m-%d') for t in pattern.transactions))
                names = ", ".join(sorted(set(t.name for t in pattern.transactions)))
                
                lines.append(f"TICKER: {pattern.ticker} ----- MOVE: {move_type}")
                lines.append(f"Purchase date: {', '.join(dates)}")
                lines.append(f"Insiders: {names}")
                lines.append(f"Total Amount: ${total_amount:,.2f}")
                lines.append(f"Transactions: {len(pattern.transactions)}")
                lines.append("")
        
        if buy_patterns:
            append_section(buy_patterns, "BUY")
        
        if sell_patterns:
            append_section(sell_patterns, "SELL")
        
        # Summary
        total_amount = sum(sum(t.amount for t in p.transactions) for p in medium_term_patterns)
        lines.append("-" * 80)
        lines.append(f"SUMMARY:")
        lines.append(f"  BUY Alerts:  {len(buy_patterns)}")
        lines.append(f"  SELL Alerts: {len(sell_patterns)}")
        lines.append(f"  Total Transaction Value: ${total_amount:,.2f}")
        lines.append(f"  Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        return "\n".join(lines)
    
    def start_continuous_monitoring(self, check_interval: int = None):
        """Start continuous monitoring with interval checks"""
        interval = check_interval or CHECK_INTERVAL
        
        print(f"\n[LOOP] Starting continuous monitoring (check every {interval}s)")
        print(f"[DATE] Daily check scheduled at: {self.daily_time}")
        
        # Schedule interval checks
        schedule.every(interval).seconds.do(self.check_for_clusters)
        
        # Schedule daily check
        schedule.every().day.at(self.daily_time).do(self.check_for_clusters)
        
        try:
            while True:
                schedule.run_pending()
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n[STOP] Monitoring stopped")
    
    def start_daily_monitoring(self):
        """Start daily monitoring at specific time"""
        print(f"\n[DATE] Starting daily monitoring at {self.daily_time}")
        
        # Schedule daily check
        schedule.every().day.at(self.daily_time).do(self.check_for_clusters)
        
        try:
            while True:
                schedule.run_pending()
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n[STOP] Daily monitoring stopped")
    
    def start_twice_daily_monitoring(self, time1: str = "09:00", time2: str = "14:00"):
        """Start daily monitoring at TWO specific times"""
        print(f"\n[DATE] Starting twice-daily monitoring at {time1} and {time2}")
        
        # Schedule checks at both times
        schedule.every().day.at(time1).do(self.check_for_clusters)
        schedule.every().day.at(time2).do(self.check_for_clusters)
        
        try:
            while True:
                schedule.run_pending()
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n[STOP] Twice-daily monitoring stopped")
    
    def run_once(self):
        """Run a single check"""
        self.check_for_clusters()
    
    @staticmethod
    def load_configuration():
        """Load configuration from environment"""
        tickers = os.getenv('TICKERS', 'AAPL,MSFT,GOOGL').split(',')
        daily_time = os.getenv('DAILY_TIME', '09:00')
        return [t.strip().upper() for t in tickers if t.strip()], daily_time


def main():
    """Main entry point"""
    # Get tickers from environment or use defaults
    tickers, daily_time = InsiderTrackerAgent.load_configuration()
    
    # Create agent
    agent = InsiderTrackerAgent(tickers, daily_time)
    
    # Check command line arguments
    if len(sys.argv) > 1:
        if sys.argv[1] == '--once':
            # Run single check
            agent.run_once()
        elif sys.argv[1] == '--daily':
            # Run daily at specific time
            agent.start_daily_monitoring()
        elif sys.argv[1] == '--twice-daily':
            # Run twice daily (9:00 and 14:00)
            agent.start_twice_daily_monitoring()
        elif sys.argv[1] == '--continuous':
            # Run continuous monitoring with interval
            agent.start_continuous_monitoring()
        else:
            print(f"Unknown option: {sys.argv[1]}")
            print("Available options: --once, --daily, --twice-daily, --continuous")
    else:
        # Default: twice-daily monitoring at 9h and 14h
        agent.start_twice_daily_monitoring()


if __name__ == "__main__":
    main()
