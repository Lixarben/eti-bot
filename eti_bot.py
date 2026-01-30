#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETI MUTLU KUTU - VDS TELEGRAM BOT v2.0 (Railway Uyumlu)
- Single instance için optimize edildi
- Webhook polling desteği
"""

import threading
import time
import re
import json
import sys
import signal
import ssl
import urllib.request
import urllib.parse
import os
from dataclasses import dataclass
from typing import Optional, Dict, List
import logging
from datetime import datetime

# Telegram Bot
import telebot
from telebot import types

# VDS için requests
import requests

# ═══════════════════════════════════════════════════════════
# KONFİGÜRASYON
# ═══════════════════════════════════════════════════════════

@dataclass
class Config:
    # Telegram Bot
    BOT_TOKEN: str = os.environ.get("7968457283:AAG-8tILmgVJvZmKv8m5DMUwX6x7aF3kYeg")
    
    # Railway Settings
    RAILWAY_ENVIRONMENT: bool = os.environ.get("RAILWAY_ENVIRONMENT", "True").lower() == "true"
    RAILWAY_PUBLIC_DOMAIN: str = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "")
    
    # Webhook Settings
    USE_WEBHOOK: bool = os.environ.get("USE_WEBHOOK", "True").lower() == "true"
    WEBHOOK_PORT: int = int(os.environ.get("PORT", 8080))
    
    # VDS Ayarları
    VDS_SERVER_URL: str = os.environ.get("VDS_SERVER_URL", "http://194.62.55.201:8080")
    MAX_VDS_WORKERS: int = 4
    
    # API Bilgileri
    API_NAME: str = "SeoClas"
    API_KEY: str = "WTBLWC9yUHFtcjlmMXhBRXVaVjFUZz09"
    BASE_URL: str = "https://api.durianrcs.com/out/ext_api"
    PID: str = "6354"
    
    # Zaman Ayarları
    SMS_TIMEOUT: float = 25.0
    
    # Worker Limits
    MAX_CODES: int = 8
    
    # Debug
    DEBUG_MODE: bool = os.environ.get("DEBUG_MODE", "True").lower() == "true"

CONFIG = Config()

# ═══════════════════════════════════════════════════════════
# DEBUG UTILS
# ═══════════════════════════════════════════════════════════

def debug_log(msg: str, level: str = "INFO"):
    """Terminale debug mesajı yaz"""
    if CONFIG.DEBUG_MODE:
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        print(f"[{timestamp}] [{level}] {msg}")

# ═══════════════════════════════════════════════════════════
# TELEGRAM BOT & STATE MANAGEMENT
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
bot = telebot.TeleBot(CONFIG.BOT_TOKEN)

# ═══════════════════════════════════════════════════════════
# VDS CLIENT
# ═══════════════════════════════════════════════════════════

class VDSClient:
    def __init__(self):
        self.base_url = CONFIG.VDS_SERVER_URL
        self.timeout = 60
    
    def check_status(self) -> bool:
        """VDS server çalışıyor mu kontrol et"""
        try:
            response = requests.get(f"{self.base_url}/health", timeout=5)
            return response.status_code == 200
        except:
            return False
    
    def kayit_yap(self, davet_kodu: str) -> dict:
        """VDS server'a kayıt isteği gönder"""
        try:
            url = f"{self.base_url}/kayit"
            data = {"davet_kodu": davet_kodu}
            
            debug_log(f"📡 VDS'ye istek: {davet_kodu}", "VDS")
            
            response = requests.post(url, json=data, timeout=self.timeout)
            result = response.json()
            
            debug_log(f"📡 VDS cevabı: {result.get('success', False)}", "VDS")
            return result
            
        except requests.exceptions.ConnectionError:
            debug_log("❌ VDS server'a bağlanılamadı!", "VDS")
            return {"success": False, "error": "VDS server'a bağlanılamadı"}
        except Exception as e:
            debug_log(f"❌ VDS hatası: {str(e)}", "VDS")
            return {"success": False, "error": str(e)}

# ═══════════════════════════════════════════════════════════
# VDS JOB ENGINE
# ═══════════════════════════════════════════════════════════

class VDSJobEngine:
    def __init__(self, user_id: int, davet_kodlari: List[str], hedefler: List[int]):
        self.user_id = user_id
        self.davet_kodlari = davet_kodlari
        self.hedefler = hedefler
        
        # VDS client
        self.vds_client = VDSClient()
        
        # İstatistikler
        self.stats = {
            'baslangic': time.time(),
            'tamamlanan': [0] * len(davet_kodlari),
            'basarisiz': [0] * len(davet_kodlari),
            'toplam_hedef': sum(hedefler),
            'toplam_tamamlanan': 0,
            'toplam_basarisiz': 0,
            'son_guncelleme': time.time(),
        }
        
        self.stop_event = threading.Event()
        self.lock = threading.Lock()
        
        # Worker sayısı
        toplam_hedef = sum(hedefler)
        self.workers = min(toplam_hedef, CONFIG.MAX_VDS_WORKERS)
        
        debug_log(f"VDS Job başlatıldı - User: {user_id}", "JOB")
        debug_log(f"  Kodlar: {davet_kodlari}", "JOB")
        debug_log(f"  Hedefler: {hedefler}", "JOB")
        debug_log(f"  Toplam hedef: {sum(hedefler)}", "JOB")
        debug_log(f"  Workers: {self.workers}", "JOB")
    
    def _vds_worker_task(self, worker_id: int):
        """VDS worker görevi"""
        debug_log(f"VDS Worker {worker_id} başladı", "WORKER")
        
        worker_iteration = 0
        
        while not self.stop_event.is_set():
            worker_iteration += 1
            
            # Hangi kod için çalışacak?
            kod_index = (worker_id + worker_iteration) % len(self.davet_kodlari)
            davet_kodu = self.davet_kodlari[kod_index]
            hedef = self.hedefler[kod_index]
            
            # Bu kod tamamlandı mı?
            with self.lock:
                tamamlanan = self.stats['tamamlanan'][kod_index]
                if tamamlanan >= hedef:
                    # Tüm kodlar tamamlandı mı kontrol et
                    all_done = True
                    for i, h in enumerate(self.hedefler):
                        if self.stats['tamamlanan'][i] < h:
                            all_done = False
                            break
                    
                    if all_done:
                        debug_log(f"Worker {worker_id}: TÜM KODLAR TAMAMLANDI, ÇIKIYOR", "WORKER")
                        self.stop_event.set()
                        break
                    
                    continue
            
            debug_log(f"VDS Worker {worker_id}: Kod {davet_kodu} çalışıyor ({tamamlanan}/{hedef})", "WORKER")
            
            # VDS SERVER'A İSTEK GÖNDER
            result = self.vds_client.kayit_yap(davet_kodu)
            
            with self.lock:
                if result.get('success'):
                    self.stats['tamamlanan'][kod_index] += 1
                    self.stats['toplam_tamamlanan'] += 1
                    
                    yuzde = (self.stats['tamamlanan'][kod_index] / hedef * 100)
                    debug_log(f"Worker {worker_id}: ✅ VDS Kod {davet_kodu}: {self.stats['tamamlanan'][kod_index]}/{hedef} (%{yuzde:.1f})", "WORKER")
                    
                    # Her 10 kayıtta bir bildirim
                    if self.stats['toplam_tamamlanan'] % 10 == 0:
                        self._send_progress_update(last_sms=result.get('sms_code', ''))
                else:
                    self.stats['basarisiz'][kod_index] += 1
                    self.stats['toplam_basarisiz'] += 1
                    debug_log(f"Worker {worker_id}: ❌ VDS hatası: {result.get('error', 'Bilinmeyen')}", "WORKER")
            
            time.sleep(1)
        
        debug_log(f"VDS Worker {worker_id} sonlandı", "WORKER")
    
    def _send_progress_update(self, last_sms: str = ""):
        """Telegram'a ilerleme güncellemesi gönder"""
        try:
            elapsed = time.time() - self.stats['baslangic']
            speed = self.stats['toplam_tamamlanan'] / (elapsed / 60) if elapsed > 60 else 0
            
            msg = f"⚡ *VDS İlerleme*\n\n"
            msg += f"📍 VDS: {CONFIG.VDS_SERVER_URL}\n"
            msg += f"✅ Tamamlanan: {self.stats['toplam_tamamlanan']}/{self.stats['toplam_hedef']}\n"
            msg += f"❌ Başarısız: {self.stats['toplam_basarisiz']}\n"
            msg += f"⏱️ Süre: {elapsed:.0f}s\n"
            
            if speed > 0:
                msg += f"⚡ Hız: {speed:.1f} kayıt/dk\n"
            
            msg += f"👥 Workers: {self.workers}"
            
            if last_sms:
                msg += f"\n📱 Son SMS: {last_sms}"
            
            bot.send_message(self.user_id, msg, parse_mode='Markdown')
            
        except:
            pass
    
    def start(self):
        debug_log("VDS job başlatılıyor...", "JOB")
        threads = []
        
        # WORKER'LARI BAŞLAT
        for i in range(self.workers):
            t = threading.Thread(target=self._vds_worker_task, args=(i+1,))
            t.daemon = True
            t.start()
            threads.append(t)
            time.sleep(0.3)
        
        # ANA KONTROL DÖNGÜSÜ
        try:
            last_update = time.time()
            
            while not self.stop_event.is_set():
                time.sleep(2)
                
                # Her 30 saniyede bir durum kontrolü
                current_time = time.time()
                if current_time - last_update >= 30:
                    last_update = current_time
                    
                    with self.lock:
                        # Tüm hedefler tamamlandı mı?
                        all_done = True
                        for i, h in enumerate(self.hedefler):
                            if self.stats['tamamlanan'][i] < h:
                                all_done = False
                                break
                        
                        if all_done:
                            debug_log(f"✅ TÜM HEDEFLER TAMAMLANDI!", "JOB")
                            self.stop_event.set()
                            break
                        
                        # Progress log
                        progress_msg = f"📈 VDS Progress: "
                        for i, (kod, hedef) in enumerate(zip(self.davet_kodlari, self.hedefler)):
                            tamam = self.stats['tamamlanan'][i]
                            if hedef > 0:
                                yuzde = (tamam / hedef * 100)
                                progress_msg += f"{kod}:{tamam}/{hedef} (%{yuzde:.1f}) "
                        debug_log(progress_msg, "PROGRESS")
                
                # 5 dakikada bir durum mesajı gönder
                if current_time - self.stats['son_guncelleme'] >= 300:
                    self._send_progress_update()
                    with self.lock:
                        self.stats['son_guncelleme'] = current_time
                        
        except KeyboardInterrupt:
            debug_log("Keyboard interrupt", "JOB")
            self.stop_event.set()
        except Exception as e:
            debug_log(f"Ana döngü hatası: {e}", "JOB")
        
        # Thread'leri bekle
        for t in threads:
            t.join(timeout=10)
        
        debug_log("VDS job tamamlandı", "JOB")
        return self.get_final_report()
    
    def stop(self):
        debug_log("VDS job durduruluyor...", "JOB")
        self.stop_event.set()
    
    def get_status(self) -> Dict:
        with self.lock:
            elapsed = time.time() - self.stats['baslangic']
            return {
                'elapsed': elapsed,
                'tamamlanan': self.stats['tamamlanan'].copy(),
                'basarisiz': self.stats['basarisiz'].copy(),
                'toplam_tamamlanan': self.stats['toplam_tamamlanan'],
                'toplam_basarisiz': self.stats['toplam_basarisiz'],
                'toplam_hedef': self.stats['toplam_hedef'],
                'workers': self.workers,
                'is_running': not self.stop_event.is_set()
            }
    
    def get_final_report(self) -> str:
        with self.lock:
            elapsed = time.time() - self.stats['baslangic']
            speed = self.stats['toplam_tamamlanan'] / (elapsed / 60) if elapsed > 0 else 0
            
            report = f"⚡ *VDS İŞLEM TAMAMLANDI!*\n\n"
            
            for i, kod in enumerate(self.davet_kodlari):
                tamam = self.stats['tamamlanan'][i]
                hedef = self.hedefler[i]
                basarisiz = self.stats['basarisiz'][i]
                
                if tamam == hedef:
                    report += f"✅ *Kod `{kod}`*: {tamam}/{hedef}\n"
                elif tamam > 0:
                    yuzde = (tamam / hedef * 100)
                    report += f"⚠️ *Kod `{kod}`*: {tamam}/{hedef} (%{yuzde:.1f}, {basarisiz} başarısız)\n"
                else:
                    report += f"❌ *Kod `{kod}`*: 0/{hedef} ({basarisiz} başarısız)\n"
            
            report += f"\n📊 *TOPLAM*: {self.stats['toplam_tamamlanan']}/{self.stats['toplam_hedef']}\n"
            report += f"❌ *Başarısız*: {self.stats['toplam_basarisiz']}\n"
            report += f"⏱️ *Süre*: {elapsed:.0f}s\n"
            report += f"👥 *Workers*: {self.workers}\n"
            report += f"📍 *VDS URL*: {CONFIG.VDS_SERVER_URL}\n"
            
            if elapsed > 0:
                report += f"⚡ *Hız*: {speed:.1f} kayıt/dk"
            
            return report

# ═══════════════════════════════════════════════════════════
# TELEGRAM HANDLERS
# ═══════════════════════════════════════════════════════════

@bot.message_handler(commands=['start'])
def start_command(message):
    user_id = message.from_user.id
    
    if bot_state.has_active_job(user_id):
        bot.reply_to(message, "🚫 *Zaten devam eden bir işleminiz var!*\n\n📊 Durum için: /bilgi\n🛑 Durdurmak için: /stop", parse_mode='Markdown')
        return
    
    # VDS kontrolü
    vds_client = VDSClient()
    if not vds_client.check_status():
        bot.reply_to(
            message,
            "⚠️ *VDS SERVER ÇALIŞMIYOR!*\n\n"
            f"VDS server'a bağlanılamadı:\n"
            f"`{CONFIG.VDS_SERVER_URL}`\n\n"
            "1. VDS server'ı kontrol edin\n"
            "2. Sunucunun çalıştığından emin olun\n"
            "3. Firewall ayarlarını kontrol edin",
            parse_mode='Markdown'
        )
        return
    
    bot_state.clear_state(user_id)
    bot_state.set_state(user_id, 'waiting_for_codes')
    bot_state.set_data(user_id, 'davet_kodlari', [])
    
    msg = f"⚡ *ETI MUTLU KUTU BOT (VDS MOD)*\n\n"
    msg += "📝 *Davet Kodları*\n"
    msg += f"Davet kodlarınızı girin (max {CONFIG.MAX_CODES}):\n\n"
    msg += "• *Tek kod:*\n"
    msg += "`8701545434`\n\n"
    msg += "• *Çoklu kod (alt alta):*\n"
    msg += "```\n8701545434\n1234567890\n9876543210\n```\n\n"
    msg += "📌 Her kod için ayrı adet belirleyeceksiniz."
    msg += f"\n\n📍 *VDS Server:* {CONFIG.VDS_SERVER_URL}"
    
    bot.reply_to(message, msg, parse_mode='Markdown')
    debug_log(f"User {user_id}: /start komutu", "TELEGRAM")

@bot.message_handler(func=lambda message: bot_state.get_state(message.from_user.id) == 'waiting_for_codes')
def handle_codes(message):
    user_id = message.from_user.id
    text = message.text.strip()
    
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    if len(lines) > CONFIG.MAX_CODES:
        bot.reply_to(message, f"❌ *Maksimum {CONFIG.MAX_CODES} kod girebilirsiniz!*", parse_mode='Markdown')
        return
    
    if len(lines) == 0:
        bot.reply_to(message, "❌ *En az 1 kod girmelisiniz!*", parse_mode='Markdown')
        return
    
    # Kod format kontrolü
    for kod in lines:
        if not kod.isdigit():
            bot.reply_to(message, f"❌ *Geçersiz kod: {kod}*\n\nKodlar sadece rakamlardan oluşmalıdır!", parse_mode='Markdown')
            return
    
    bot_state.set_data(user_id, 'davet_kodlari', lines)
    bot_state.set_state(user_id, 'waiting_for_counts')
    bot_state.set_data(user_id, 'current_code_index', 0)
    
    codes = lines
    first_code = codes[0]
    
    msg = f"📋 *Kod {1}/{len(codes)}*\n\n"
    msg += f"Kod: `{first_code}`\n\n"
    msg += "Bu kod için kaç adet istiyorsunuz? *(1-500)*"
    
    bot.reply_to(message, msg, parse_mode='Markdown')
    debug_log(f"User {user_id}: {len(lines)} kod girdi", "TELEGRAM")

@bot.message_handler(func=lambda message: bot_state.get_state(message.from_user.id) == 'waiting_for_counts')
def handle_counts(message):
    user_id = message.from_user.id
    text = message.text.strip()
    
    try:
        count = int(text)
        if count < 1 or count > 500:
            bot.reply_to(message, "❌ *1-500 arası bir sayı girin!*", parse_mode='Markdown')
            return
    except:
        bot.reply_to(message, "❌ *Geçerli bir sayı girin!*", parse_mode='Markdown')
        return
    
    codes = bot_state.get_data(user_id, 'davet_kodlari', [])
    current_index = bot_state.get_data(user_id, 'current_code_index', 0)
    
    if 'hedefler' not in bot_state.get_data(user_id, '_dict', {}):
        bot_state.set_data(user_id, 'hedefler', [])
    
    hedefler = bot_state.get_data(user_id, 'hedefler', [])
    hedefler.append(count)
    bot_state.set_data(user_id, 'hedefler', hedefler)
    
    current_index += 1
    
    if current_index < len(codes):
        bot_state.set_data(user_id, 'current_code_index', current_index)
        next_code = codes[current_index]
        
        msg = f"✅ *Kod {current_index}/{len(codes)} kaydedildi*\n\n"
        msg += f"📋 *Kod {current_index+1}/{len(codes)}*\n\n"
        msg += f"Kod: `{next_code}`\n\n"
        msg += "Bu kod için kaç adet istiyorsunuz? *(1-500)*"
        
        bot.reply_to(message, msg, parse_mode='Markdown')
        debug_log(f"User {user_id}: Kod {current_index} için {count} adet", "TELEGRAM")
    else:
        bot_state.set_state(user_id, 'processing')
        
        codes = bot_state.get_data(user_id, 'davet_kodlari', [])
        hedefler = bot_state.get_data(user_id, 'hedefler', [])
        
        workers = CONFIG.MAX_VDS_WORKERS
        
        start_msg = f"⚡ *VDS İşlem Başlatıldı!*\n\n"
        start_msg += f"📊 *Özet*\n"
        start_msg += f"• Kod sayısı: {len(codes)}\n"
        start_msg += f"• Toplam hedef: {sum(hedefler)}\n"
        start_msg += f"• Workers: {min(sum(hedefler), workers)}\n\n"
        
        start_msg += "📋 *Kod Listesi*\n"
        for i, (kod, hedef) in enumerate(zip(codes, hedefler)):
            start_msg += f"{i+1}. `{kod}` → {hedef} adet\n"
        
        start_msg += "\n⏳ *İşlem başlıyor...*\n\n"
        start_msg += "📈 Durum için: /bilgi\n"
        start_msg += "🛑 Durdurmak için: /stop\n"
        start_msg += "💡 Yardım için: /yardim\n\n"
        start_msg += f"📍 *VDS MOD:* {CONFIG.VDS_SERVER_URL}"
        
        bot.reply_to(message, start_msg, parse_mode='Markdown')
        debug_log(f"User {user_id}: Tüm kodlar alındı, VDS job başlatılıyor", "TELEGRAM")
        
        def run_job():
            job = VDSJobEngine(user_id, codes, hedefler)
            bot_state.set_active_job(user_id, job)
            
            try:
                final_report = job.start()
                bot.send_message(user_id, final_report, parse_mode='Markdown')
                debug_log(f"User {user_id}: VDS Job tamamlandı", "TELEGRAM")
            except Exception as e:
                error_msg = f"❌ *Hata oluştu!*\n\n`{str(e)}`"
                bot.send_message(user_id, error_msg, parse_mode='Markdown')
                debug_log(f"User {user_id}: VDS Job hatası - {e}", "TELEGRAM")
            finally:
                bot_state.remove_active_job(user_id)
                bot_state.clear_state(user_id)
        
        thread = threading.Thread(target=run_job, daemon=True)
        thread.start()

@bot.message_handler(commands=['bilgi'])
def info_command(message):
    user_id = message.from_user.id
    
    job = bot_state.get_active_job(user_id)
    if not job:
        bot.reply_to(message, "📭 *Aktif bir işlem yok!*\n\nYeni işlem başlatmak için: /start", parse_mode='Markdown')
        return
    
    status = job.get_status()
    
    msg = f"⚡ *VDS DURUM RAPORU*\n\n"
    
    codes = bot_state.get_data(user_id, 'davet_kodlari', [])
    hedefler = bot_state.get_data(user_id, 'hedefler', [])
    
    for i, (kod, hedef) in enumerate(zip(codes, hedefler)):
        tamam = status['tamamlanan'][i]
        basarisiz = status['basarisiz'][i]
        yuzde = (tamam / hedef * 100) if hedef > 0 else 0
        
        bar_length = 10
        filled = int(bar_length * tamam / hedef) if hedef > 0 else 0
        bar = '█' * filled + '░' * (bar_length - filled)
        
        if tamam == hedef:
            msg += f"✅ *{i+1}. Kod `{kod}`*\n"
            msg += f"   {bar} {tamam}/{hedef} (100%)\n\n"
        elif tamam > 0:
            msg += f"⏳ *{i+1}. Kod `{kod}`*\n"
            msg += f"   {bar} {tamam}/{hedef} (%{yuzde:.1f})\n"
            msg += f"   ❌ Başarısız: {basarisiz}\n\n"
        else:
            msg += f"❌ *{i+1}. Kod `{kod}`*\n"
            msg += f"   {bar} 0/{hedef} (0%)\n"
            msg += f"   ❌ Başarısız: {basarisiz}\n\n"
    
    msg += f"📈 *TOPLAM:* {status['toplam_tamamlanan']}/{status['toplam_hedef']}\n"
    msg += f"❌ *Başarısız:* {status['toplam_basarisiz']}\n"
    msg += f"⏱️ *Süre:* {status['elapsed']:.1f}s\n"
    msg += f"👥 *Workers:* {status['workers']}\n"
    
    if status['elapsed'] > 0:
        hiz = status['toplam_tamamlanan'] / (status['elapsed'] / 60)
        msg += f"⚡ *Hız:* {hiz:.1f} kayıt/dk\n"
    
    msg += f"📍 *VDS:* {CONFIG.VDS_SERVER_URL}\n"
    msg += f"🎯 *Durum:* {'✅ ÇALIŞIYOR' if status['is_running'] else '🛑 DURDURULDU'}"
    
    bot.reply_to(message, msg, parse_mode='Markdown')
    debug_log(f"User {user_id}: /bilgi komutu", "TELEGRAM")

@bot.message_handler(commands=['stop'])
def stop_command(message):
    user_id = message.from_user.id
    
    job = bot_state.get_active_job(user_id)
    if not job:
        bot.reply_to(message, "📭 *Durdurulacak işlem yok!*", parse_mode='Markdown')
        return
    
    job.stop()
    
    status = job.get_status()
    
    msg = f"⚡ *VDS İşlem Durduruldu!*\n\n"
    
    codes = bot_state.get_data(user_id, 'davet_kodlari', [])
    hedefler = bot_state.get_data(user_id, 'hedefler', [])
    
    msg += "📋 *Son Durum*\n"
    for i, (kod, hedef) in enumerate(zip(codes, hedefler)):
        tamam = status['tamamlanan'][i]
        basarisiz = status['basarisiz'][i]
        
        if tamam == hedef:
            msg += f"✅ {i+1}. `{kod}`: {tamam}/{hedef}\n"
        elif tamam > 0:
            msg += f"⚠️ {i+1}. `{kod}`: {tamam}/{hedef} ({basarisiz} başarısız)\n"
        else:
            msg += f"❌ {i+1}. `{kod}`: 0/{hedef} ({basarisiz} başarısız)\n"
    
    msg += f"\n📊 *TOPLAM:* {status['toplam_tamamlanan']}/{status['toplam_hedef']}"
    
    bot.reply_to(message, msg, parse_mode='Markdown')
    bot_state.remove_active_job(user_id)
    bot_state.clear_state(user_id)
    debug_log(f"User {user_id}: /stop komutu", "TELEGRAM")

@bot.message_handler(commands=['vds_test'])
def vds_test_command(message):
    """VDS bağlantı testi"""
    vds_client = VDSClient()
    
    if vds_client.check_status():
        bot.reply_to(
            message,
            f"✅ *VDS BAĞLANTI TESTİ*\n\n"
            f"📍 Server: {CONFIG.VDS_SERVER_URL}\n"
            f"📡 Durum: Bağlantı başarılı\n"
            f"🔧 Mod: Aktif",
            parse_mode='Markdown'
        )
    else:
        bot.reply_to(
            message,
            f"❌ *VDS BAĞLANTI TESTİ*\n\n"
            f"📍 Server: {CONFIG.VDS_SERVER_URL}\n"
            f"📡 Durum: Bağlantı başarısız\n"
            f"🔧 Mod: Pasif",
            parse_mode='Markdown'
        )

@bot.message_handler(commands=['yardim', 'help'])
def help_command(message):
    msg = "🤖 *ETI MUTLU KUTU BOT (VDS MOD)*\n\n"
    msg += "📋 *Ana Komutlar:*\n"
    msg += "• /start - Yeni işlem başlat\n"
    msg += "• /bilgi - Mevcut durumu gör\n"
    msg += "• /stop - İşlemi durdur\n"
    msg += "• /vds_test - VDS bağlantı testi\n\n"
    
    msg += "📝 *Kullanım:*\n"
    msg += "1. /start yaz\n"
    msg += f"2. Davet kodlarını gir (max {CONFIG.MAX_CODES})\n"
    msg += "3. Her kod için adet belirle (1-500)\n"
    msg += "4. İşlem otomatik başlar\n\n"
    
    msg += "⚙️ *Ayarlar:*\n"
    msg += f"• Max kod: {CONFIG.MAX_CODES}\n"
    msg += f"• VDS worker: {CONFIG.MAX_VDS_WORKERS}\n"
    msg += f"• SMS timeout: {CONFIG.SMS_TIMEOUT}s\n"
    msg += f"• VDS URL: {CONFIG.VDS_SERVER_URL}"
    
    bot.reply_to(message, msg, parse_mode='Markdown')

@bot.message_handler(func=lambda message: True)
def default_handler(message):
    bot.reply_to(message, "❓ *Bilinmeyen komut!*\n\n/yardim yazarak kullanımı öğrenebilirsin.", parse_mode='Markdown')

# ═══════════════════════════════════════════════════════════
# WEBHOOK ve HEALTH CHECK
# ═══════════════════════════════════════════════════════════

from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/')
def health_check():
    vds_client = VDSClient()
    vds_status = vds_client.check_status()
    
    return jsonify({
        'status': 'online',
        'bot': 'running',
        'vds_connection': vds_status,
        'vds_url': CONFIG.VDS_SERVER_URL,
        'debug_mode': CONFIG.DEBUG_MODE,
        'timestamp': datetime.now().isoformat()
    })

@app.route('/webhook', methods=['POST'])
def webhook():
    """Telegram webhook endpoint"""
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return ''
    return 'Bad request', 400

def set_webhook():
    """Webhook'u ayarla"""
    if CONFIG.RAILWAY_PUBLIC_DOMAIN:
        webhook_url = f"https://{CONFIG.RAILWAY_PUBLIC_DOMAIN}/webhook"
        bot.remove_webhook()
        time.sleep(1)
        bot.set_webhook(url=webhook_url)
        debug_log(f"Webhook set to: {webhook_url}", "WEBHOOK")
        return True
    return False

def run_polling():
    """Long polling başlat"""
    debug_log("Long polling başlatılıyor...", "BOT")
    bot.polling(none_stop=True, timeout=30, long_polling_timeout=30)

# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════

def main():
    print("="*70)
    print("🤖 ETI MUTLU KUTU - VDS TELEGRAM BOT v2.0 (Railway)")
    print("="*70)
    print(f"📱 Token: {CONFIG.BOT_TOKEN[:10]}...")
    print(f"🔧 Mod: ⚡ VDS MOD")
    print(f"📍 VDS URL: {CONFIG.VDS_SERVER_URL}")
    print(f"⚙️ SMS Timeout: {CONFIG.SMS_TIMEOUT}s")
    print(f"⚙️ Max VDS Workers: {CONFIG.MAX_VDS_WORKERS}")
    print(f"⚙️ Max Kod: {CONFIG.MAX_CODES}")
    print(f"🐞 Debug Mode: {CONFIG.DEBUG_MODE}")
    print(f"🌐 Webhook: {CONFIG.USE_WEBHOOK}")
    
    if CONFIG.RAILWAY_PUBLIC_DOMAIN:
        print(f"🌐 Public Domain: {CONFIG.RAILWAY_PUBLIC_DOMAIN}")
    print("="*70)
    
    # VDS kontrolü
    vds_client = VDSClient()
    if vds_client.check_status():
        print("✅ VDS Server: Bağlantı başarılı")
    else:
        print("⚠️  VDS Server: Bağlantı başarısız!")
        print("⚠️  Bot çalışacak ancak VDS erişimi olmayacak")
    
    # Token kontrolü
    if "AAFtGjtxYv0dqQAGnziaBnaf-GrrI0sPzdk" in CONFIG.BOT_TOKEN:
        print("⚠️  UYARI: Örnek bot token'ı kullanılıyor olabilir!")
        print("⚠️  Lütfen Railway Variables'da BOT_TOKEN ayarlayın!")
    
    print("\n🚀 Bot başlatılıyor...")
    print("📞 Komutlar: /start, /bilgi, /stop, /vds_test, /yardim")
    print("="*70)
    
    # Signal handler
    def signal_handler(sig, frame):
        print("\n\n🛑 Bot durduruluyor...")
        # Aktif tüm job'ları durdur
        for user_id in list(bot_state.active_jobs.keys()):
            job = bot_state.get_active_job(user_id)
            if job:
                job.stop()
        
        # Webhook'u kaldır
        if CONFIG.USE_WEBHOOK:
            bot.remove_webhook()
        
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        if CONFIG.USE_WEBHOOK and CONFIG.RAILWAY_PUBLIC_DOMAIN:
            # Webhook modu
            debug_log("Webhook modu başlatılıyor...", "SYSTEM")
            set_webhook()
            
            # Flask server'ı başlat
            debug_log(f"Flask server başlatılıyor (PORT: {CONFIG.WEBHOOK_PORT})", "SYSTEM")
            app.run(host='0.0.0.0', port=CONFIG.WEBHOOK_PORT)
        else:
            # Long polling modu (single instance için)
            debug_log("Long polling modu başlatılıyor...", "SYSTEM")
            
            # Önce webhook var mı kontrol et ve kaldır
            bot.remove_webhook()
            time.sleep(2)
            
            # Health check için basit thread
            def simple_health_check():
                from flask import Flask
                health_app = Flask(__name__)
                
                @health_app.route('/')
                def health():
                    return jsonify({"status": "ok", "bot": "running"})
                
                health_app.run(host='0.0.0.0', port=CONFIG.WEBHOOK_PORT)
            
            # Health check thread'i başlat
            health_thread = threading.Thread(target=simple_health_check, daemon=True)
            health_thread.start()
            
            # Polling başlat
            run_polling()
            
    except Exception as e:
        print(f"❌ Bot hatası: {e}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        sys.exit(1)

if __name__ == "__main__":
    # Gerekli paketleri kontrol et
    try:
        import requests
    except ImportError:
        print("❌ 'requests' paketi kurulu değil!")
        print("📦 Kurulum: pip install requests")
        sys.exit(1)
    
    try:
        from flask import Flask, request, jsonify
    except ImportError:
        print("❌ 'flask' paketi kurulu değil!")
        print("📦 Kurulum: pip install flask")
        sys.exit(1)
    
    main()
