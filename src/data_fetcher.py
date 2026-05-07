"""Data fetcher for insider transaction data"""

from datetime import datetime
from typing import List
from src.models import InsiderTransaction
from src.openinsider_client import OpenInsiderClient
from src.finviz_client import FinvizClient


class DataFetcher:
    """Fetches insider transaction data from multiple sources with fallback"""

    def __init__(self):
        self.openinsider_client = OpenInsiderClient()
        self.finviz_client = FinvizClient()

        self.last_fetch_status = {
            'success': False,
            'source': None,
            'error': None,
            'timestamp': None,
            'count': 0
        }

    def fetch_all_transactions(self, tickers: List[str], days_back: int = 30) -> List[InsiderTransaction]:
        """Fetch transactions with automatic fallback between data sources."""
        all_transactions = []
        source_used = None
        error_messages = []

        # === PRIMARY: OpenInsider bulk ===
        print("[DATA] Fetching from OpenInsider (primary)...")
        try:
            bulk_txs = self.openinsider_client.fetch_bulk_transactions(days_back)
            if bulk_txs and len(bulk_txs) > 10:
                all_transactions.extend(bulk_txs)
                source_used = "OpenInsider"
                print(f"[OK] Found {len(bulk_txs)} transactions from OpenInsider")
            elif bulk_txs:
                error_messages.append(f"OpenInsider: Only {len(bulk_txs)} transactions (possible degradation)")
                print(f"[WARNING] OpenInsider returned only {len(bulk_txs)} txs - trying Finviz...")
            else:
                error_messages.append("OpenInsider: No transactions returned")
                print("[WARNING] OpenInsider returned nothing")
        except Exception as e:
            error_messages.append(f"OpenInsider: {e}")
            print(f"[WARNING] OpenInsider failed: {e}")

        # === BACKUP: Finviz ===
        if not all_transactions or len(all_transactions) < 20:
            print("[DATA] Trying Finviz (backup)...")
            try:
                finviz_txs = self.finviz_client.fetch_recent_transactions(days_back)
                if finviz_txs:
                    if all_transactions:
                        existing_keys = {(t.ticker, t.transaction_date) for t in all_transactions}
                        new = [t for t in finviz_txs if (t.ticker, t.transaction_date) not in existing_keys]
                        all_transactions.extend(new)
                        print(f"[OK] Added {len(new)} new transactions from Finviz (total: {len(all_transactions)})")
                    else:
                        all_transactions.extend(finviz_txs)
                        source_used = "Finviz"
                        print(f"[OK] Found {len(finviz_txs)} transactions from Finviz")
            except Exception as e:
                error_messages.append(f"Finviz: {e}")
                print(f"[WARNING] Finviz failed: {e}")

        # === LAST RESORT: per-ticker OpenInsider ===
        if not all_transactions:
            print("[DATA] Trying per-ticker checks (slow)...")
            for i, ticker in enumerate(tickers[:20], 1):
                if i % 10 == 0:
                    print(f"   [{i}/20] Progress...")
                txs = self.openinsider_client.fetch_insider_transactions(ticker, days_back)
                all_transactions.extend(txs)
            if all_transactions:
                source_used = "OpenInsider-PerTicker"
                print(f"[OK] Found {len(all_transactions)} from per-ticker checks")

        self.last_fetch_status = {
            'success': len(all_transactions) > 0,
            'source': source_used,
            'error': "; ".join(error_messages) if error_messages else None,
            'timestamp': datetime.now(),
            'count': len(all_transactions)
        }

        all_transactions.sort(key=lambda x: x.transaction_date, reverse=True)
        print(f"[OK] Total transactions: {len(all_transactions)}")
        return all_transactions

    def get_health_status(self) -> dict:
        return self.last_fetch_status
