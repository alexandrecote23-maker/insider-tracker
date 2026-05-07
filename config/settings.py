import os
from dotenv import load_dotenv

load_dotenv()

# Email Configuration
EMAIL_SENDER = os.getenv('EMAIL_SENDER')
EMAIL_PASSWORD = os.getenv('EMAIL_PASSWORD')
EMAIL_RECIPIENT = os.getenv('EMAIL_RECIPIENT', 'AlexandreCote23@gmail.com')

# SMS Configuration (Twilio)
TWILIO_ACCOUNT_SID = os.getenv('TWILIO_ACCOUNT_SID')
TWILIO_AUTH_TOKEN = os.getenv('TWILIO_AUTH_TOKEN')
TWILIO_FROM_NUMBER = os.getenv('TWILIO_FROM_NUMBER')
TWILIO_TO_NUMBER = os.getenv('TWILIO_TO_NUMBER', '+1-819-350-4323')

# Alert Thresholds
MIN_TRANSACTION_AMOUNT = float(os.getenv('MIN_TRANSACTION_AMOUNT', 250000))  # Increased from 50k to reduce noise
MIN_INSIDERS = int(os.getenv('MIN_INSIDERS', 2))
MEDIUM_TERM_DAYS_MIN = int(os.getenv('MEDIUM_TERM_DAYS_MIN', 14))
MEDIUM_TERM_DAYS_MAX = int(os.getenv('MEDIUM_TERM_DAYS_MAX', 21))

# SELL Alerts - Only show SELL signals for these tickers
SELL_ALERT_TICKERS = ['TSM', 'AMD', 'IAG.to', 'NILI']

# Check Interval (in seconds)
CHECK_INTERVAL = int(os.getenv('CHECK_INTERVAL', 3600))

# Cache Directory
CACHE_DIR = os.getenv('CACHE_DIR', './cache')
if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)
