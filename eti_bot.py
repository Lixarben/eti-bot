#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETI MUTLU KUTU - PYTHONANYWHERE VERSION v3.0
- PythonAnywhere uyumlu (Selenium yok, sadece VDS kontrolü)
- VDS: 194.62.55.201:8080 
- Always-on task desteği
- Web panel + Telegram bot
"""

import threading
import time
import json
import sys
import os
import logging
from datetime import datetime
from typing import Optional, Dict, List
from dataclasses import dataclass, asdict
from queue import Queue
import json
import re

# PythonAnywhere'de kurulu gelen paketler
try:
    import requests
except ImportError:
    print("❌ requests paketi gerekli: pip install --user requests")
    sys.exit(1)

# Flask web framework (PythonAnywhere'de mevcut)
try:
    from flask import Flask, render_template_string, request, jsonify
    from flask_socketio import SocketIO, emit
except ImportError:
    print("❌ Flask kurulu değil")
    Flask = None

# Telegram bot (kurman gerekecek)
try:
    import telebot
    from telebot import types
except ImportError:
    print("⚠️  telebot kurulu değil: pip install --user pyTelegramBotAPI")
    telebot = None

# ═══════════════════════════════════════════════════════════
# KONFİGÜRASYON
# ═══════════════════════════════════════════════════════════

@dataclass
class Config:
    # Telegram Bot - KENDİ TOKEN'INI EKLE!
    BOT_TOKEN: str = "8182630877:AAFtGjtxYv0dqQAGnziaBnaf-GrrI0sPzdk"
    
    # VDS Ayarları
    VDS_URL = "http://194.62.55.201:8080"
    MAX_VDS_WORKERS: int = 4
    
    # API Bilgileri (VDS üzerinden çalışacak)
    # Bu bilgiler sadece log için, asıl iş VDS'de
    API_NAME: str = "SeoClas"
    API_KEY: str = "WTBLWC9yUHFtcjlmMXhBRXVaVjFUZz09"
    BASE_URL: str = "https://api.durianrcs.com/out/ext_api"
    PID: str = "6354"
    
    # Zaman Ayarları
    SMS_TIMEOUT: float = 25.0
    REQUEST_TIMEOUT: int = 60  # VDS istekleri için uzun timeout
    
    # PythonAnywhere Özel
    PYTHONANYWHERE: bool = True  # True: PA modu, False: Normal
    ALWAYS_ON_TASK: bool = True  # PythonAnywhere always-on task kullan
    
    # Debug
    DEBUG_MODE: bool = True
    LOG_FILE: str = "/tmp/eti_bot.log"  # PythonAnywhere path'i güncelle!

CONFIG = Config()

# ═══════════════════════════════════════════════════════════
# LOGGER SETUP (PythonAnywhere için dosya logu)
# ═══════════════════════════════════════════════════════════

def setup_logging():
    """PythonAnywhere için dosya logu ayarla"""
    log_format = '%(asctime)s | %(levelname)s | %(message)s'
    logging.basicConfig(
        level=logging.INFO if CONFIG.DEBUG_MODE else logging.WARNING,
        format=log_format,
        handlers=[
            logging.FileHandler(CONFIG.LOG_FILE),
            logging.StreamHandler(sys.stdout)
        ]
    )
    return logging.getLogger(__name__)

logger = setup_logging()

def debug_log(msg: str, level: str = "INFO"):
    """Log yaz"""
    if level == "ERROR":
        logger.error(msg)
    elif level == "WARNING":
        logger.warning(msg)
    else:
        logger.info(msg)

# ═══════════════════════════════════════════════════════════
# VDS CLIENT - PythonAnywhere'den VDS'ye bağlantı
# ═══════════════════════════════════════════════════════════

class VDSClient:
    def __init__(self):
        self.base_url = CONFIG.VDS_SERVER_URL
        self.timeout = CONFIG.REQUEST_TIMEOUT
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'PythonAnywhere-ETI-Bot/3.0',
            'Content-Type': 'application/json'
        })
    
    def check_status(self) -> bool:
        """VDS server çalışıyor mu kontrol et"""
        try:
            response = self.session.get(
                f"{self.base_url}/health", 
                timeout=10
            )
            return response.status_code == 200
        except Exception as e:
            debug_log(f"VDS health check hatası: {e}", "ERROR")
            return False
    
    def get_status(self) -> dict:
        """VDS server durumunu al"""
        try:
            response = self.session.get(
                f"{self.base_url}/status",
                timeout=10
            )
            return response.json()
        except Exception as e:
            debug_log(f"VDS status hatası: {e}", "ERROR")
            return {"error": str(e), "online": False}
    
    def kayit_yap(self, davet_kodu: str, worker_id: int = 1) -> dict:
        """Tek bir kayıt için VDS'ye istek gönder"""
        try:
            url = f"{self.base_url}/kayit"
            data = {
                "davet_kodu": davet_kodu,
                "worker_id": worker_id,
                "api_name": CONFIG.API_NAME,
                "api_key": CONFIG.API_KEY,
                "pid": CONFIG.PID
            }
            
            debug_log(f"VDS'ye kayıt isteği: {davet_kodu} (Worker {worker_id})")
            
            response = self.session.post(
                url, 
                json=data, 
                timeout=self.timeout
            )
            result = response.json()
            
            success = result.get('success', False)
            debug_log(f"VDS cevabı: {'✅' if success else '❌'} {result.get('message', '')}")
            return result
            
        except requests.exceptions.ConnectionError:
            error_msg = "VDS server'a bağlanılamadı! IP: 194.62.55.201:8080"
            debug_log(error_msg, "ERROR")
            return {"success": False, "error": error_msg}
        except requests.exceptions.Timeout:
            error_msg = f"VDS timeout ({self.timeout}s)"
            debug_log(error_msg, "ERROR")
            return {"success": False, "error": error_msg}
        except Exception as e:
            debug_log(f"VDS hatası: {str(e)}", "ERROR")
            return {"success": False, "error": str(e)}
    
    def batch_kayit(self, kodlar: List[str], hedefler: List[int]) -> dict:
        """Toplu kayıt başlat (VDS'de paralel işlem)"""
        try:
            url = f"{self.base_url}/batch_kayit"
            data = {
                "kodlar": kodlar,
                "hedefler": hedefler,
                "max_workers": CONFIG.MAX_VDS_WORKERS,
                "api_name": CONFIG.API_NAME,
                "api_key": CONFIG.API_KEY,
                "pid": CONFIG.PID
            }
            
            debug_log(f"Batch kayıt isteği: {kodlar} -> {hedefler}")
            
            response = self.session.post(
                url,
                json=data,
                timeout=5  # Hemen cevap döner, işlem arka planda
            )
            return response.json()
            
        except Exception as e:
            debug_log(f"Batch kayıt hatası: {e}", "ERROR")
            return {"success": False, "error": str(e)}
    
    def get_progress(self, job_id: str) -> dict:
        """İşlem ilerlemesini al"""
        try:
            response = self.session.get(
                f"{self.base_url}/progress/{job_id}",
                timeout=10
            )
            return response.json()
        except Exception as e:
            return {"error": str(e)}

# ═══════════════════════════════════════════════════════════
# JOB YÖNETİMİ - PythonAnywhere tarafında
# ═══════════════════════════════════════════════════════════

class JobManager:
    def __init__(self):
        self.active_jobs = {}
        self.job_history = []
        self.lock = threading.Lock()
        self.vds_client = VDSClient()
    
    def create_job(self, user_id: int, kodlar: List[str], hedefler: List[int]) -> str:
        """Yeni işlem oluştur"""
        job_id = f"job_{user_id}_{int(time.time())}"
        
        job_data = {
            'id': job_id,
            'user_id': user_id,
            'kodlar': kodlar,
            'hedefler': hedefler,
            'created_at': datetime.now().isoformat(),
            'status': 'pending',
            'progress': {
                'tamamlanan': [0] * len(kodlar),
                'basarisiz': [0] * len(kodlar),
                'toplam_tamamlanan': 0,
                'toplam_hedef': sum(hedefler)
            },
            'logs': []
        }
        
        with self.lock:
            self.active_jobs[job_id] = job_data
        
        debug_log(f"Job oluşturuldu: {job_id}")
        return job_id
    
    def start_job(self, job_id: str):
        """İşlemi VDS'de başlat"""
        with self.lock:
            if job_id not in self.active_jobs:
                return False
            
            job = self.active_jobs[job_id]
            job['status'] = 'running'
        
        # VDS'ye batch istek gönder
        result = self.vds_client.batch_kayit(
            job['kodlar'],
            job['hedefler']
        )
        
        if result.get('success'):
            with self.lock:
                self.active_jobs[job_id]['vds_job_id'] = result.get('job_id')
            debug_log(f"Job VDS'de başlatıldı: {result.get('job_id')}")
            return True
        else:
            with self.lock:
                self.active_jobs[job_id]['status'] = 'error'
                self.active_jobs[job_id]['error'] = result.get('error')
            return False
    
    def update_progress(self, job_id: str):
        """VDS'den ilerleme bilgisini al"""
        with self.lock:
            if job_id not in self.active_jobs:
                return None
            
            job = self.active_jobs[job_id]
            vds_job_id = job.get('vds_job_id')
        
        if not vds_job_id:
            return job
        
        # VDS'den progress al
        progress = self.vds_client.get_progress(vds_job_id)
        
        with self.lock:
            self.active_jobs[job_id]['progress'] = progress
            self.active_jobs[job_id]['last_update'] = datetime.now().isoformat()
            
            # Tamamlandı mı kontrol et
            if progress.get('completed'):
                self.active_jobs[job_id]['status'] = 'completed'
                self.job_history.append(self.active_jobs[job_id])
        
        return self.active_jobs[job_id]
    
    def get_job(self, job_id: str) -> Optional[dict]:
        with self.lock:
            return self.active_jobs.get(job_id)
    
    def get_user_jobs(self, user_id: int) -> List[dict]:
        with self.lock:
            return [
                job for job in self.active_jobs.values() 
                if job['user_id'] == user_id
            ]
    
    def stop_job(self, job_id: str) -> bool:
        """İşlemi durdur"""
        try:
            response = self.vds_client.session.post(
                f"{CONFIG.VDS_SERVER_URL}/stop/{job_id}",
                timeout=10
            )
            
            with self.lock:
                if job_id in self.active_jobs:
                    self.active_jobs[job_id]['status'] = 'stopped'
            
            return response.json().get('success', False)
        except:
            return False

job_manager = JobManager()

# ═══════════════════════════════════════════════════════════
# TELEGRAM BOT - PythonAnywhere Uyumlu
# ═══════════════════════════════════════════════════════════

if telebot:
    bot = telebot.TeleBot(CONFIG.BOT_TOKEN)
    
    # Kullanıcı durumları
    user_states = {}
    user_data = {}
    
    def get_state(user_id: int) -> Optional[str]:
        return user_states.get(user_id)
    
    def set_state(user_id: int, state: str):
        user_states[user_id] = state
    
    def clear_state(user_id: int):
        if user_id in user_states:
            del user_states[user_id]
        if user_id in user_data:
            del user_data[user_id]
    
    def get_data(user_id: int, key: str, default=None):
        return user_data.get(user_id, {}).get(key, default)
    
    def set_data(user_id: int, key: str, value):
        if user_id not in user_data:
            user_data[user_id] = {}
        user_data[user_id][key] = value
    
    @bot.message_handler(commands=['start'])
    def start_command(message):
        user_id = message.from_user.id
        
        # VDS kontrolü
        vds_client = VDSClient()
        if not vds_client.check_status():
            bot.reply_to(
                message,
                "❌ *VDS SERVER ÇALIŞMIYOR!*\n\n"
                "VDS (194.62.55.201:8080) bağlantısı kurulamadı.\n"
                "Lütfen VDS server'ını kontrol et.",
                parse_mode='Markdown'
            )
            return
        
        clear_state(user_id)
        set_state(user_id, 'waiting_for_codes')
        set_data(user_id, 'davet_kodlari', [])
        
        msg = (
            "🤖 *ETI MUTLU KUTU - PYTHONANYWHERE BOT*\n\n"
            "✅ VDS Server bağlantısı aktif!\n"
            "📍 Server: `194.62.55.201:8080`\n\n"
            "📝 *Davet Kodlarını Gir (max 8):*\n\n"
            "• Tek kod:\n`8701545434`\n\n"
            "• Çoklu kod:\n"
            "```\n8701545434\n1234567890\n9876543210\n```"
        )
        
        bot.reply_to(message, msg, parse_mode='Markdown')
        debug_log(f"User {user_id}: /start")
    
    @bot.message_handler(func=lambda msg: get_state(msg.from_user.id) == 'waiting_for_codes')
    def handle_codes(message):
        user_id = message.from_user.id
        text = message.text.strip()
        
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        
        if len(lines) > 8:
            bot.reply_to(message, "❌ *Maksimum 8 kod!*")
            return
        
        if not all(l.isdigit() for l in lines):
            bot.reply_to(message, "❌ *Kodlar sadece rakam olmalı!*")
            return
        
        set_data(user_id, 'davet_kodlari', lines)
        set_state(user_id, 'waiting_for_counts')
        set_data(user_id, 'current_code_index', 0)
        
        first_code = lines[0]
        msg = (
            f"📋 *Kod 1/{len(lines)}*\n\n"
            f"Kod: `{first_code}`\n\n"
            f"Kaç adet istiyorsun? *(1-500)*"
        )
        
        bot.reply_to(message, msg, parse_mode='Markdown')
    
    @bot.message_handler(func=lambda msg: get_state(msg.from_user.id) == 'waiting_for_counts')
    def handle_counts(message):
        user_id = message.from_user.id
        text = message.text.strip()
        
        try:
            count = int(text)
            if not 1 <= count <= 500:
                raise ValueError
        except:
            bot.reply_to(message, "❌ *1-500 arası sayı gir!*")
            return
        
        codes = get_data(user_id, 'davet_kodlari', [])
        current_idx = get_data(user_id, 'current_code_index', 0)
        
        hedefler = get_data(user_id, 'hedefler', [])
        hedefler.append(count)
        set_data(user_id, 'hedefler', hedefler)
        
        current_idx += 1
        
        if current_idx < len(codes):
            set_data(user_id, 'current_code_index', current_idx)
            next_code = codes[current_idx]
            
            msg = (
                f"✅ Kod {current_idx}/{len(codes)}: {count} adet\n\n"
                f"📋 *Kod {current_idx+1}/{len(codes)}*\n"
                f"Kod: `{next_code}`\n\n"
                f"Kaç adet?"
            )
            bot.reply_to(message, msg, parse_mode='Markdown')
        else:
            # Tüm kodlar alındı, işlemi başlat
            set_state(user_id, 'processing')
            
            # Job oluştur
            job_id = job_manager.create_job(user_id, codes, hedefler)
            
            # VDS'de başlat
            if job_manager.start_job(job_id):
                toplam = sum(hedefler)
                msg = (
                    f"⚡ *İŞLEM BAŞLATILDI!*\n\n"
                    f"🆔 Job ID: `{job_id}`\n"
                    f"📊 Toplam: {toplam} kayıt\n"
                    f"👥 Workers: {CONFIG.MAX_VDS_WORKERS}\n\n"
                    f"📈 Durum: /durum\n"
                    f"🛑 Durdur: /durdur\n"
                    f"📋 Tüm işlemlerin: /islerim"
                )
            else:
                msg = "❌ *İşlem başlatılamadı!* VDS hatası."
            
            bot.reply_to(message, msg, parse_mode='Markdown')
            clear_state(user_id)
    
    @bot.message_handler(commands=['durum'])
    def status_command(message):
        user_id = message.from_user.id
        jobs = job_manager.get_user_jobs(user_id)
        
        if not jobs:
            bot.reply_to(message, "📭 *Aktif işlem yok!*")
            return
        
        msg = "📊 *AKTİF İŞLEMLERİN*\n\n"
        
        for job in jobs[-3:]:  # Son 3 işlem
            progress = job['progress']
            status_emoji = {
                'pending': '⏳',
                'running': '▶️',
                'completed': '✅',
                'error': '❌',
                'stopped': '🛑'
            }.get(job['status'], '❓')
            
            msg += f"{status_emoji} `{job['id'][-8:]}`\n"
            msg += f"   Durum: {job['status']}\n"
            msg += f"   İlerleme: {progress.get('toplam_tamamlanan', 0)}/{progress.get('toplam_hedef', 0)}\n\n"
        
        bot.reply_to(message, msg, parse_mode='Markdown')
    
    @bot.message_handler(commands=['islerim'])
    def my_jobs_command(message):
        status_command(message)  # Alias
    
    @bot.message_handler(commands=['durdur'])
    def stop_command(message):
        user_id = message.from_user.id
        jobs = job_manager.get_user_jobs(user_id)
        
        if not jobs:
            bot.reply_to(message, "📭 *Durdurulacak işlem yok!*")
            return
        
        # Son aktif işlemi durdur
        active_jobs = [j for j in jobs if j['status'] == 'running']
        if not active_jobs:
            bot.reply_to(message, "🛑 *Çalışan işlem yok!*")
            return
        
        job = active_jobs[-1]
        if job_manager.stop_job(job['id']):
            bot.reply_to(message, f"✅ *İşlem durduruldu:* `{job['id'][-8:]}`")
        else:
            bot.reply_to(message, "❌ *Durdurma başarısız!*")
    
    @bot.message_handler(commands=['vds'])
    def vds_status_command(message):
        vds_client = VDSClient()
        
        if vds_client.check_status():
            status = vds_client.get_status()
            msg = (
                f"✅ *VDS SERVER AKTİF*\n\n"
                f"📍 IP: `194.62.55.201:8080`\n"
                f"👥 Aktif Worker: {status.get('active_workers', '?')}/{CONFIG.MAX_VDS_WORKERS}\n"
                f"📊 Toplam İşlem: {status.get('total_jobs', '?')}\n"
                f"⚡ Durum: Çevrimiçi"
            )
        else:
            msg = (
                f"❌ *VDS SERVER KAPALI*\n\n"
                f"📍 IP: `194.62.55.201:8080`\n"
                f"⚠️ Bağlantı kurulamadı!"
            )
        
        bot.reply_to(message, msg, parse_mode='Markdown')
    
    @bot.message_handler(commands=['yardim'])
    def help_command(message):
        msg = (
            "🤖 *ETI MUTLU KUTU - KOMUTLAR*\n\n"
            "📋 *Ana Komutlar:*\n"
            "• /start - Yeni işlem başlat\n"
            "• /durum - Aktif işlemleri gör\n"
            "• /islerim - Tüm işlemlerin\n"
            "• /durdur - Son işlemi durdur\n"
            "• /vds - VDS durumunu kontrol et\n\n"
            "⚙️ *Bilgi:*\n"
            "• Bot PythonAnywhere'de çalışıyor\n"
            "• İşlemler VDS (194.62.55.201) üzerinde yapılıyor\n"
            "• Max 8 kod, her biri için max 500 adet"
        )
        bot.reply_to(message, msg, parse_mode='Markdown')

# ═══════════════════════════════════════════════════════════
# WEB PANEL - Flask (PythonAnywhere Web App)
# ═══════════════════════════════════════════════════════════

if Flask:
    app = Flask(__name__)
    
    HTML_TEMPLATE = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>ETI Bot - PythonAnywhere Panel</title>
        <meta charset="utf-8">
        <style>
            body { font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }
            .header { background: #2c3e50; color: white; padding: 20px; border-radius: 8px; margin-bottom: 20px; }
            .status-box { background: #ecf0f1; padding: 15px; border-radius: 8px; margin-bottom: 20px; }
            .job-card { background: #fff; border: 1px solid #ddd; padding: 15px; margin-bottom: 10px; border-radius: 5px; }
            .online { color: #27ae60; font-weight: bold; }
            .offline { color: #e74c3c; font-weight: bold; }
            button { background: #3498db; color: white; border: none; padding: 10px 20px; border-radius: 5px; cursor: pointer; }
            button:hover { background: #2980b9; }
            pre { background: #2c3e50; color: #2ecc71; padding: 15px; overflow-x: auto; border-radius: 5px; }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>🤖 ETI MUTLU KUTU</h1>
            <p>PythonAnywhere Hybrid Bot Panel</p>
        </div>
        
        <div class="status-box">
            <h3>🌐 VDS Server Durumu</h3>
            <p>IP: <code>194.62.55.201:8080</code></p>
            <p>Durum: <span class="{{ 'online' if vds_online else 'offline' }}">
                {{ '✅ Çevrimiçi' if vds_online else '❌ Çevrimdışı' }}
            </span></p>
            {% if vds_status %}
                <p>Aktif Worker: {{ vds_status.get('active_workers', 0) }}/4</p>
                <p>Toplam İşlem: {{ vds_status.get('total_jobs', 0) }}</p>
            {% endif %}
        </div>
        
        <div class="status-box">
            <h3>📊 Aktif İşlemler</h3>
            {% if jobs %}
                {% for job in jobs %}
                <div class="job-card">
                    <strong>ID:</strong> {{ job.id }}<br>
                    <strong>Kullanıcı:</strong> {{ job.user_id }}<br>
                    <strong>Kodlar:</strong> {{ ', '.join(job.kodlar) }}<br>
                    <strong>Hedefler:</strong> {{ ', '.join(job.hedefler|map('string')) }}<br>
                    <strong>Durum:</strong> {{ job.status }}<br>
                    <strong>İlerleme:</strong> 
                    {{ job.progress.toplam_tamamlanan }}/{{ job.progress.toplam_hedef }}
                </div>
                {% endfor %}
            {% else %}
                <p>📭 Aktif işlem yok</p>
            {% endif %}
        </div>
        
        <div class="status-box">
            <h3>📝 Loglar (Son 20)</h3>
            <pre>{{ logs }}</pre>
        </div>
        
        <form action="/refresh" method="post">
            <button type="submit">🔄 Yenile</button>
        </form>
    </body>
    </html>
    """
    
    @app.route('/')
    def index():
        vds_client = VDSClient()
        vds_online = vds_client.check_status()
        vds_status = vds_client.get_status() if vds_online else None
        
        # Son logları oku
        logs = "Log dosyası bulunamadı"
        try:
            if os.path.exists(CONFIG.LOG_FILE):
                with open(CONFIG.LOG_FILE, 'r') as f:
                    lines = f.readlines()
                    logs = ''.join(lines[-20:])
        except:
            pass
        
        jobs = list(job_manager.active_jobs.values())
        
        return render_template_string(
            HTML_TEMPLATE,
            vds_online=vds_online,
            vds_status=vds_status,
            jobs=jobs,
            logs=logs
        )
    
    @app.route('/refresh', methods=['POST'])
    def refresh():
        return index()
    
    @app.route('/api/status')
    def api_status():
        vds_client = VDSClient()
        return jsonify({
            'vds_online': vds_client.check_status(),
            'vds_status': vds_client.get_status(),
            'active_jobs': len(job_manager.active_jobs),
            'pythonanywhere': True
        })
    
    @app.route('/api/jobs')
    def api_jobs():
        return jsonify({
            'jobs': list(job_manager.active_jobs.values())
        })

# ═══════════════════════════════════════════════════════════
# BACKGROUND TASK - PythonAnywhere Always-on Task
# ═══════════════════════════════════════════════════════════

def background_task():
    """Arka planda çalışan görev - PythonAnywhere Always-on task için"""
    debug_log("Background task başlatıldı")
    
    vds_client = VDSClient()
    
    while True:
        try:
            # Aktif job'ları güncelle
            for job_id in list(job_manager.active_jobs.keys()):
                job = job_manager.active_jobs.get(job_id)
                if job and job.get('status') == 'running':
                    job_manager.update_progress(job_id)
                    debug_log(f"Job güncellendi: {job_id}")
            
            # Her 10 saniyede bir kontrol
            time.sleep(10)
            
        except Exception as e:
            debug_log(f"Background task hatası: {e}", "ERROR")
            time.sleep(30)

# ═══════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════

def main():
    print("="*70)
    print("🤖 ETI MUTLU KUTU - PYTHONANYWHERE v3.0")
    print("="*70)
    print(f"📍 VDS Server: {CONFIG.VDS_SERVER_URL}")
    print(f"👥 Max Workers: {CONFIG.MAX_VDS_WORKERS}")
    print(f"🐍 PythonAnywhere Modu: {'Aktif' if CONFIG.PYTHONANYWHERE else 'Pasif'}")
    print("="*70)
    
    # VDS kontrolü
    vds_client = VDSClient()
    if vds_client.check_status():
        print("✅ VDS Server: Bağlantı başarılı")
        status = vds_client.get_status()
        print(f"   Workers: {status.get('active_workers', '?')}/4")
    else:
        print("❌ VDS Server: Bağlantı başarısız!")
        print("   194.62.55.201:8080 kontrol et")
    
    # Telegram bot kontrolü
    if telebot and CONFIG.BOT_TOKEN:
        print("✅ Telegram Bot: Hazır")
        
        # Bot polling'i ayrı thread'de başlat
        def run_bot():
            try:
                bot.polling(none_stop=True, interval=0)
            except Exception as e:
                debug_log(f"Bot hatası: {e}", "ERROR")
        
        bot_thread = threading.Thread(target=run_bot, daemon=True)
        bot_thread.start()
        print("🤖 Bot polling başlatıldı")
    else:
        print("⚠️  Telegram Bot: Devre dışı (token kontrol et)")
    
    # Flask web app (eğer WSGI olarak çalışmıyorsa)
    if Flask and __name__ == '__main__':
        print("🌐 Web Panel: http://localhost:5000")
        # Background task başlat
        bg_thread = threading.Thread(target=background_task, daemon=True)
        bg_thread.start()
        
        # Flask çalıştır (sadece local test için)
        # PythonAnywhere'de bu kısım WSGI ile değiştirilir
        app.run(host='0.0.0.0', port=5000, debug=False)
    
    print("="*70)
    print("✅ Sistem hazır!")
    print("📞 Telegram: /start")
    print("🌐 Web: /")
    print("="*70)

# PythonAnywhere WSGI için
if Flask and __name__ != '__main__':
    # Always-on task başlat
    bg_thread = threading.Thread(target=background_task, daemon=True)
    bg_thread.start()
    
    # Flask app WSGI için hazır
    application = app

if __name__ == '__main__':

    main()

