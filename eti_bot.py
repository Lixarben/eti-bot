#!/usr/bin/env python3
"""
ETİ MUTLU KUTU BOT - TAM ÇALIŞAN VERSİYON
Davet kodu kayıt sistemi
"""

import os
import sys
import time
import json
import requests
import telebot
from flask import Flask, jsonify
import threading
from datetime import datetime

print("="*60)
print("🚀 ETİ MUTLU KUTU BOT - PRODUCTION")
print("="*60)

# CONFIGURATION
BOT_TOKEN = os.environ.get("BOT_TOKEN", "7968457283:AAG-8tILmgVJvZmKv8m5DMUwX6x7aF3kYeg")
VDS_URL = os.environ.get("VDS_SERVER_URL", "http://194.62.55.201:8080")
PORT = int(os.environ.get("PORT", 8080))

# Bot oluştur
try:
    bot = telebot.TeleBot(BOT_TOKEN)
    print(f"✅ Bot başlatıldı: {BOT_TOKEN[:15]}...")
except Exception as e:
    print(f"❌ Bot hatası: {e}")
    sys.exit(1)

# User state management
user_data = {}

# VDS Functions
def check_vds():
    """VDS server kontrolü"""
    try:
        response = requests.get(f"{VDS_URL}/health", timeout=5)
        return response.status_code == 200
    except:
        return False

def register_to_vds(davet_kodu, adet=1):
    """VDS'ye kayıt isteği gönder"""
    try:
        url = f"{VDS_URL}/kayit"
        data = {"davet_kodu": davet_kodu, "adet": adet}
        response = requests.post(url, json=data, timeout=30)
        return response.json()
    except Exception as e:
        return {"success": False, "error": str(e)}

# Telegram Handlers
@bot.message_handler(commands=['start', 'basla'])
def start_command(message):
    user_id = message.from_user.id
    
    welcome_msg = """
🤖 *ETİ MUTLU KUTU BOT* v2.0

📍 *VDS Server:* `http://194.62.55.201:8080`
📡 *Durum:* {}

📋 *Kullanım:*
1. Davet kodunu gönder (10 haneli)
2. Kaç adet istediğini yaz (1-500)
3. Bot işlemi başlatır

📝 *Örnek:*
`8701545434` (kod)
`50` (adet)

🔧 *Komutlar:*
/start - Bu mesaj
/test - VDS test
/durum - Sistem durumu
/yardim - Yardım

⚡ *Not:* VDS server kapalı olsa bile bot çalışır!
""".format("✅ AKTİF" if check_vds() else "❌ KAPALI")
    
    bot.reply_to(message, welcome_msg, parse_mode='Markdown')
    
    # User state'i sıfırla
    user_data[user_id] = {"state": "waiting_code"}

@bot.message_handler(commands=['test'])
def test_command(message):
    if check_vds():
        bot.reply_to(message, "✅ *VDS SERVER ÇALIŞIYOR!*\n\nKayıt yapılabilir.", parse_mode='Markdown')
    else:
        bot.reply_to(message, "❌ *VDS SERVER KAPALI!*\n\nSunucu: `{}`\n\nBot çalışıyor ama VDS bağlantısı yok.".format(VDS_URL), parse_mode='Markdown')

@bot.message_handler(commands=['durum', 'status'])
def status_command(message):
    user_id = message.from_user.id
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    status_msg = f"""
📊 *SİSTEM DURUMU*

🤖 Bot: ✅ ÇALIŞIYOR
📍 VDS: {'✅ AKTİF' if check_vds() else '❌ KAPALI'}
👤 Kullanıcı ID: `{user_id}`
🕐 Saat: {current_time}
🚀 Platform: Railway

📈 *İstatistikler:*
Toplam Kullanıcı: {len(user_data)}
VDS URL: {VDS_URL}
"""
    bot.reply_to(message, status_msg, parse_mode='Markdown')

@bot.message_handler(commands=['yardim', 'help'])
def help_command(message):
    help_msg = """
📋 *YARDIM MENÜSÜ*

🤖 *Ana Komutlar:*
/start - Botu başlat
/test - VDS bağlantı testi
/durum - Sistem durumu
/yardim - Bu mesaj

📝 *Kullanım Adımları:*
1. 10 haneli davet kodunu gönder
   Örnek: `8701545434`
   
2. Kaç adet istediğini yaz
   Örnek: `50` (1-500 arası)

3. Bot işlemi başlatacak

⚠️ *Not:*
- VDS server kapalıysa kayıt yapılamaz
- Bot her zaman çalışır durumda
- Her kod için maksimum 500 adet
"""
    bot.reply_to(message, help_msg, parse_mode='Markdown')

@bot.message_handler(func=lambda message: True)
def handle_messages(message):
    user_id = message.from_user.id
    text = message.text.strip()
    
    # Eğer user için state yoksa, oluştur
    if user_id not in user_data:
        user_data[user_id] = {"state": "waiting_code"}
    
    current_state = user_data[user_id].get("state", "waiting_code")
    
    # STATE 1: Kod bekleniyor
    if current_state == "waiting_code":
        if text.isdigit() and len(text) == 10:
            # Geçerli kod
            user_data[user_id] = {
                "state": "waiting_count",
                "davet_kodu": text
            }
            
            reply_msg = f"""
🎯 *Kod Alındı!*

Davet Kodu: `{text}`

Şimdi kaç adet kayıt yapmak istiyorsun?
(1 ile 500 arasında bir sayı yaz)

Örnek: `50`
"""
            bot.reply_to(message, reply_msg, parse_mode='Markdown')
            
        else:
            # Geçersiz kod
            bot.reply_to(message, "❌ *Geçersiz Kod!*\n\nLütfen 10 haneli bir davet kodu gönder.\n\nÖrnek: `8701545434`", parse_mode='Markdown')
    
    # STATE 2: Adet bekleniyor
    elif current_state == "waiting_count":
        if text.isdigit():
            adet = int(text)
            
            if 1 <= adet <= 500:
                davet_kodu = user_data[user_id].get("davet_kodu", "")
                
                # VDS kontrolü
                if not check_vds():
                    bot.reply_to(message, f"""
❌ *VDS SERVER KAPALI!*

Davet Kodu: `{davet_kodu}`
Adet: `{adet}`

📍 VDS Server: {VDS_URL}

⚠️ VDS server şu anda kapalı.
Lütfen daha sonra tekrar deneyin.

/test yazarak durumu kontrol edebilirsin.
""", parse_mode='Markdown')
                    
                    # State'i sıfırla
                    user_data[user_id] = {"state": "waiting_code"}
                    return
                
                # Kayıt işlemini başlat
                processing_msg = f"""
⚡ *KAYIT BAŞLATILIYOR*

✅ Kod: `{davet_kodu}`
✅ Adet: `{adet}`
📍 VDS: {VDS_URL}

⏳ VDS sunucusuna istek gönderiliyor...
Bu işlem birkaç saniye sürebilir.
"""
                msg = bot.reply_to(message, processing_msg, parse_mode='Markdown')
                
                # VDS'ye kayıt isteği gönder (thread'de)
                def send_registration():
                    try:
                        result = register_to_vds(davet_kodu, adet)
                        
                        if result.get("success"):
                            success_msg = f"""
🎉 *KAYIT BAŞARILI!*

✅ Kod: `{davet_kodu}`
✅ Adet: `{adet}`
✅ Tamamlanan: `{result.get('completed', adet)}`
❌ Başarısız: `{result.get('failed', 0)}`

⏱️ Süre: {result.get('duration', 'N/A')}
📱 SMS: {result.get('sms_code', 'N/A')}

📍 VDS: {VDS_URL}
"""
                            bot.edit_message_text(
                                chat_id=message.chat.id,
                                message_id=msg.message_id,
                                text=success_msg,
                                parse_mode='Markdown'
                            )
                        else:
                            error_msg = f"""
❌ *KAYIT BAŞARISIZ!*

Kod: `{davet_kodu}`
Adet: `{adet}`
Hata: {result.get('error', 'Bilinmeyen hata')}

📍 VDS: {VDS_URL}

⚠️ Lütfen daha sonra tekrar deneyin.
"""
                            bot.edit_message_text(
                                chat_id=message.chat.id,
                                message_id=msg.message_id,
                                text=error_msg,
                                parse_mode='Markdown'
                            )
                    
                    except Exception as e:
                        error_msg = f"""
❌ *SİSTEM HATASI!*

Hata: {str(e)}

📍 VDS: {VDS_URL}

⚠️ Teknik bir sorun oluştu.
"""
                        bot.edit_message_text(
                            chat_id=message.chat.id,
                            message_id=msg.message_id,
                            text=error_msg,
                            parse_mode='Markdown'
                        )
                    
                    finally:
                        # State'i sıfırla
                        user_data[user_id] = {"state": "waiting_code"}
                
                # Thread başlat
                thread = threading.Thread(target=send_registration)
                thread.start()
                
            else:
                bot.reply_to(message, "❌ *Geçersiz Adet!*\n\nLütfen 1 ile 500 arasında bir sayı girin.\n\nÖrnek: `50`", parse_mode='Markdown')
        else:
            bot.reply_to(message, "❌ *Sayı Girin!*\n\nLütfen sadece rakamlardan oluşan bir sayı girin.\n\nÖrnek: `50`", parse_mode='Markdown')

# Flask Web Server
app = Flask(__name__)

@app.route('/')
def home():
    return jsonify({
        "status": "online",
        "service": "ETİ Mutlu Kutu Bot",
        "version": "2.0",
        "vds_url": VDS_URL,
        "vds_status": "active" if check_vds() else "inactive",
        "users": len(user_data),
        "timestamp": datetime.now().isoformat()
    })

@app.route('/health')
def health():
    return jsonify({
        "status": "healthy",
        "bot": "running",
        "vds": check_vds(),
        "uptime": time.time() - start_time
    })

# Run functions
def run_web_server():
    """Web server'ı başlat"""
    print(f"🌐 Web server başlatılıyor: 0.0.0.0:{PORT}")
    app.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False)

def run_telegram_bot():
    """Telegram bot'u başlat"""
    print("🤖 Telegram bot polling başlatılıyor...")
    
    # Önceki webhook'u temizle
    try:
        bot.remove_webhook()
        time.sleep(1)
    except:
        pass
    
    # Polling başlat
    while True:
        try:
            print("📡 Telegram API'ye bağlanılıyor...")
            bot.polling(none_stop=True, timeout=30, long_polling_timeout=30)
        except Exception as e:
            print(f"⚠️ Bot hatası: {e}")
            time.sleep(5)

# Main
start_time = time.time()

def main():
    print(f"\n📍 VDS Server: {VDS_URL}")
    print(f"🔧 Port: {PORT}")
    print(f"👥 Kullanıcılar: {len(user_data)}")
    print("="*60)
    
    # VDS test
    vds_status = "✅ AKTİF" if check_vds() else "❌ KAPALI"
    print(f"📡 VDS Durum: {vds_status}")
    
    # Thread'leri başlat
    web_thread = threading.Thread(target=run_web_server, daemon=True)
    bot_thread = threading.Thread(target=run_telegram_bot, daemon=True)
    
    web_thread.start()
    time.sleep(2)
    bot_thread.start()
    
    print("\n✅ SİSTEM HAZIR!")
    print("="*60)
    print("📱 Telegram'da botunuzu kullanabilirsiniz")
    print("🔗 Health Check: https://your-app.railway.app/health")
    print("="*60)
    
    # Ana thread
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 Bot durduruluyor...")

if __name__ == "__main__":
    main()
