"""OpenInsider scraper for US insider transactions"""

import time
import requests
from datetime import datetime, timedelta
from typing import List, Optional
from bs4 import BeautifulSoup
from src.models import InsiderTransaction


class OpenInsiderClient:
    """Fetches insider transaction data from OpenInsider.com"""

    BASE_URL = "http://openinsider.com"
    TIMEOUT = 15

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })

    def _get(self, url: str, retries: int = 1) -> Optional[requests.Response]:
        """GET with one retry on timeout/connection error."""
        for attempt in range(retries + 1):
            try:
                response = self.session.get(url, timeout=self.TIMEOUT)
                response.raise_for_status()
                return response
            except (requests.Timeout, requests.ConnectionError) as e:
                if attempt < retries:
                    time.sleep(5)
                else:
                    print(f"[WARNING] OpenInsider: request failed after {retries + 1} attempts: {e}")
                    return None
            except requests.RequestException as e:
                print(f"[WARNING] OpenInsider: request error: {e}")
                return None
        return None

    def _parse_row_bulk(self, cols) -> Optional[InsiderTransaction]:
        """
        Parse one row from the bulk screener (no ticker filter).
        Bulk layout adds a company-name column at col[4], shifting all others by one.
        0=marker 1=filing_date 2=tx_date 3=ticker 4=company
        5=insider 6=title 7=trade_type 8=price 9=qty 10=owned 11=%chg 12=value
        """
        if len(cols) < 13:
            return None
        try:
            tx_date = datetime.strptime(cols[2].text.strip(), '%Y-%m-%d')

            trade = cols[7].text.strip().upper()
            if 'P' in trade:
                tx_type = 'BUY'
            elif 'S' in trade:
                tx_type = 'SELL'
            else:
                return None

            price = float(cols[8].text.strip().replace('$', '').replace(',', '') or 0)
            shares = int(cols[9].text.strip().replace(',', '').replace('+', '').replace('-', '') or 0)
            value_text = cols[12].text.strip().replace('$', '').replace(',', '').replace('+', '').replace('-', '')
            amount = float(value_text) if value_text else shares * price

            if amount < 50000:
                return None

            return InsiderTransaction(
                name=cols[5].text.strip(),
                ticker=cols[3].text.strip().upper(),
                transaction_type=tx_type,
                shares=abs(shares),
                price=price,
                amount=abs(amount),
                transaction_date=tx_date,
                relationship=cols[6].text.strip()
            )
        except (ValueError, IndexError, AttributeError):
            return None

    def _parse_row_ticker(self, cols, ticker: str) -> Optional[InsiderTransaction]:
        """
        Parse one row from a per-ticker screener page.
        Per-ticker layout omits the company-name column.
        0=marker 1=filing_date 2=tx_date 3=ticker
        4=insider 5=title 6=trade_type 7=price 8=qty 9=owned 10=%chg 11=value
        """
        if len(cols) < 12:
            return None
        try:
            tx_date = datetime.strptime(cols[2].text.strip(), '%Y-%m-%d')

            if cols[3].text.strip().upper() != ticker.upper():
                return None

            trade = cols[6].text.strip().upper()
            if 'P' in trade:
                tx_type = 'BUY'
            elif 'S' in trade:
                tx_type = 'SELL'
            else:
                return None

            price = float(cols[7].text.strip().replace('$', '').replace(',', '') or 0)
            shares = int(cols[8].text.strip().replace(',', '').replace('+', '').replace('-', '') or 0)
            value_text = cols[11].text.strip().replace('$', '').replace(',', '').replace('+', '').replace('-', '')
            amount = float(value_text) if value_text else shares * price

            if amount < 50000:
                return None

            return InsiderTransaction(
                name=cols[4].text.strip(),
                ticker=ticker.upper(),
                transaction_type=tx_type,
                shares=abs(shares),
                price=price,
                amount=abs(amount),
                transaction_date=tx_date,
                relationship=cols[5].text.strip()
            )
        except (ValueError, IndexError, AttributeError):
            return None

    def fetch_bulk_transactions(self, days_back: int = 30) -> List[InsiderTransaction]:
        """Fetch all recent insider transactions in bulk (up to 5 pages)."""
        transactions = []
        cutoff_date = datetime.now() - timedelta(days=days_back)

        for page in range(1, 6):
            url = (
                f"{self.BASE_URL}/screener?s=&o=&pl=&ph=&ll=&lh=&fd=30&fdr=&td=0&tdr="
                f"&fdlyl=&fdlyh=&dtefrom=&dteto=&xp=1&vl=50000&vh=&ocl=&och="
                f"&session=on&page={page}"
            )
            response = self._get(url)
            if response is None:
                break

            soup = BeautifulSoup(response.text, 'html.parser')
            table = soup.find('table', class_='tinytable')
            if not table:
                break

            rows = table.find_all('tr')[1:]
            if not rows:
                break

            page_count = 0
            for row in rows:
                cols = row.find_all('td')
                tx = self._parse_row_bulk(cols)
                if tx and tx.transaction_date >= cutoff_date:
                    transactions.append(tx)
                    page_count += 1

            print(f"   Page {page}: {page_count} transactions")
            if page_count == 0:
                break

        return transactions

    def fetch_insider_transactions(self, ticker: str, days_back: int = 30) -> List[InsiderTransaction]:
        """Fetch insider transactions for a single ticker."""
        if any(suffix in ticker for suffix in ('.TO', '.V', '.CN')):
            return []

        cutoff_date = datetime.now() - timedelta(days=days_back)
        transactions = []

        response = self._get(f"{self.BASE_URL}/screener?s={ticker}")
        if response is None:
            return transactions

        soup = BeautifulSoup(response.text, 'html.parser')
        table = soup.find('table', class_='tinytable')
        if not table:
            return transactions

        for row in table.find_all('tr')[1:]:
            cols = row.find_all('td')
            tx = self._parse_row_ticker(cols, ticker)
            if tx and tx.transaction_date >= cutoff_date:
                transactions.append(tx)

        return transactions
