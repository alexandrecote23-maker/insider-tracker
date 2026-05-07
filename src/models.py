"""Data models for insider transactions"""

from datetime import datetime
from typing import Dict, Any


class InsiderTransaction:
    """Represents a single insider transaction"""
    
    def __init__(self, name: str, ticker: str, transaction_type: str, 
                 shares: int, price: float, amount: float, 
                 transaction_date: datetime, relationship: str):
        self.name = name
        self.ticker = ticker
        self.transaction_type = transaction_type  # 'BUY' or 'SELL'
        self.shares = shares
        self.price = price
        self.amount = amount
        self.transaction_date = transaction_date
        self.relationship = relationship
    
    def __repr__(self):
        return (f"InsiderTransaction({self.name}, {self.ticker}, {self.transaction_type}, "
                f"${self.amount:,.2f}, {self.transaction_date.date()})")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert transaction to dictionary"""
        return {
            'name': self.name,
            'ticker': self.ticker,
            'transaction_type': self.transaction_type,
            'shares': self.shares,
            'price': self.price,
            'amount': self.amount,
            'transaction_date': self.transaction_date.isoformat(),
            'relationship': self.relationship
        }
