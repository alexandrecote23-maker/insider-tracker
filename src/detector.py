"""Detector for clustered insider moves"""

from datetime import datetime, timedelta
from typing import List, Dict, Any
from src.models import InsiderTransaction


class ClusterPattern:
    """Represents a detected cluster pattern"""

    def __init__(self, pattern_type: str, ticker: str, transactions: List[InsiderTransaction],
                 alert_message: str):
        self.pattern_type = pattern_type
        self.ticker = ticker
        self.transactions = transactions
        self.alert_message = alert_message
        self.detected_at = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        return {
            'pattern_type': self.pattern_type,
            'ticker': self.ticker,
            'detected_at': self.detected_at.isoformat(),
            'transactions': [t.to_dict() for t in self.transactions],
            'alert_message': self.alert_message
        }


class ClusterDetector:
    """Detects clustered insider moves within a 14-21 day window"""

    def __init__(self, min_amount: float = 50000, min_insiders: int = 2,
                 medium_term_min: int = 14, medium_term_max: int = 21,
                 sell_alert_tickers: list = None):
        self.min_amount = min_amount
        self.min_insiders = min_insiders
        self.medium_term_min = medium_term_min
        self.medium_term_max = medium_term_max
        self.sell_alert_tickers = sell_alert_tickers or []

    def detect_patterns(self, transactions: List[InsiderTransaction]) -> List[ClusterPattern]:
        """Detect all cluster patterns in transactions."""
        patterns = []
        by_ticker: Dict[str, List[InsiderTransaction]] = {}
        for tx in transactions:
            by_ticker.setdefault(tx.ticker, []).append(tx)

        for ticker, ticker_txs in by_ticker.items():
            patterns.extend(self._detect_medium_term_clusters(ticker, ticker_txs))

        return patterns

    def _detect_medium_term_clusters(self, ticker: str, transactions: List[InsiderTransaction]) -> List[ClusterPattern]:
        """Detect clusters within 14-21 days."""
        patterns = []
        sorted_txs = sorted(transactions, key=lambda x: x.transaction_date)

        seen_buy_messages: set = set()
        seen_sell_messages: set = set()

        for start_tx in sorted_txs:
            if start_tx.amount < self.min_amount:
                continue

            end_date = start_tx.transaction_date + timedelta(days=self.medium_term_max)
            start_date = start_tx.transaction_date - timedelta(days=self.medium_term_min - 1)

            window_buys = []
            window_sells = []
            for tx in sorted_txs:
                if start_date <= tx.transaction_date <= end_date and tx.amount >= self.min_amount:
                    if tx.transaction_type == 'BUY':
                        window_buys.append(tx)
                    else:
                        window_sells.append(tx)

            if len(window_buys) >= self.min_insiders:
                date_range = f"{window_buys[0].transaction_date.date()} - {window_buys[-1].transaction_date.date()}"
                names = ", ".join(t.name for t in window_buys)
                msg = (
                    f"[BUY] MEDIUM-TERM BUY SIGNAL - {ticker}\n"
                    f"Period: {date_range} (14-21 days)\n"
                    f"Insiders: {names}\n"
                    f"Total Amount: ${sum(t.amount for t in window_buys):,.2f}\n"
                    f"Transactions: {len(window_buys)}"
                )
                if msg not in seen_buy_messages:
                    seen_buy_messages.add(msg)
                    patterns.append(ClusterPattern("MEDIUM_TERM_BUY", ticker, window_buys, msg))

            if len(window_sells) >= self.min_insiders:
                if not self.sell_alert_tickers or ticker in self.sell_alert_tickers:
                    date_range = f"{window_sells[0].transaction_date.date()} - {window_sells[-1].transaction_date.date()}"
                    names = ", ".join(t.name for t in window_sells)
                    msg = (
                        f"[SELL] MEDIUM-TERM SELL SIGNAL - {ticker}\n"
                        f"Period: {date_range} (14-21 days)\n"
                        f"Insiders: {names}\n"
                        f"Total Amount: ${sum(t.amount for t in window_sells):,.2f}\n"
                        f"Transactions: {len(window_sells)}"
                    )
                    if msg not in seen_sell_messages:
                        seen_sell_messages.add(msg)
                        patterns.append(ClusterPattern("MEDIUM_TERM_SELL", ticker, window_sells, msg))

        return patterns
