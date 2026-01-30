#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETI BOT - Railway Debug Version
"""

import threading
import time
import logging
import sys
import os
from datetime import datetime

try:
    import requests
except ImportError:
    print("❌ requests kurulu degil")
    sys.exit(1)

try:
    import telebot
except ImportError:
    print("❌ telebot kurulu degil")
    sys.exit(1)

# KONFIGURASYON
BOT_TOKEN = "8182630877:AAFtGjtxYv0dqQAGnziaBnaf-GrrI0sPzdk"
VDS_URL = "http://194.62.55.201:8080"

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Bot
bot = telebot.TeleBot(BOT_TOKEN)

class VDSClient:
    def __init__(self):
        self.url = VDS_URL
        print(f"DEBUG: VDSClient initialized with URL: {self.url}")
    
    def check(self):
        """VDS server çalışıyor mu kontrol et - DEBUG EKLENDI"""
        print(f"\n{'='*50}")
        print(f"DEBUG: check_status() started")
        print(f"DEBUG: Target URL: {self.url}")
        print(f"DEBUG: Target IP: 194.62.55.201")
        print(f"{'='*50}")
        
        # 1. Önce socket bağlantısı dene
        try:
            import socket
            print(f"DEBUG: Trying socket connection to 194.62.55.201:8080...")
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            result = sock.connect_ex(('194.62.55.201', 8080))
            print(f"DEBUG: Socket result: {result} (0 = success)")
            sock.close()
        except Exception as e:
            print(f"DEBUG: Socket error: {type(e).__name__}: {e}")
        
        # 2. HTTP isteği dene
        try:
            print(f"DEBUG: Trying HTTP GET {self.url}/health...")
            response = requests.get(
                f"{self.url}/health", 
                timeout=10,
                headers={'User-Agent': 'ETI-Bot-Debug/1.0'}
            )
            print(f"DEBUG: HTTP Status: {response.status_code}")
            print(f"DEBUG: Response body: {response.text[:100]}")
            print(f"{'='*50}\n")
            return response.status_code == 200
            
        except requests.exceptions.ConnectTimeout as e:
            print(f"DEBUG ERROR: Connection timeout - {e}")
            print(f"{'='*50}\n")
            return False
        except requests.exceptions.ConnectionError as e:
            print(f"DEBUG ERROR: Connection error - {e}")
            print(f"{'='*50}\n")
            return False
        except Exception as e:
            print(f"DEBUG ERROR: {type(e).__name__} - {e}")
            print(f"{'='*50}\n")
            return False

vds = VDSClient()

@bot.message_handler(commands=['start'])
def start(message):
    user_id = message.from_user.id
    print(f"\n{'='*50}")
    print(f"DEBUG: /start command received from user {user_id}")
    print(f"{'='*50}")
    
    result = vds.check()
    status = "✅ ONLINE" if result else "❌ OFFLINE"
    
    print(f"DEBUG: VDS check result: {status}")
    
    bot.reply_to(message, 
        f"🤖 *ETI Bot (Debug Mode)*\n\n"
        f"VDS Status: `{status}`\n"
        f"IP: `194.62.55.201:8080`\n\n"
        f"Check console logs for details.", 
        parse_mode='Markdown')

@bot.message_handler(commands=['vds'])
def vds_status(message):
    print(f"\n{'='*50}")
    print(f"DEBUG: /vds command received")
    print(f"{'='*50}")
    
    result = vds.check()
    
    if result:
        msg = "✅ *VDS ONLINE*\n\nDebug: Connection successful"
    else:
        msg = ("❌ *VDS OFFLINE*\n\n"
               "Debug: Check console logs\n"
               "Possible causes:\n"
               "• VDS server down\n"
               "• Network timeout\n"
               "• Firewall blocking")
    
    print(f"DEBUG: Sending response: {msg[:50]}...")
    bot.reply_to(message, msg, parse_mode='Markdown')

@bot.message_handler(commands=['test'])
def test_cmd(message):
    """Detaylı network testi"""
    print(f"\n{'='*50}")
    print(f"DEBUG: /test command - Full network diagnostics")
    
    results = []
    
    # Test 1: DNS çözümleme
    try:
        import socket
        ip = socket.gethostbyname('194.62.55.201')
        results.append(f"✅ DNS: {ip}")
    except Exception as e:
        results.append(f"❌ DNS: {e}")
    
    # Test 2: Ping (ICMP)
    try:
        import subprocess
        ping = subprocess.run(
            ['ping', '-c', '2', '194.62.55.201'],
            capture_output=True, text=True, timeout=10
        )
        if ping.returncode == 0:
            results.append(f"✅ Ping: OK")
        else:
            results.append(f"❌ Ping: Failed")
    except Exception as e:
        results.append(f"❌ Ping: {e}")
    
    # Test 3: HTTP
    try:
        r = requests.get('http://194.62.55.201:8080/health', timeout=5)
        results.append(f"✅ HTTP: {r.status_code}")
    except Exception as e:
        results.append(f"❌ HTTP: {type(e).__name__}")
    
    # Test 4: HTTPS
    try:
        r = requests.get('https://194.62.55.201:8080/health', timeout=5, verify=False)
        results.append(f"✅ HTTPS: {r.status_code}")
    except Exception as e:
        results.append(f"❌ HTTPS: {type(e).__name__}")
    
    report = "\n".join(results)
    print(f"DEBUG: Test results:\n{report}")
    print(f"{'='*50}\n")
    
    bot.reply_to(message, f"🔍 *Network Test Results*\n\n{report}", parse_mode='Markdown')

@bot.message_handler(commands=['yardim'])
def help_cmd(message):
    bot.reply_to(message, 
        "Debug Komutları:\n"
        "/start - Başlat + VDS check\n"
        "/vds - VDS durumu (detaylı)\n"
        "/test - Full network test\n"
        "/yardim - Bu mesaj")

def main():
    print("="*70)
    print("🤖 ETI Bot - Railway Debug Version")
    print("="*70)
    print(f"📍 VDS Server: {VDS_URL}")
    print(f"🔧 Debug mode: ENABLED")
    print("="*70)
    
    # Başlangıç testi
    print("\nDEBUG: Startup test - checking VDS...")
    vds.check()
    
    print("\n🚀 Bot başlatiliyor...")
    print("📞 Komutlar: /start, /vds, /test, /yardim")
    print("="*70)
    
    bot.polling(none_stop=True, interval=1, timeout=30)

if __name__ == "__main__":
    main()
