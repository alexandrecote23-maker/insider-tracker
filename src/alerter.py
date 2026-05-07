"""Alert system for email and SMS notifications"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
import json
import os
from datetime import datetime
import hashlib


class EmailAlerter:
    """Sends email alerts"""
    
    def __init__(self, sender_email: str, sender_password: str):
        self.sender_email = sender_email
        self.sender_password = sender_password
    
    def send_alert(self, recipient: str, subject: str, message: str) -> bool:
        """Send email alert"""
        try:
            # Create message
            msg = MIMEMultipart()
            msg['From'] = self.sender_email
            msg['To'] = recipient
            msg['Subject'] = subject
            
            # Attach plain text message
            msg.attach(MIMEText(message, 'plain'))
            
            # Send email
            with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
                server.login(self.sender_email, self.sender_password)
                server.send_message(msg)
            
            print(f"[OK] Email sent to {recipient}")
            return True
        
        except Exception as e:
            print(f"[ERROR] Failed to send email: {e}")
            return False


class SMSAlerter:
    """Sends SMS alerts using Twilio"""
    
    def __init__(self, account_sid: str, auth_token: str, from_number: str):
        try:
            from twilio.rest import Client
            self.client = Client(account_sid, auth_token)
            self.from_number = from_number
            self.enabled = True
        except ImportError:
            print("[WARNING] Twilio not installed. SMS alerts disabled.")
            self.enabled = False
        except Exception as e:
            print(f"[WARNING] Failed to initialize Twilio: {e}")
            self.enabled = False
    
    def send_alert(self, to_number: str, message: str) -> bool:
        """Send SMS alert"""
        if not self.enabled:
            print("[ERROR] SMS alerts disabled (Twilio not configured)")
            return False
        
        try:
            # Truncate message to SMS length (160 chars) if needed
            sms_message = message[:160] if len(message) > 160 else message
            
            sms = self.client.messages.create(
                body=sms_message,
                from_=self.from_number,
                to=to_number
            )
            
            print(f"[OK] SMS sent to {to_number} (ID: {sms.sid})")
            return True
        
        except Exception as e:
            print(f"[ERROR] Failed to send SMS: {e}")
            return False


class AlertManager:
    """Manages all alerts with duplicate prevention"""
    
    # Use absolute path based on script location
    SENT_ALERTS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'cache', 'sent_alerts.json')
    
    def __init__(self, email_alerter: Optional[EmailAlerter] = None, 
                 sms_alerter: Optional[SMSAlerter] = None):
        self.email_alerter = email_alerter
        self.sms_alerter = sms_alerter
        
        # Ensure cache directory exists
        os.makedirs(os.path.dirname(self.SENT_ALERTS_FILE), exist_ok=True)
        
        # Load previously sent alerts from cache
        self.sent_alerts = self._load_sent_alerts()
        print(f"[CACHE] Loaded {len(self.sent_alerts)} previously sent alerts from {self.SENT_ALERTS_FILE}")
    
    def _load_sent_alerts(self) -> dict:
        """Load previously sent alerts from cache file"""
        if not os.path.exists(self.SENT_ALERTS_FILE):
            print(f"[CACHE] No cache file found at {self.SENT_ALERTS_FILE}")
            return {}
        
        try:
            # Read with UTF-8 encoding, handling BOM if present
            with open(self.SENT_ALERTS_FILE, 'r', encoding='utf-8-sig') as f:
                content = f.read().strip()
                if not content:
                    print(f"[CACHE] Cache file is empty")
                    return {}
                data = json.loads(content)
                return data
        except json.JSONDecodeError as e:
            print(f"[ERROR] Invalid JSON in cache file: {e}")
            # Backup corrupted file
            backup_file = self.SENT_ALERTS_FILE + '.corrupted'
            try:
                os.rename(self.SENT_ALERTS_FILE, backup_file)
                print(f"[CACHE] Corrupted cache backed up to {backup_file}")
            except:
                pass
            return {}
        except Exception as e:
            print(f"[ERROR] Could not load sent alerts cache: {e}")
            return {}
    
    def _save_sent_alerts(self):
        """Save sent alerts to cache file"""
        try:
            os.makedirs(os.path.dirname(self.SENT_ALERTS_FILE), exist_ok=True)
            # Write with UTF-8 encoding without BOM
            with open(self.SENT_ALERTS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.sent_alerts, f, indent=2)
            print(f"[CACHE] Saved {len(self.sent_alerts)} alerts to cache")
        except Exception as e:
            print(f"[ERROR] Could not save sent alerts cache: {e}")
    
    def _get_alert_hash(self, ticker: str, move_type: str) -> str:
        """Hash scoped to the current calendar month so new clusters re-alert monthly."""
        month_key = datetime.now().strftime('%Y-%m')
        combined = f"{ticker}|{move_type}|{month_key}"
        return hashlib.md5(combined.encode()).hexdigest()
    
    def filter_new_patterns(self, patterns: list) -> list:
        """Return only patterns that have not been sent yet"""
        new_patterns = []
        for pattern in patterns:
            move_type = "BUY" if "BUY" in pattern.pattern_type else "SELL"
            alert_key = self._get_alert_hash(pattern.ticker, move_type)
            if alert_key not in self.sent_alerts:
                new_patterns.append(pattern)
            else:
                print(f"[SKIP] Already sent: {pattern.ticker} - {move_type}")
        return new_patterns
    
    def send_cluster_alert(self, alert_message: str, new_patterns: list,
                          recipient_email: str, recipient_phone: str) -> bool:
        """Send email with only the new patterns and mark them as sent"""
        
        if not new_patterns:
            print(f"[INFO] No new alerts to send")
            return False
        
        new_labels = []
        keys_to_track = []
        for pattern in new_patterns:
            move_type = "BUY" if "BUY" in pattern.pattern_type else "SELL"
            new_labels.append(f"{pattern.ticker}-{move_type}")
            keys_to_track.append(self._get_alert_hash(pattern.ticker, move_type))
        
        print(f"[NEW] Found {len(new_patterns)} new alerts: {', '.join(new_labels)}")
        
        success = True
        
        if self.email_alerter:
            email_success = self.email_alerter.send_alert(
                recipient_email,
                "Insider Tracker — Clustered Insider Activity Detected",
                alert_message
            )
            success = success and email_success
        
        if self.sms_alerter and recipient_phone and success:
            lines = alert_message.split('\n')
            short_message = f"{lines[0][:50]}... Check email for details."
            sms_success = self.sms_alerter.send_alert(recipient_phone, short_message)
            success = success and sms_success
        
        if success:
            for alert_key in keys_to_track:
                self.sent_alerts[alert_key] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            self._save_sent_alerts()
            print(f"[OK] Tracked {len(keys_to_track)} new alerts as sent")
        
        return success
    
    def send_health_alert(self, status: dict, recipient_email: str) -> bool:
        """Send alert when data fetching fails or system has issues"""
        
        # Only send health alerts once per day to avoid spam
        health_key = f"health_alert_{datetime.now().strftime('%Y-%m-%d')}"
        if health_key in self.sent_alerts:
            print(f"[SKIP] Health alert already sent today")
            return False
        
        subject = "⚠️ Insider Tracker - System Alert"
        
        message_lines = [
            "INSIDER TRACKER - SYSTEM HEALTH ALERT",
            "",
            f"Time: {status.get('timestamp', 'Unknown')}",
            f"Status: {'OK' if status.get('success') else 'FAILED'}",
            f"Data Source: {status.get('source', 'None available')}",
            f"Transactions Found: {status.get('count', 0)}",
            ""
        ]
        
        if status.get('degraded'):
            message_lines.extend([
                "⚠️ SERVICE DEGRADATION DETECTED",
                status.get('warning', 'System is operating with reduced data'),
                "",
                "IMPACT:",
                "- You may be missing some insider alerts",
                "- Data sources are not responding normally",
                "- The system is using fallback data sources",
                ""
            ])
        
        if status.get('error'):
            message_lines.append("ERRORS:")
            message_lines.append(status['error'])
            message_lines.append("")
        
        if not status.get('success'):
            message_lines.extend([
                "ACTION REQUIRED:",
                "- All data sources failed to return data",
                "- The system cannot detect insider activity",
                "- Please check your internet connection",
                "- Data sources may be temporarily down",
                "",
                "The system will retry at the next scheduled check."
            ])
        
        message = "\n".join(message_lines)
        
        if self.email_alerter:
            success = self.email_alerter.send_alert(
                recipient_email,
                subject,
                message
            )
            
            if success:
                self.sent_alerts[health_key] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                self._save_sent_alerts()
            
            return success
        
        return False
