#!/usr/bin/env python3
"""
ETI BOT - Railway için Basit Versiyon
"""

import os
import sys
import time
import requests
import telebot
from flask import Flask, jsonify
import threading

print("="*60)
print("🚀 ETI BOT BAŞLATILIYOR...")
print("="*60)

# 1. BOT TOKEN KONTROLÜ
BOT_TOKEN = os.environ.get("BOT_TOKEN")

if not BOT_TOKEN:
    print("❌ HATA: BOT_TOKEN bulunamadı!")
    print("")
    print("📋 RAILWAY'DE AYARLA:")
    print("1. Railway dashboard'a git")
    print("2. Projeni seç")
    print("3. 'Variables' sekmesine tıkla")
    print("4. 'New Variable' butonuna tıkla")
    print("5. Name: BOT_TOKEN")
    print("6. Value: 7968457283:AAG-8tILmgVJvZmKv8m5DMUwX6x7aF3kYeg")
    print("7. 'Add' butonuna tıkla")
    print("8. 'Redeploy' butonuna tıkla")
    print("")
    print("⏳ 30 saniye bekleyip kapanıyor...")
    time.sleep(30)
    sys.exit(1)

print(f"✅ BOT_TOKEN: {BOT_TOKEN[:10]}...")

# 2. DİĞER AYARLAR
VDS_URL = os.environ.get("VDS_SERVER_URL", "http://194.62.55.201:8080")
DEBUG = os.environ.get("DEBUG", "True").lower() == "true"
PORT = int(os.environ.get("PORT", 8080))

print(f"📍 VDS Server: {VDS_URL}")
print(f"🐞 Debug: {DEBUG}")
print(f"🌐 Port: {PORT}")
print("="*60)

# 3. BOT'U OLUŞTUR
try:
    bot = telebot.TeleBot(BOT_TOKEN)
    print("🤖 Bot başarıyla oluşturuldu")
except Exception as e:
    print(f"❌ Bot oluşturulamadı: {e}")
    sys.exit(1)

# 4. VDS TEST FONKSİYONU
def test_vds():
    try:
        print(f"🔍 VDS test ediliyor: {VDS_URL}")
        response = requests.get(f"{VDS_URL}/health", timeout=5)
        if response.status_code == 200:
            print("✅ VDS Server: ÇALIŞIYOR")
            return True
        else:
            print(f"⚠️ VDS Server: HATA ({response.status_code})")
            return False
    except Exception as e:
        print(f"❌ VDS Server: BAĞLANAMADI - {e}")
        return False

# 5. TELEGRAM KOMUTLARI
@bot.message_handler(commands=['start'])
def start_cmd(message):
    vds_status = "✅ ÇALIŞIYOR" if test_vds() else "❌ KAPALI"
    
    msg = f"""
🤖 *ETİ MUTLU KUTU BOT*

📍 *VDS Server:* {VDS_URL}
📡 *Durum:* {vds_status}

📋 *Komutlar:*
/start - Bu mesajı göster
/test - VDS bağlantı testi
/durum - Sistem durumu
/yardim - Yardım menüsü

⚡ Bot hazır! Davet kodunu gönder.
"""
    bot.reply_to(message, msg, parse_mode='Markdown')

@bot.message_handler(commands=['test'])
def test_cmd(message):
    if test_vds():
        bot.reply_to(message, "✅ *VDS SERVER ÇALIŞIYOR!*", parse_mode='Markdown')
    else:
        bot.reply_to(message, "❌ *VDS SERVER KAPALI!*", parse_mode='Markdown')

@bot.message_handler(commands=['durum'])
def status_cmd(message):
    import datetime
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    msg = f"""
📊 *SİSTEM DURUMU*

🤖 Bot: ÇALIŞIYOR
📍 VDS: {VDS_URL}
👤 Kullanıcı: {message.from_user.id}
🕐 Zaman: {now}
🚀 Railway: Aktif
"""
    bot.reply_to(message, msg, parse_mode='Markdown')

@bot.message_handler(commands=['yardim'])
def help_cmd(message):
    msg = """
📋 *YARDIM MENÜSÜ*

• /start - Botu başlat
• /test - VDS bağlantı testi
• /durum - Sistem durumu
• /yardim - Bu mesaj

📝 *Kullanım:*
1. Davet kodunu gönder (örn: 8701545434)
2. Kaç adet istediğini yaz
3. Bot işlemi başlatır

📍 *VDS URL:* """ + VDS_URL
    
    bot.reply_to(message, msg, parse_mode='Markdown')

@bot.message_handler(func=lambda message: True)
def handle_text(message):
    text = message.text.strip()
    
    if text.isdigit() and len(text) == 10:
        bot.reply_to(message, f"🎯 *Kod alındı:* `{text}`\n\nKaç adet istiyorsun? (1-100)", parse_mode='Markdown')
    elif text.isdigit() and 1 <= int(text) <= 100:
        bot.reply_to(message, f"✅ *{text} adet* kayıt başlatılıyor...\n\n⚡ VDS sunucusuna istek gönderiliyor.", parse_mode='Markdown')
    else:
        bot.reply_to(message, "🤔 Anlamadım. /yardim yazarak yardım alabilirsin.", parse_mode='Markdown')

# 6. FLASK WEB SERVER (Railway Health Check için)
app = Flask(__name__)

@app.route('/')
def home():
    return jsonify({
        "status": "online",
        "service": "ETI Bot",
        "bot": "running",
        "vds_url": VDS_URL,
        "timestamp": time.time()
    })

@app.route('/health')
def health():
    vds_ok = test_vds()
    return jsonify({
        "bot": "running",
        "vds_connection": vds_ok,
        "uptime": time.time() - start_time
    })

# 7. ANA FONKSİYONLAR
def run_web():
    """Web server'ı başlat"""
    print(f"🌐 Web server başlatılıyor: 0.0.0.0:{PORT}")
    app.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False)

def run_bot():
    """Telegram bot'u başlat"""
    print("🤖 Telegram bot başlatılıyor...")
    while True:
        try:
            bot.polling(none_stop=True, timeout=30)
        except Exception as e:
            print(f"⚠️ Bot hatası: {e}")
            time.sleep(5)

# 8. MAIN
start_time = time.time()

def main():
    print("\n" + "="*60)
    print("🚀 SİSTEM BAŞLATILIYOR...")
    print("="*60)
    
    # VDS test
    test_vds()
    
    # Thread'leri başlat
    web_thread = threading.Thread(target=run_web, daemon=True)
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    
    web_thread.start()
    time.sleep(2)  # Web server'ın başlaması için bekle
    bot_thread.start()
    
    print("✅ Tüm servisler başlatıldı!")
    print("="*60)
    print("📱 Telegram'da botunuzu kullanabilirsiniz")
    print("="*60)
    
    # Ana thread'i çalışır tut
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 Bot durduruluyor...")

if __name__ == "__main__":
    main()
