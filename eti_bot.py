#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETI MUTLU KUTU - VDS TELEGRAM BOT v2.0
Railway için optimize edilmiş versiyon
"""

import os
import sys
import threading
import time
import json
import signal
from typing import Optional, Dict, List
from datetime import datetime

# Önce dependency kontrolü
print("📦 Paketler kontrol ediliyor...")

try:
    import telebot
    from telebot import types
    import requests
    from flask import Flask, request, jsonify
    print("✅ Tüm paketler yüklü")
except ImportError as e:
    print(f"❌ Eksik paket: {e}")
    print("📦 Kurulum: pip install telebot requests flask")
    sys.exit(1)

# ═══════════════════════════════════════════════════════════
# KONFİGÜRASYON
# ═══════════════════════════════════════════════════════════

print("⚙️  Konfigürasyon yükleniyor...")

# Environment variables kontrolü
BOT_TOKEN = os.environ.get("BOT_TOKEN")
VDS_SERVER_URL = os.environ.get("VDS_SERVER_URL", "http://194.62.55.201:8080")
DEBUG_MODE = os.environ.get("DEBUG_MODE", "True").lower() == "true"
PORT = int(os.environ.get("PORT", 8080))
RAILWAY_PUBLIC_DOMAIN = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "")

# BOT_TOKEN zorunlu kontrolü
if not BOT_TOKEN:
    print("❌ HATA: BOT_TOKEN bulunamadı!")
    print("ℹ️  Railway'de Variables sekmesine git ve ekle:")
    print("   Name: BOT_TOKEN")
    print("   Value: 7968457283:AAG-8tILmgVJvZmKv8m5DMUwX6x7aF3kYeg")
    print("⏳ 10 saniye sonra kapanıyor...")
    time.sleep(10)
    sys.exit(1)

print(f"✅ BOT_TOKEN: {BOT_TOKEN[:10]}...")
print(f"📍 VDS Server: {VDS_SERVER_URL}")
print(f"🐞 Debug: {DEBUG_MODE}")
print(f"🌐 Port: {PORT}")

# ═══════════════════════════════════════════════════════════
# DEBUG UTILS
# ═══════════════════════════════════════════════════════════

def debug_log(msg: str, level: str = "INFO"):
    """Debug mesajı"""
    if DEBUG_MODE:
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] [{level}] {msg}")

# ═══════════════════════════════════════════════════════════
# BOT INIT
# ═══════════════════════════════════════════════════════════

print("🤖 Bot başlatılıyor...")
try:
    bot = telebot.TeleBot(BOT_TOKEN)
    print("✅ Bot başarıyla oluşturuldu")
except Exception as e:
    print(f"❌ Bot oluşturulamadı: {e}")
    sys.exit(1)

# ═══════════════════════════════════════════════════════════
# STATE MANAGEMENT
# ═══════════════════════════════════════════════════════════

class BotState:
    def __init__(self):
        self.user_states = {}
        self.user_data = {}
        self.active_jobs = {}
        self.job_lock = threading.Lock()
    
    def set_state(self, user_id: int, state: str):
        self.user_states[user_id] = state
    
    def get_state(self, user_id: int) -> Optional[str]:
        return self.user_states.get(user_id)
    
    def clear_state(self, user_id: int):
        if user_id in self.user_states:
            del self.user_states[user_id]
        if user_id in self.user_data:
            del self.user_data[user_id]
    
    def set_data(self, user_id: int, key: str, value):
        if user_id not in self.user_data:
            self.user_data[user_id] = {}
        self.user_data[user_id][key] = value
    
    def get_data(self, user_id: int, key: str, default=None):
        return self.user_data.get(user_id, {}).get(key, default)
    
    def has_active_job(self, user_id: int) -> bool:
        with self.job_lock:
            return user_id in self.active_jobs
    
    def set_active_job(self, user_id: int, job_data: dict):
        with self.job_lock:
            self.active_jobs[user_id] = job_data
    
    def get_active_job(self, user_id: int) -> Optional[dict]:
        with self.job_lock:
            return self.active_jobs.get(user_id)
    
    def remove_active_job(self, user_id: int):
        with self.job_lock:
            if user_id in self.active_jobs:
                del self.active_jobs[user_id]

bot_state = BotState()

# ═══════════════════════════════════════════════════════════
# VDS CLIENT
# ═══════════════════════════════════════════════════════════

class VDSClient:
    def __init__(self):
        self.base_url = VDS_SERVER_URL
        self.timeout = 30
    
    def check_status(self) -> bool:
        """VDS server çalışıyor mu kontrol et"""
        try:
            debug_log(f"VDS kontrol: {self.base_url}", "VDS")
            response = requests.get(f"{self.base_url}/health", timeout=5)
            debug_log(f"VDS cevap: {response.status_code}", "VDS")
            return response.status_code == 200
        except Exception as e:
            debug_log(f"VDS bağlantı hatası: {e}", "VDS")
            return False
    
    def kayit_yap(self, davet_kodu: str) -> dict:
        """VDS server'a kayıt isteği gönder"""
        try:
            url = f"{self.base_url}/kayit"
            data = {"davet_kodu": davet_kodu}
            
            debug_log(f"VDS istek: {davet_kodu}", "VDS")
            
            response = requests.post(url, json=data, timeout=self.timeout)
            result = response.json()
            
            debug_log(f"VDS cevap: {result}", "VDS")
            return result
            
        except Exception as e:
            debug_log(f"VDS hatası: {str(e)}", "VDS")
            return {"success": False, "error": str(e)}

# ═══════════════════════════════════════════════════════════
# TELEGRAM HANDLERS - BASİT VERSİYON
# ═══════════════════════════════════════════════════════════

@bot.message_handler(commands=['start'])
def start_command(message):
    user_id = message.from_user.id
    debug_log(f"User {user_id}: /start", "TELEGRAM")
    
    vds_client = VDSClient()
    
    msg = "🤖 *ETI MUTLU KUTU BOT* 🚀\n\n"
    msg += "📍 *VDS Modu Aktif*\n"
    msg += f"🔗 Server: `{VDS_SERVER_URL}`\n\n"
    
    if vds_client.check_status():
        msg += "✅ *VDS Bağlantısı:* Aktif\n\n"
        msg += "📝 Kullanım:\n"
        msg += "1. Davet kodunu gönder\n"
        msg += "2. Kaç adet istediğini yaz\n"
        msg += "3. Bot otomatik çalışır\n\n"
        msg += "Örnek kod: `8701545434`"
    else:
        msg += "❌ *VDS Bağlantısı:* Kapalı\n"
        msg += "Sunucuya bağlanılamıyor!\n"
        msg += f"URL: {VDS_SERVER_URL}"
    
    bot.reply_to(message, msg, parse_mode='Markdown')

@bot.message_handler(commands=['test'])
def test_command(message):
    user_id = message.from_user.id
    debug_log(f"User {user_id}: /test", "TELEGRAM")
    
    vds_client = VDSClient()
    
    if vds_client.check_status():
        bot.reply_to(message, "✅ *VDS SERVER ÇALIŞIYOR!*", parse_mode='Markdown')
    else:
        bot.reply_to(message, "❌ *VDS SERVER KAPALI!*", parse_mode='Markdown')

@bot.message_handler(commands=['durum'])
def status_command(message):
    user_id = message.from_user.id
    
    msg = "📊 *SİSTEM DURUMU*\n\n"
    msg += f"🤖 Bot: Çalışıyor\n"
    msg += f"📍 VDS: {VDS_SERVER_URL}\n"
    msg += f"👤 Kullanıcı ID: {user_id}\n"
    msg += f"🕐 Zaman: {datetime.now().strftime('%H:%M:%S')}"
    
    bot.reply_to(message, msg, parse_mode='Markdown')

@bot.message_handler(commands=['yardim', 'help'])
def help_command(message):
    msg = "📋 *KOMUT LİSTESİ*\n\n"
    msg += "• /start - Botu başlat\n"
    msg += "• /test - VDS bağlantı testi\n"
    msg += "• /durum - Sistem durumu\n"
    msg += "• /yardim - Bu mesaj\n\n"
    msg += "📍 *VDS URL:* " + VDS_SERVER_URL
    
    bot.reply_to(message, msg, parse_mode='Markdown')

@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    user_id = message.from_user.id
    text = message.text.strip()
    
    debug_log(f"User {user_id} mesaj: {text[:50]}", "TELEGRAM")
    
    if text.isdigit() and len(text) == 10:
        # Davet kodu gibi görünüyor
        bot.reply_to(message, f"🎯 Kod alındı: `{text}`\n\nKaç adet istiyorsun? (1-100)", parse_mode='Markdown')
    elif text.isdigit() and 1 <= int(text) <= 100:
        # Adet bilgisi
        bot.reply_to(message, f"✅ {text} adet kayıt başlatılıyor...\n\n⚡ VDS sunucusuna istek gönderiliyor.", parse_mode='Markdown')
    else:
        bot.reply_to(message, "❓ Anlamadım. /yardim yazarak komutları görebilirsin.", parse_mode='Markdown')

# ═══════════════════════════════════════════════════════════
# FLASK APP FOR RAILWAY
# ═══════════════════════════════════════════════════════════

app = Flask(__name__)

@app.route('/')
def home():
    return jsonify({
        "status": "online",
        "service": "ETI Mutlu Kutu Bot",
        "vds_server": VDS_SERVER_URL,
        "timestamp": datetime.now().isoformat()
    })

@app.route('/health')
def health():
    vds_client = VDSClient()
    vds_status = vds_client.check_status()
    
    return jsonify({
        "bot": "running",
        "vds_connection": vds_status,
        "uptime": time.time() - start_time
    })

# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════

start_time = time.time()

def run_flask():
    """Flask server'ı başlat"""
    debug_log(f"Flask başlatılıyor: 0.0.0.0:{PORT}", "WEB")
    app.run(host='0.0.0.0', port=PORT, debug=False)

def run_bot():
    """Telegram bot'u başlat"""
    debug_log("Bot polling başlatılıyor...", "BOT")
    
    # Webhook'u temizle (önceki instance'lardan kalma)
    try:
        bot.remove_webhook()
        time.sleep(1)
    except:
        pass
    
    # Long polling başlat
    while True:
        try:
            debug_log("Polling başlatılıyor...", "BOT")
            bot.polling(none_stop=True, timeout=30)
        except Exception as e:
            debug_log(f"Polling hatası: {e}", "ERROR")
            time.sleep(5)

def main():
    print("\n" + "="*60)
    print("🤖 ETI MUTLU KUTU BOT - RAILWAY EDITION")
    print("="*60)
    print(f"🔧 Bot Token: {BOT_TOKEN[:10]}...")
    print(f"📍 VDS Server: {VDS_SERVER_URL}")
    print(f"🌐 Port: {PORT}")
    print(f"🐞 Debug: {DEBUG_MODE}")
    print("="*60)
    print("🚀 Başlatılıyor...")
    
    # VDS test
    vds_client = VDSClient()
    if vds_client.check_status():
        print("✅ VDS Server: Bağlantı başarılı")
    else:
        print("⚠️  VDS Server: Bağlantı yok")
    
    # Thread'leri başlat
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    
    flask_thread.start()
    time.sleep(2)
    bot_thread.start()
    
    # Ana thread'i bekle
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 Bot durduruluyor...")
        sys.exit(0)

if __name__ == "__main__":
    main()
