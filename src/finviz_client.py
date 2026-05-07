"""Finviz insider trading scraper - backup data source"""

import time
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from typing import List, Optional
from src.models import InsiderTransaction


class FinvizClient:
    """Scrapes insider trading data from Finviz as backup source"""

    def __init__(self):
        self.base_url = "https://finviz.com/insidertrading.ashx"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Referer': 'https://finviz.com/'
        })

    def _get(self, url: str, retries: int = 1) -> Optional[requests.Response]:
        """GET with one retry on timeout/connection error."""
        for attempt in range(retries + 1):
            try:
                response = self.session.get(url, timeout=15)
                response.raise_for_status()
                return response
            except (requests.Timeout, requests.ConnectionError) as e:
                if attempt < retries:
                    time.sleep(5)
                else:
                    print(f"[WARNING] Finviz: request failed after {retries + 1} attempts: {e}")
                    return None
            except requests.RequestException as e:
                print(f"[WARNING] Finviz: request error: {e}")
                return None
        return None

    def fetch_recent_transactions(self, days_back: int = 30, min_value: float = 50000) -> List[InsiderTransaction]:
        """Fetch recent insider transactions from Finviz."""
        transactions = []
        cutoff_date = datetime.now() - timedelta(days=days_back)

        for trade_code, tx_type in [('1', 'BUY'), ('2', 'SELL')]:
            response = self._get(f"{self.base_url}?tc={trade_code}")
            if response is None:
                continue

            soup = BeautifulSoup(response.text, 'html.parser')
            table = soup.find('table', class_='styled-table-new')
            if not table:
                print(f"[FINVIZ] No table found for {tx_type}")
                continue

            for row in table.find_all('tr')[1:]:
                cols = row.find_all('td')
                if len(cols) < 8:
                    continue

                try:
                    # col[0]=ticker col[1]=owner col[2]=relationship
                    # col[3]=date col[4]=type col[5]=price col[6]=shares col[7]=value
                    date_text = cols[3].text.strip()
                    try:
                        tx_date = datetime.strptime(date_text, "%b %d '%y")
                    except ValueError:
                        try:
                            tx_date = datetime.strptime(date_text, "%b %d").replace(year=datetime.now().year)
                        except ValueError:
                            continue

                    if tx_date < cutoff_date:
                        continue

                    value_text = cols[7].text.strip().replace('$', '').replace(',', '')
                    try:
                        amount = float(value_text)
                    except ValueError:
                        continue

                    if amount < min_value:
                        continue

                    shares_text = cols[6].text.strip().replace(',', '')
                    try:
                        shares = int(shares_text)
                    except ValueError:
                        shares = 0

                    price_text = cols[5].text.strip().replace('$', '').replace(',', '')
                    try:
                        price = float(price_text)
                    except ValueError:
                        price = amount / shares if shares > 0 else 0

                    transactions.append(InsiderTransaction(
                        name=cols[1].text.strip(),
                        ticker=cols[0].text.strip().upper(),
                        transaction_type=tx_type,
                        shares=abs(shares),
                        price=price,
                        amount=abs(amount),
                        transaction_date=tx_date,
                        relationship=cols[2].text.strip()
                    ))

                except Exception:
                    continue

        return transactions
