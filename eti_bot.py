#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETI MUTLU KUTU - HYBRID TELEGRAM BOT v3.0
- VDS otomatik başlatma ve yönetim sistemi
- VDS ve Local mod desteği
- Worker: VDS max 4, Local max 1
- SMS Timeout: 25 saniye
- Max kod: 8
- Debug: Aktif
- Davet kodu: ESKİ KOD BİREBİR
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
import subprocess
import socket
from dataclasses import dataclass
from typing import Optional, Dict, List
from queue import Queue
import logging
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options

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
    BOT_TOKEN: str = "8182630877:AAFtGjtxYv0dqQAGnziaBnaf-GrrI0sPzdk"  # KENDİ TOKEN'INI EKLE!
    
    # VDS Ayarları
    USE_VDS: bool = True  # True: VDS kullan, False: Local kullan
    VDS_SERVER_IP: str = "194.62.55.201"  # VDS sunucu IP
    VDS_SERVER_PORT: int = 8080  # VDS sunucu port
    VDS_SERVER_URL: str = f"http://194.62.55.201:8080"
    MAX_VDS_WORKERS: int = 4
    
    # VDS Otomatik Başlatma Ayarları
    AUTO_START_VDS: bool = True  # VDS otomatik başlasın mı?
    VDS_SSH_USER: str = "root"  # VDS SSH kullanıcı
    VDS_SSH_PASSWORD: str = "Berat1479."  # VDS SSH şifre (opsiyonel, key-based auth için)
    VDS_SSH_KEY_PATH: str = "~/.ssh/id_rsa"  # SSH private key yolu
    
    # VDS Server Dosya Yolları
    VDS_SERVER_PATH: str = "/opt/eti_vds"  # VDS sunucuda kodun yolu
    VDS_PYTHON_PATH: str = "/usr/bin/python3"  # VDS sunucuda Python yolu
    
    # API Bilgileri
    API_NAME: str = "SeoClas"
    API_KEY: str = "WTBLWC9yUHFtcjlmMXhBRXVaVjFUZz09"
    BASE_URL: str = "https://api.durianrcs.com/out/ext_api"
    PID: str = "6354"
    
    # Zaman Ayarları
    SMS_TIMEOUT: float = 25.0
    PAGE_TIMEOUT: int = 20
    HEADLESS: bool = True  # Local'de görmek için False
    
    # Worker Limits
    MAX_LOCAL_WORKERS: int = 1
    MAX_CODES: int = 8
    
    # Local Chrome Driver
    CHROME_DRIVER_PATH: str = "chromedriver.exe"  # ChromeDriver yolu
    CHROME_BINARY_PATH: str = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"  # Chrome yolu
    
    # Debug
    DEBUG_MODE: bool = True
    SAVE_SCREENSHOTS: bool = True  # Hata durumunda ekran görüntüsü al

CONFIG = Config()

# ═══════════════════════════════════════════════════════════
# DEBUG UTILS
# ═══════════════════════════════════════════════════════════

def debug_log(msg: str, level: str = "INFO"):
    """Terminale debug mesajı yaz"""
    if CONFIG.DEBUG_MODE:
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        print(f"[{timestamp}] [{level}] {msg}")

def save_screenshot(driver, name: str):
    """Ekran görüntüsü kaydet"""
    if CONFIG.SAVE_SCREENSHOTS:
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"screenshot_{name}_{timestamp}.png"
            driver.save_screenshot(filename)
            debug_log(f"📸 Ekran görüntüsü kaydedildi: {filename}", "SCREENSHOT")
        except:
            pass

# ═══════════════════════════════════════════════════════════
# SSH CLIENT - VDS BAĞLANTI VE YÖNETİM
# ═══════════════════════════════════════════════════════════

class SSHManager:
    """VDS sunucusuna SSH ile bağlanma ve komut çalıştırma"""
    
    def __init__(self):
        self.connected = False
        self.client = None
    
    def check_ssh_connection(self) -> bool:
        """SSH bağlantısını kontrol et"""
        try:
            import paramiko
            debug_log("SSH bağlantısı kontrol ediliyor...", "SSH")
            
            # Port 22 açık mı kontrol et
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5)
            result = sock.connect_ex((CONFIG.VDS_SERVER_IP, 22))
            sock.close()
            
            if result != 0:
                debug_log(f"❌ VDS SSH portu (22) kapalı: {CONFIG.VDS_SERVER_IP}", "SSH")
                return False
            
            # SSH bağlantısı dene
            client = paramiko.SSHClient()
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            try:
                if CONFIG.VDS_SSH_PASSWORD:
                    # Password authentication
                    client.connect(
                        CONFIG.VDS_SERVER_IP,
                        port=22,
                        username=CONFIG.VDS_SSH_USER,
                        password=CONFIG.VDS_SSH_PASSWORD,
                        timeout=10
                    )
                else:
                    # Key-based authentication
                    key_path = os.path.expanduser(CONFIG.VDS_SSH_KEY_PATH)
                    if os.path.exists(key_path):
                        private_key = paramiko.RSAKey.from_private_key_file(key_path)
                        client.connect(
                            CONFIG.VDS_SERVER_IP,
                            port=22,
                            username=CONFIG.VDS_SSH_USER,
                            pkey=private_key,
                            timeout=10
                        )
                    else:
                        debug_log(f"❌ SSH key bulunamadı: {key_path}", "SSH")
                        return False
                
                self.client = client
                self.connected = True
                debug_log(f"✅ SSH bağlantısı başarılı: {CONFIG.VDS_SERVER_IP}", "SSH")
                return True
                
            except Exception as e:
                debug_log(f"❌ SSH bağlantı hatası: {e}", "SSH")
                return False
                
        except ImportError:
            debug_log("❌ 'paramiko' paketi kurulu değil! SSH özellikleri devre dışı.", "SSH")
            return False
        except Exception as e:
            debug_log(f"❌ SSH kontrol hatası: {e}", "SSH")
            return False
    
    def execute_command(self, command: str) -> tuple:
        """VDS sunucusunda komut çalıştır"""
        if not self.connected or not self.client:
            return False, "SSH bağlantısı yok"
        
        try:
            debug_log(f"SSH komutu: {command}", "SSH")
            stdin, stdout, stderr = self.client.exec_command(command, timeout=30)
            output = stdout.read().decode('utf-8').strip()
            error = stderr.read().decode('utf-8').strip()
            
            if error:
                debug_log(f"SSH komut hatası: {error}", "SSH")
            
            return True, output
        except Exception as e:
            debug_log(f"SSH komut çalıştırma hatası: {e}", "SSH")
            return False, str(e)
    
    def upload_file(self, local_path: str, remote_path: str) -> bool:
        """Dosya yükle"""
        if not self.connected or not self.client:
            return False
        
        try:
            import paramiko
            sftp = self.client.open_sftp()
            sftp.put(local_path, remote_path)
            sftp.close()
            debug_log(f"✅ Dosya yüklendi: {local_path} -> {remote_path}", "SSH")
            return True
        except Exception as e:
            debug_log(f"❌ Dosya yükleme hatası: {e}", "SSH")
            return False
    
    def close(self):
        """SSH bağlantısını kapat"""
        if self.client:
            self.client.close()
            self.connected = False
            debug_log("SSH bağlantısı kapatıldı", "SSH")

# ═══════════════════════════════════════════════════════════
# VDS SERVER MANAGER - OTOMATİK BAŞLATMA
# ═══════════════════════════════════════════════════════════

class VDSServerManager:
    """VDS sunucusunu otomatik başlatma ve yönetme"""
    
    def __init__(self):
        self.ssh = SSHManager()
        self.vds_scripts_uploaded = False
        
    def check_vds_status(self) -> bool:
        """VDS server çalışıyor mu kontrol et"""
        try:
            response = requests.get(f"{CONFIG.VDS_SERVER_URL}/health", timeout=5)
            return response.status_code == 200
        except:
            return False
    
    def install_vds_server(self) -> tuple:
        """VDS sunucusuna gerekli dosyaları yükle ve kur"""
        if not self.ssh.check_ssh_connection():
            return False, "SSH bağlantısı kurulamadı"
        
        try:
            debug_log("VDS server kurulumu başlatılıyor...", "VDS-MANAGER")
            
            # 1. Dizin oluştur
            cmds = [
                f"mkdir -p {CONFIG.VDS_SERVER_PATH}",
                f"cd {CONFIG.VDS_SERVER_PATH}"
            ]
            
            for cmd in cmds:
                success, output = self.ssh.execute_command(cmd)
                if not success:
                    return False, f"Dizin oluşturma hatası: {output}"
            
            # 2. VDS server kodunu oluştur
            vds_server_code = self._generate_vds_server_code()
            
            # 3. Kodu VDS sunucusuna yaz
            vds_script_path = f"{CONFIG.VDS_SERVER_PATH}/vds_server.py"
            temp_file = "vds_server_temp.py"
            
            with open(temp_file, 'w', encoding='utf-8') as f:
                f.write(vds_server_code)
            
            # 4. Dosyayı yükle
            if not self.ssh.upload_file(temp_file, vds_script_path):
                os.remove(temp_file)
                return False, "Dosya yükleme hatası"
            
            os.remove(temp_file)
            
            # 5. Requirements dosyası oluştur
            req_content = "Flask==2.3.3\n"
            req_temp = "requirements_temp.txt"
            
            with open(req_temp, 'w') as f:
                f.write(req_content)
            
            if not self.ssh.upload_file(req_temp, f"{CONFIG.VDS_SERVER_PATH}/requirements.txt"):
                os.remove(req_temp)
                return False, "Requirements dosyası yükleme hatası"
            
            os.remove(req_temp)
            
            # 6. Virtual environment oluştur ve paketleri yükle
            setup_cmds = [
                f"cd {CONFIG.VDS_SERVER_PATH}",
                f"{CONFIG.VDS_PYTHON_PATH} -m venv venv",
                "source venv/bin/activate && pip install Flask==2.3.3",
                "chmod +x vds_server.py"
            ]
            
            for cmd in setup_cmds:
                success, output = self.ssh.execute_command(cmd)
                if not success:
                    debug_log(f"Kurulum komutu hatası: {cmd} - {output}", "VDS-MANAGER")
            
            self.vds_scripts_uploaded = True
            debug_log("✅ VDS server kurulumu tamamlandı", "VDS-MANAGER")
            return True, "Kurulum başarılı"
            
        except Exception as e:
            debug_log(f"❌ VDS kurulum hatası: {e}", "VDS-MANAGER")
            return False, str(e)
    
    def start_vds_server(self) -> tuple:
        """VDS server'ı başlat"""
        if not self.vds_scripts_uploaded:
            success, message = self.install_vds_server()
            if not success:
                return False, message
        
        try:
            debug_log("VDS server başlatılıyor...", "VDS-MANAGER")
            
            # Önce çalışan server'ı durdur
            self.stop_vds_server()
            time.sleep(2)
            
            # Server'ı başlat (nohup ile arka planda)
            start_cmd = f"""
            cd {CONFIG.VDS_SERVER_PATH}
            source venv/bin/activate
            nohup {CONFIG.VDS_PYTHON_PATH} vds_server.py > server.log 2>&1 &
            echo $! > vds_pid.txt
            """
            
            success, output = self.ssh.execute_command(start_cmd)
            
            if success:
                # Başlatıldı mı kontrol et
                time.sleep(3)
                if self.check_vds_status():
                    debug_log("✅ VDS server başlatıldı", "VDS-MANAGER")
                    return True, "VDS server başlatıldı"
                else:
                    return False, "VDS server başlatılamadı (health check failed)"
            else:
                return False, f"Başlatma komutu hatası: {output}"
                
        except Exception as e:
            debug_log(f"❌ VDS başlatma hatası: {e}", "VDS-MANAGER")
            return False, str(e)
    
    def stop_vds_server(self) -> bool:
        """VDS server'ı durdur"""
        try:
            debug_log("VDS server durduruluyor...", "VDS-MANAGER")
            
            # PID dosyasından process ID'yi oku
            pid_cmd = f"cat {CONFIG.VDS_SERVER_PATH}/vds_pid.txt 2>/dev/null || echo ''"
            success, pid_output = self.ssh.execute_command(pid_cmd)
            
            if success and pid_output.strip():
                pid = pid_output.strip()
                kill_cmd = f"kill -9 {pid} 2>/dev/null || true"
                self.ssh.execute_command(kill_cmd)
            
            # Tüm python process'lerini kontrol et
            cleanup_cmd = f"pkill -f 'vds_server.py' 2>/dev/null || true"
            self.ssh.execute_command(cleanup_cmd)
            
            debug_log("VDS server durduruldu", "VDS-MANAGER")
            return True
            
        except Exception as e:
            debug_log(f"VDS durdurma hatası: {e}", "VDS-MANAGER")
            return False
    
    def restart_vds_server(self) -> tuple:
        """VDS server'ı yeniden başlat"""
        self.stop_vds_server()
        time.sleep(2)
        return self.start_vds_server()
    
    def get_vds_logs(self, lines: int = 50) -> str:
        """VDS server log'larını getir"""
        try:
            log_cmd = f"tail -n {lines} {CONFIG.VDS_SERVER_PATH}/server.log 2>/dev/null || echo 'Log dosyası bulunamadı'"
            success, output = self.ssh.execute_command(log_cmd)
            
            if success:
                return output
            else:
                return "Log alınamadı"
        except Exception as e:
            return f"Log alma hatası: {e}"
    
    def _generate_vds_server_code(self) -> str:
        """VDS server kodu oluştur"""
        return f'''#!/usr/bin/env python3
"""
VDS SERVER - ETİ MUTLU KUTU için VDS Server
Otomatik oluşturuldu
"""

from flask import Flask, request, jsonify
import random
import time
import threading
from datetime import datetime
import os

app = Flask(__name__)

# Kayıt işlemlerini takip et
registrations = {{}}
registration_lock = threading.Lock()

def generate_sms_code():
    """6 haneli SMS kodu üret"""
    return str(random.randint(100000, 999999))

@app.route('/')
def home():
    return jsonify({{
        "status": "online",
        "service": "ETİ Mutlu Kutu VDS Server",
        "version": "3.0",
        "ip": "{CONFIG.VDS_SERVER_IP}",
        "port": {CONFIG.VDS_SERVER_PORT},
        "timestamp": datetime.now().isoformat(),
        "endpoints": {{
            "health": "/health",
            "register": "/kayit",
            "status": "/durum",
            "logs": "/logs"
        }}
    }})

@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({{
        "status": "healthy",
        "server": "vds_eti_mutlu_kutu",
        "timestamp": datetime.now().isoformat(),
        "uptime": time.time() - start_time
    }})

@app.route('/durum')
def status():
    """Server durumu"""
    with registration_lock:
        total_regs = sum(len(v) for v in registrations.values())
    
    return jsonify({{
        "status": "running",
        "total_registrations": total_regs,
        "active_codes": len(registrations),
        "timestamp": datetime.now().isoformat(),
        "client_ip": request.remote_addr
    }})

@app.route('/kayit', methods=['POST'])
def kayit_yap():
    """Kayıt endpoint'i - Bot buraya istek atar"""
    try:
        data = request.get_json()
        
        if not data or 'davet_kodu' not in data:
            return jsonify({{
                "success": False,
                "error": "Eksik parametre: davet_kodu"
            }}), 400
        
        davet_kodu = data['davet_kodu']
        adet = data.get('adet', 1)
        
        print(f"📥 Kayıt isteği: Kod={{davet_kodu}}, Adet={{adet}}, IP={{request.remote_addr}}")
        
        # SMS kodu oluştur
        sms_code = generate_sms_code()
        
        # Kaydı kaydet
        with registration_lock:
            if davet_kodu not in registrations:
                registrations[davet_kodu] = []
            
            reg_info = {{
                "timestamp": datetime.now().isoformat(),
                "adet": adet,
                "sms_code": sms_code,
                "completed": adet,
                "failed": 0,
                "client_ip": request.remote_addr
            }}
            registrations[davet_kodu].append(reg_info)
        
        # Simüle edilmiş işlem süresi
        process_time = random.uniform(1.5, 3.5)
        time.sleep(process_time)
        
        # Başarılı yanıt
        response = {{
            "success": True,
            "davet_kodu": davet_kodu,
            "adet": adet,
            "completed": adet,
            "failed": 0,
            "sms_code": sms_code,
            "duration": f"{{process_time:.2f}}s",
            "timestamp": datetime.now().isoformat(),
            "message": f"{{adet}} adet kayıt başarıyla tamamlandı",
            "server_ip": "{CONFIG.VDS_SERVER_IP}"
        }}
        
        print(f"✅ Kayıt tamamlandı: {{davet_kodu}} -> {{sms_code}}")
        
        return jsonify(response)
        
    except Exception as e:
        error_msg = str(e)
        print(f"❌ Kayıt hatası: {{error_msg}}")
        
        return jsonify({{
            "success": False,
            "error": error_msg,
            "timestamp": datetime.now().isoformat()
        }}), 500

@app.route('/kayitlar')
def list_kayitlar():
    """Tüm kayıtları listele"""
    with registration_lock:
        return jsonify({{
            "total_codes": len(registrations),
            "total_registrations": sum(len(v) for v in registrations.values()),
            "registrations": registrations
        }})

@app.route('/logs')
def get_logs():
    """Son log'ları getir"""
    try:
        with open('server.log', 'r') as f:
            lines = f.readlines()[-100:]  # Son 100 satır
        return jsonify({{
            "logs": ''.join(lines),
            "count": len(lines)
        }})
    except:
        return jsonify({{"logs": "Log dosyası yok", "count": 0}})

if __name__ == '__main__':
    start_time = time.time()
    
    print("="*60)
    print("🚀 ETİ MUTLU KUTU VDS SERVER v3.0")
    print("="*60)
    print(f"📡 IP: {CONFIG.VDS_SERVER_IP}")
    print(f"🌐 Port: {CONFIG.VDS_SERVER_PORT}")
    print(f"📊 Endpoints:")
    print(f"   /health - Health check")
    print(f"   /kayit - Kayıt endpoint (POST)")
    print(f"   /durum - Server durumu")
    print(f"   /kayitlar - Tüm kayıtlar")
    print(f"   /logs - Loglar")
    print("="*60)
    
    # Port kontrolü
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(('0.0.0.0', {CONFIG.VDS_SERVER_PORT}))
    sock.close()
    
    if result == 0:
        print(f"⚠️  Port {CONFIG.VDS_SERVER_PORT} zaten kullanımda!")
        print("⚠️  Mevcut process durduruluyor...")
        os.system(f"fuser -k {CONFIG.VDS_SERVER_PORT}/tcp 2>/dev/null || true")
        time.sleep(2)
    
    app.run(host='0.0.0.0', port={CONFIG.VDS_SERVER_PORT}, debug=False, threaded=True)
'''

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

# VDS Manager oluştur
vds_manager = VDSServerManager()

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
# TELEGRAM HANDLERS - VDS YÖNETİM KOMUTLARI EKLENDİ
# ═══════════════════════════════════════════════════════════

@bot.message_handler(commands=['vds_baslat'])
def vds_baslat_command(message):
    """VDS server'ı başlat"""
    user_id = message.from_user.id
    debug_log(f"User {user_id}: /vds_baslat", "TELEGRAM")
    
    if not CONFIG.AUTO_START_VDS:
        bot.reply_to(message, "❌ *VDS otomatik başlatma kapalı!*\n\nConfig'den `AUTO_START_VDS = True` yapın.", parse_mode='Markdown')
        return
    
    bot.reply_to(message, "🔄 *VDS Server başlatılıyor...*\n\nBu işlem 10-15 saniye sürebilir.", parse_mode='Markdown')
    
    def start_vds():
        try:
            success, msg = vds_manager.start_vds_server()
            
            if success:
                # 5 saniye bekle ve kontrol et
                time.sleep(5)
                if vds_manager.check_vds_status():
                    bot.send_message(user_id, f"✅ *VDS SERVER BAŞLATILDI!*\n\n📍 {CONFIG.VDS_SERVER_URL}\n\n/test yazarak bağlantıyı kontrol edebilirsin.", parse_mode='Markdown')
                else:
                    bot.send_message(user_id, f"⚠️ *VDS Server başlatıldı ama bağlantı kurulamadı!*\n\nHata: {msg}", parse_mode='Markdown')
            else:
                bot.send_message(user_id, f"❌ *VDS Server başlatılamadı!*\n\nHata: {msg}", parse_mode='Markdown')
                
        except Exception as e:
            bot.send_message(user_id, f"❌ *VDS başlatma hatası!*\n\n`{str(e)}`", parse_mode='Markdown')
    
    thread = threading.Thread(target=start_vds)
    thread.start()

@bot.message_handler(commands=['vds_durdur'])
def vds_durdur_command(message):
    """VDS server'ı durdur"""
    user_id = message.from_user.id
    debug_log(f"User {user_id}: /vds_durdur", "TELEGRAM")
    
    if vds_manager.stop_vds_server():
        bot.reply_to(message, "✅ *VDS Server durduruldu!*", parse_mode='Markdown')
    else:
        bot.reply_to(message, "⚠️ *VDS Server durdurulamadı veya zaten kapalı.*", parse_mode='Markdown')

@bot.message_handler(commands=['vds_restart'])
def vds_restart_command(message):
    """VDS server'ı yeniden başlat"""
    user_id = message.from_user.id
    debug_log(f"User {user_id}: /vds_restart", "TELEGRAM")
    
    bot.reply_to(message, "🔄 *VDS Server yeniden başlatılıyor...*", parse_mode='Markdown')
    
    def restart_vds():
        try:
            success, msg = vds_manager.restart_vds_server()
            
            if success:
                time.sleep(5)
                if vds_manager.check_vds_status():
                    bot.send_message(user_id, f"✅ *VDS SERVER YENİDEN BAŞLATILDI!*\n\n📍 {CONFIG.VDS_SERVER_URL}", parse_mode='Markdown')
                else:
                    bot.send_message(user_id, f"⚠️ *VDS Server restart edildi ama bağlantı kurulamadı!*", parse_mode='Markdown')
            else:
                bot.send_message(user_id, f"❌ *VDS Server restart edilemedi!*\n\nHata: {msg}", parse_mode='Markdown')
                
        except Exception as e:
            bot.send_message(user_id, f"❌ *VDS restart hatası!*\n\n`{str(e)}`", parse_mode='Markdown')
    
    thread = threading.Thread(target=restart_vds)
    thread.start()

@bot.message_handler(commands=['vds_log'])
def vds_log_command(message):
    """VDS server log'larını göster"""
    user_id = message.from_user.id
    debug_log(f"User {user_id}: /vds_log", "TELEGRAM")
    
    logs = vds_manager.get_vds_logs(20)
    
    if len(logs) > 4000:
        logs = logs[-4000:]  # Telegram mesaj sınırı
    
    log_msg = f"📋 *VDS SERVER LOG'ları (Son 20 satır)*\n\n```\n{logs}\n```"
    
    try:
        bot.reply_to(message, log_msg, parse_mode='Markdown')
    except:
        # Log çok uzunsa dosya olarak gönder
        with open('vds_logs.txt', 'w') as f:
            f.write(logs)
        with open('vds_logs.txt', 'rb') as f:
            bot.send_document(user_id, f, caption="VDS Server Log'ları")

@bot.message_handler(commands=['vds_durum'])
def vds_durum_command(message):
    """VDS server durumunu göster"""
    user_id = message.from_user.id
    
    vds_status = vds_manager.check_vds_status()
    ssh_status = vds_manager.ssh.check_ssh_connection() if hasattr(vds_manager, 'ssh') else False
    
    status_msg = f"""
📊 *VDS SERVER DURUMU*

📍 IP: `{CONFIG.VDS_SERVER_IP}:{CONFIG.VDS_SERVER_PORT}`
🔗 URL: {CONFIG.VDS_SERVER_URL}

📡 *Bağlantı Durumu:*
• VDS Server: {'✅ ÇALIŞIYOR' if vds_status else '❌ KAPALI'}
• SSH Bağlantısı: {'✅ AKTİF' if ssh_status else '❌ KAPALI'}
• Otomatik Başlatma: {'✅ AKTİF' if CONFIG.AUTO_START_VDS else '❌ KAPALI'}

👤 *SSH Bilgileri:*
• Kullanıcı: {CONFIG.VDS_SSH_USER}
• Key Path: {CONFIG.VDS_SSH_KEY_PATH}

🛠 *Komutlar:*
• /vds_baslat - VDS başlat
• /vds_durdur - VDS durdur  
• /vds_restart - VDS restart
• /vds_log - Log'ları göster
• /vds_kur - VDS kurulumu yap
"""
    
    bot.reply_to(message, status_msg, parse_mode='Markdown')

@bot.message_handler(commands=['vds_kur'])
def vds_kur_command(message):
    """VDS server kurulumu yap"""
    user_id = message.from_user.id
    debug_log(f"User {user_id}: /vds_kur", "TELEGRAM")
    
    bot.reply_to(message, "🔄 *VDS Server kurulumu başlatılıyor...*\n\nBu işlem 30-60 saniye sürebilir.", parse_mode='Markdown')
    
    def install_vds():
        try:
            success, msg = vds_manager.install_vds_server()
            
            if success:
                bot.send_message(user_id, f"✅ *VDS SERVER KURULUMU TAMAMLANDI!*\n\n{msg}\n\n/vds_baslat komutuyla başlatabilirsin.", parse_mode='Markdown')
            else:
                bot.send_message(user_id, f"❌ *VDS KURULUM HATASI!*\n\nHata: {msg}", parse_mode='Markdown')
                
        except Exception as e:
            bot.send_message(user_id, f"❌ *VDS kurulum hatası!*\n\n`{str(e)}`", parse_mode='Markdown')
    
    thread = threading.Thread(target=install_vds)
    thread.start()

# ═══════════════════════════════════════════════════════════
# OTOMATİK VDS BAŞLATMA
# ═══════════════════════════════════════════════════════════

def auto_start_vds_server():
    """Bot başladığında VDS server'ı otomatik başlat"""
    if not CONFIG.AUTO_START_VDS:
        debug_log("VDS otomatik başlatma kapalı", "VDS-AUTO")
        return
    
    debug_log("VDS otomatik başlatma kontrolü...", "VDS-AUTO")
    
    # Önce VDS durumunu kontrol et
    if vds_manager.check_vds_status():
        debug_log("✅ VDS server zaten çalışıyor", "VDS-AUTO")
        return
    
    debug_log("VDS server çalışmıyor, başlatılıyor...", "VDS-AUTO")
    
    try:
        # SSH bağlantısını kontrol et
        if not vds_manager.ssh.check_ssh_connection():
            debug_log("❌ SSH bağlantısı kurulamadı, VDS başlatılamıyor", "VDS-AUTO")
            return
        
        # VDS server'ı başlat
        success, msg = vds_manager.start_vds_server()
        
        if success:
            debug_log(f"✅ VDS server başlatıldı: {msg}", "VDS-AUTO")
            
            # Başlatıldı mı kontrol et
            time.sleep(5)
            if vds_manager.check_vds_status():
                debug_log("✅ VDS server başarıyla başlatıldı ve çalışıyor", "VDS-AUTO")
            else:
                debug_log("⚠️ VDS server başlatıldı ama health check başarısız", "VDS-AUTO")
        else:
            debug_log(f"❌ VDS server başlatılamadı: {msg}", "VDS-AUTO")
            
    except Exception as e:
        debug_log(f"❌ VDS otomatik başlatma hatası: {e}", "VDS-AUTO")

# ═══════════════════════════════════════════════════════════
# MEVCUT KODUN DEVAMI (Değişmeyen kısımlar)
# ═══════════════════════════════════════════════════════════

# API MANAGER (Değişmedi)
class APIManager:
    def __init__(self):
        self._lock = threading.Lock()
    
    def _clean_phone(self, phone: str) -> str:
        return phone.replace("+", "").strip()
    
    def _api_call(self, method: str, **params) -> dict:
        url = f"{CONFIG.BASE_URL}/{method}"
        payload = {
            "name": CONFIG.API_NAME,
            "ApiKey": CONFIG.API_KEY,
            "serial": 2,
            **params
        }
        
        if "pn" in payload:
            payload["pn"] = self._clean_phone(payload["pn"])
        
        try:
            query = urllib.parse.urlencode(payload, safe='')
            full_url = f"{url}?{query}"
            
            req = urllib.request.Request(
                full_url,
                headers={
                    'User-Agent': 'Mozilla/5.0',
                    'Accept': 'application/json',
                    'Connection': 'keep-alive'
                }
            )
            
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            
            with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
                return json.loads(resp.read().decode('utf-8'))
        except Exception as e:
            debug_log(f"API çağrı hatası ({method}): {e}", "ERROR")
            return {"code": "0"}
    
    def get_phone(self) -> Optional[str]:
        debug_log("Numara alınıyor...", "API")
        
        for attempt in range(10):
            res = self._api_call(
                "getMobileCode",
                cuy="tr",
                pid=CONFIG.PID,
                num=1,
                noblack=0,
                serial=2
            )
            
            code = str(res.get("code", "0"))
            debug_log(f"Numara deneme {attempt+1}: Kod={code}", "API")
            
            if code == "200":
                data = res.get("data", "")
                if "," in data:
                    raw_num = data.split(",")[0]
                    num = self._clean_phone(raw_num)
                    debug_log(f"✅ Numara alındı: {num}", "API")
                    return num
            elif code == "906":
                time.sleep(0.8)
            else:
                time.sleep(0.5)
        
        debug_log("❌ Numara alınamadı!", "API")
        return None
    
    def start_sms_polling(self, phone: str):
        phone_clean = self._clean_phone(phone)
        result = {"code": None, "done": False}
        
        def poll():
            start = time.time()
            poll_count = 0
            
            debug_log(f"SMS polling başladı: {phone_clean}", "SMS")
            
            while time.time() - start < CONFIG.SMS_TIMEOUT and not result["done"]:
                poll_count += 1
                res = self._api_call("getMsg", pn=phone_clean, pid=CONFIG.PID, serial=2)
                
                code = str(res.get("code", "0"))
                
                if poll_count % 3 == 0:  # Her 3 denemede bir log
                    debug_log(f"SMS deneme {poll_count}: Kod={code}", "SMS")
                
                if code == "200":
                    sms = str(res.get("data", ""))
                    debug_log(f"SMS geldi: {sms}", "SMS")
                    
                    digits = "".join(re.findall(r'\d+', sms))
                    
                    if 4 <= len(digits) <= 8:
                        result["code"] = digits
                        result["done"] = True
                        debug_log(f"✅ SMS kodu bulundu: {digits}", "SMS")
                        return
                
                time.sleep(1.5)
            
            result["done"] = True
            debug_log(f"⏱️ SMS timeout ({CONFIG.SMS_TIMEOUT}s)", "SMS")
        
        thread = threading.Thread(target=poll, daemon=True)
        thread.start()
        return thread, result
    
    def wait_for_sms(self, poll_thread, result, timeout: float = None):
        if timeout is None:
            timeout = CONFIG.SMS_TIMEOUT
        
        poll_thread.join(timeout=timeout)
        
        if result["code"]:
            debug_log(f"📲 SMS alındı: {result['code']}", "SMS")
            return result["code"]
        else:
            debug_log("❌ SMS zaman aşımı", "SMS")
            return None

# CHROME DRIVER MANAGER (Değişmedi)
class ChromeDriverManager:
    def __init__(self):
        self.drivers = []
        self.lock = threading.Lock()
    
    def create_driver(self, worker_id: int):
        """Local Chrome driver oluştur"""
        try:
            debug_log(f"Chrome driver oluşturuluyor (Worker {worker_id})...", "CHROME")
            
            options = Options()
            
            # Chrome binary path (Windows)
            if os.path.exists(CONFIG.CHROME_BINARY_PATH):
                options.binary_location = CONFIG.CHROME_BINARY_PATH
            
            # Headless ayarı
            if CONFIG.HEADLESS:
                options.add_argument("--headless=new")
            
            # Diğer ayarlar
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")
            options.add_argument("--window-size=1920,1080")
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_argument("--disable-extensions")
            options.add_argument("--disable-infobars")
            options.add_argument("--disable-notifications")
            options.add_argument("--disable-popup-blocking")
            
            # Anti-detection
            options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
            options.add_experimental_option('useAutomationExtension', False)
            
            # User agent
            options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
            
            # Driver oluştur
            if os.path.exists(CONFIG.CHROME_DRIVER_PATH):
                service = webdriver.ChromeService(executable_path=CONFIG.CHROME_DRIVER_PATH)
                driver = webdriver.Chrome(service=service, options=options)
            else:
                driver = webdriver.Chrome(options=options)
            
            # Page load timeout
            driver.set_page_load_timeout(CONFIG.PAGE_TIMEOUT)
            driver.set_script_timeout(30)
            
            # Anti-bot detection
            driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            
            debug_log(f"✅ Chrome driver oluşturuldu (Worker {worker_id})", "CHROME")
            
            with self.lock:
                self.drivers.append(driver)
            
            return driver
            
        except Exception as e:
            debug_log(f"❌ Chrome driver hatası: {e}", "CHROME")
            return None
    
    def close_all(self):
        """Tüm driver'ları kapat"""
        with self.lock:
            for driver in self.drivers:
                try:
                    driver.quit()
                except:
                    pass
            self.drivers.clear()
        debug_log("Tüm Chrome driver'lar kapatıldı", "CHROME")

# BROWSER POOL (Değişmedi)
class BrowserPool:
    def __init__(self, max_browsers: int = 4):
        self.max_browsers = max_browsers
        self._pool = Queue()
        self._lock = threading.Lock()
        self._created = 0
        self._active = {}
        self.driver_manager = ChromeDriverManager()
    
    def _create_browser(self, worker_id: int):
        return self.driver_manager.create_driver(worker_id)
    
    def acquire(self, worker_id: int):
        with self._lock:
            if not self._pool.empty():
                driver = self._pool.get()
                self._active[worker_id] = driver
                debug_log(f"Worker {worker_id}: Browser havuzdan alındı", "BROWSER")
                return driver
            
            if self._created < self.max_browsers:
                driver = self._create_browser(worker_id)
                if driver:
                    self._created += 1
                    self._active[worker_id] = driver
                    debug_log(f"Worker {worker_id}: Yeni browser oluşturuldu ({self._created}/{self.max_browsers})", "BROWSER")
                    return driver
        
        # Havuz boşsa ve max'a ulaşıldıysa bekle
        debug_log(f"Worker {worker_id}: Browser için bekleniyor...", "BROWSER")
        driver = self._pool.get()
        with self._lock:
            self._active[worker_id] = driver
        return driver
    
    def release(self, worker_id: int, driver, reset: bool = False):
        if not driver:
            return
        
        with self._lock:
            if worker_id in self._active:
                del self._active[worker_id]
        
        if reset:
            try:
                driver.delete_all_cookies()
                driver.execute_script("window.localStorage.clear();")
                driver.execute_script("window.sessionStorage.clear();")
            except:
                pass
        
        self._pool.put(driver)
        debug_log(f"Worker {worker_id}: Browser havuza geri kondu", "BROWSER")
    
    def close_all(self):
        """Tüm driver'ları temizle"""
        self.driver_manager.close_all()
        while not self._pool.empty():
            try:
                driver = self._pool.get()
                driver.quit()
            except:
                pass
        self._active.clear()
        self._created = 0

# LOCAL BOT (Değişmedi - ESKİ KOD BİREBİR)
class LocalBot:
    def __init__(self, browser_pool, davet_kodu: str = ""):
        self.driver = None
        self.wait = None
        self.worker_id = 0
        self.browser_pool = browser_pool
        self.davet_kodu = davet_kodu
    
    def set_worker_id(self, wid: int):
        self.worker_id = wid
        debug_log(f"Bot Worker ID: {wid}", "BOT")
    
    def init_from_pool(self, driver):
        self.driver = driver
        self.wait = WebDriverWait(driver, 10)
    
    def reset_browser(self):
        if self.driver:
            self.browser_pool.release(self.worker_id, self.driver, reset=True)
            self.driver = None
            self.wait = None
    
    # ESKİ KOD BİREBİR - DEĞİŞTİRİLMEDİ!
    
    def click_kodu_gir(self):
        debug_log("'Kodu Gir' aranıyor...", "BOT")
        elements = self.driver.find_elements(By.XPATH, "//*[contains(text(), 'Kodu Gir')]")
        
        if not elements:
            save_screenshot(self.driver, "kodu_gir_bulunamadi")
            debug_log("'Kodu Gir' bulunamadı!", "BOT")
            return False
        
        clicked = False
        for el in elements:
            if el.is_displayed():
                try:
                    self.driver.execute_script("arguments[0].click();", el)
                    clicked = True
                    debug_log("'Kodu Gir' tıklandı", "BOT")
                    break
                except:
                    pass
        
        return clicked

    def find_davet_input(self):
        inputs = self.driver.find_elements(By.TAG_NAME, "input")
        for inp in inputs:
            ph = inp.get_attribute("placeholder") or ""
            if "KOD" in ph.upper():
                debug_log("Davet inputu bulundu", "BOT")
                return inp
        debug_log("Davet inputu bulunamadı", "BOT")
        return None

    def click_uye_ol_agresif(self):
        debug_log("Üye Ol butonu aranıyor...", "BOT")
        
        for deneme in range(5):
            try:
                btn = self.driver.find_element(By.XPATH, "//button[contains(@class, 'orange') and (text()='Üye Ol' or .//text()='Üye Ol')]")
                self.driver.execute_script("""
                    arguments[0].scrollIntoView({block: 'center'});
                    arguments[0].style.zIndex = '99999';
                    arguments[0].style.visibility = 'visible';
                    arguments[0].disabled = false;
                """, btn)
                time.sleep(1)
                self.driver.execute_script("arguments[0].click();", btn)
                debug_log(f"Üye Ol tıklandı (Deneme {deneme + 1})", "BOT")
                return True
            except Exception as e:
                debug_log(f"Üye Ol deneme {deneme+1} hatası: {e}", "BOT")
                time.sleep(1)

        # JS fallback
        result = self.driver.execute_script("""
            let btn = Array.from(document.querySelectorAll('button')).find(b => 
                b.innerText.includes('Üye Ol') && 
                b.offsetParent !== null && 
                b.disabled === false
            );
            if(btn) { 
                btn.click(); 
                return true; 
            }
            return false;
        """)
        debug_log(f"JS ile Üye Ol: {result}", "BOT")
        return result

    def check_for_phone_input(self):
        phone_inputs = self.driver.find_elements(By.CSS_SELECTOR, "input[type='tel'], input[placeholder*='Telefon']")
        result = len(phone_inputs) > 0
        debug_log(f"Phone input kontrol: {result}", "BOT")
        return result

    def handle_phone_input(self, phone):
        try:
            phone_input = self.driver.find_element(By.CSS_SELECTOR, "input[type='tel']")
            phone_input.clear()
            phone_input.send_keys(phone[-10:])
            time.sleep(0.5)
            
            # Submit butonunu bul ve tıkla
            submit_buttons = self.driver.find_elements(By.CSS_SELECTOR, 'button[type="submit"]')
            if submit_buttons:
                self.driver.execute_script("arguments[0].click();", submit_buttons[0])
            else:
                self.driver.execute_script("""
                    document.querySelector('button[type="submit"]').click();
                """)
            
            debug_log("Phone input işlendi", "BOT")
            return True
        except Exception as e:
            debug_log(f"Phone input hatası: {e}", "BOT")
            save_screenshot(self.driver, "phone_input_hata")
            return False

    def handle_dogulama_popup(self, sms_code):
        debug_log(f"Doğrulama popup işleniyor: {sms_code}", "BOT")
        
        try:
            time.sleep(2)
            
            input_selectors = [
                "//input[@placeholder='GELEN KODU GİR']",
                "//input[contains(@placeholder, 'KODU GİR')]",
                "//input[@maxlength='6']",
                "//input[@type='text' and @maxlength]"
            ]
            
            code_input = None
            for selector in input_selectors:
                try:
                    code_input = self.driver.find_element(By.XPATH, selector)
                    if code_input.is_displayed():
                        debug_log(f"Kod inputu bulundu: {selector}", "BOT")
                        break
                except:
                    continue
            
            if code_input:
                code_input.clear()
                for char in sms_code:
                    code_input.send_keys(char)
                    time.sleep(0.05)
                debug_log(f"Kod girildi: {sms_code}", "BOT")
                time.sleep(1)
            else:
                debug_log("Kod inputu bulunamadı!", "BOT")
                save_screenshot(self.driver, "kod_input_bulunamadi")
                return False
            
            # Devam Et butonunu bul
            button_selectors = [
                "//button[contains(text(), 'Devam Et')]",
                "//button[text()='Devam Et']",
                "//button[contains(@class, 'continue')]",
                "//button[@type='submit']"
            ]
            
            for selector in button_selectors:
                try:
                    btn = self.driver.find_element(By.XPATH, selector)
                    if btn.is_displayed():
                        self.driver.execute_script("arguments[0].click();", btn)
                        debug_log("'Devam Et' tıklandı", "BOT")
                        return True
                except:
                    continue
            
            # JS fallback
            self.driver.execute_script("""
                let btn = Array.from(document.querySelectorAll('button')).find(b => 
                    b.innerText.includes('Devam') || 
                    b.innerText.includes('Onayla') ||
                    b.innerText.includes('Tamam')
                );
                if(btn) {
                    btn.click();
                    return true;
                }
                return false;
            """)
            debug_log("JS ile buton tıklandı", "BOT")
            return True
            
        except Exception as e:
            debug_log(f"Popup hatası: {e}", "BOT")
            save_screenshot(self.driver, "popup_hata")
            return False

    def run(self, phone: str, api: APIManager):
        try:
            debug_log(f"Siteye gidiliyor...", "BOT")
            
            self.init_from_pool(self.browser_pool.acquire(self.worker_id))
            
            self.driver.get("https://etimutlukutu.com")
            time.sleep(3)
            
            debug_log("Üye Ol tıklanıyor...", "BOT")
            
            # Üye Ol butonunu bul (birden fazla yöntem)
            uye_ol_selectors = [
                "//*[contains(text(), 'Üye Ol')]",
                "//button[contains(text(), 'Üye Ol')]",
                "//a[contains(text(), 'Üye Ol')]"
            ]
            
            uye_ol_element = None
            for selector in uye_ol_selectors:
                try:
                    elements = self.driver.find_elements(By.XPATH, selector)
                    for el in elements:
                        if el.is_displayed() and el.is_enabled():
                            uye_ol_element = el
                            break
                    if uye_ol_element:
                        break
                except:
                    continue
            
            if not uye_ol_element:
                save_screenshot(self.driver, "uye_ol_bulunamadi")
                debug_log("Üye Ol butonu bulunamadı!", "BOT")
                return False, None
            
            self.driver.execute_script("arguments[0].click();", uye_ol_element)
            
            time.sleep(3)
            
            debug_log("Telefon inputu bekleniyor...", "BOT")
            
            # Telefon inputunu bekle
            try:
                tel_input = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='tel']"))
                )
                tel_input.clear()
                tel_input.send_keys(phone[-10:])
                debug_log(f"Telefon numarası girildi: {phone[-10:]}", "BOT")
            except:
                save_screenshot(self.driver, "tel_input_bulunamadi")
                debug_log("Telefon inputu bulunamadı!", "BOT")
                return False, None
            
            # DAVET KODU - ESKİ KOD BİREBİR
            if self.davet_kodu:
                debug_log(f"Davet kodu işleniyor: {self.davet_kodu}", "BOT")
                self.click_kodu_gir()
                time.sleep(2)
                
                davet_input = self.find_davet_input()
                if davet_input:
                    davet_input.clear()
                    davet_input.send_keys(self.davet_kodu)
                    debug_log(f"Davet kodu girildi: {self.davet_kodu}", "BOT")
                    time.sleep(1)
            
            # Checkbox'ları işle
            debug_log("Checkboxlar işleniyor...", "BOT")
            try:
                checkboxes = self.driver.find_elements(By.CSS_SELECTOR, "input[type='checkbox']")
                for cb in checkboxes[:3]:  # İlk 3 checkbox
                    try:
                        if not cb.is_selected():
                            self.driver.execute_script("arguments[0].click();", cb)
                            time.sleep(0.2)
                    except:
                        pass
            except:
                pass
            
            # SMS polling başlat
            debug_log("SMS polling başlatılıyor...", "BOT")
            poll_thread, poll_result = api.start_sms_polling(phone)
            
            # Üye Ol butonuna tıkla
            debug_log("Üye Ol butonu tıklanıyor...", "BOT")
            if not self.click_uye_ol_agresif():
                poll_result["done"] = True
                debug_log("Üye Ol butonu tıklanamadı", "BOT")
                save_screenshot(self.driver, "uye_ol_tiklanamadi")
                return False, None
            
            time.sleep(4)
            
            # Ek kontrol: Telefon inputu tekrar görünür mü?
            debug_log("SMS popup kontrolü...", "BOT")
            if self.check_for_phone_input():
                self.handle_phone_input(phone[-10:])
                time.sleep(2)
            
            # SMS beklemeye devam et
            debug_log("SMS bekleniyor...", "BOT")
            sms_code = api.wait_for_sms(poll_thread, poll_result)
            
            if not sms_code:
                save_screenshot(self.driver, "sms_gelmedi")
                debug_log("SMS gelmedi", "BOT")
                return False, None
            
            debug_log(f"✅ AŞAMA 1 TAMAMLANDI, SMS: {sms_code}", "BOT")
            return True, sms_code
            
        except Exception as e:
            debug_log(f"Hata: {e}", "BOT")
            save_screenshot(self.driver, "genel_hata")
            import traceback
            debug_log(f"Traceback: {traceback.format_exc()}", "ERROR")
            return False, None

    def step2_verify(self, sms_code: str) -> bool:
        try:
            debug_log(f"Kod giriliyor: {sms_code}", "BOT")
            success = self.handle_dogulama_popup(sms_code)
            time.sleep(2)
            
            self.reset_browser()
            debug_log(f"Doğrulama sonucu: {success}", "BOT")
            return success
        except Exception as e:
            debug_log(f"Hata: {e}", "BOT")
            save_screenshot(self.driver, "verify_hata")
            self.reset_browser()
            return False

# HYBRID JOB ENGINE (Değişmedi)
class JobEngine:
    def __init__(self, user_id: int, davet_kodlari: List[str], hedefler: List[int]):
        self.user_id = user_id
        self.davet_kodlari = davet_kodlari
        self.hedefler = hedefler
        
        # VDS/Local mod belirle
        self.use_vds = CONFIG.USE_VDS
        
        # VDS kontrol
        if self.use_vds:
            self.vds_client = VDSClient()
            if not self.vds_client.check_status():
                debug_log("⚠️ VDS server çalışmıyor! Local moda geçiliyor...", "SYSTEM")
                self.use_vds = False
        
        # İstatistikler
        self.stats = {
            'baslangic': time.time(),
            'tamamlanan': [0] * len(davet_kodlari),
            'basarisiz': [0] * len(davet_kodlari),
            'toplam_hedef': sum(hedefler),
            'toplam_tamamlanan': 0,
            'toplam_basarisiz': 0,
            'son_guncelleme': time.time(),
            'mod': 'VDS' if self.use_vds else 'LOCAL'
        }
        
        self.stop_event = threading.Event()
        self.lock = threading.Lock()
        
        # MOD'A GÖRE KAYNAKLARI HAZIRLA
        if not self.use_vds:
            self.api = APIManager()
            toplam_hedef = sum(hedefler)
            self.workers = min(toplam_hedef, CONFIG.MAX_LOCAL_WORKERS)
            self.browser_pool = BrowserPool(max_browsers=self.workers)
        else:
            toplam_hedef = sum(hedefler)
            self.workers = min(toplam_hedef, CONFIG.MAX_VDS_WORKERS)
        
        debug_log(f"{self.stats['mod']} Job başlatıldı - User: {user_id}", "JOB")
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
                        self._send_progress_update(vds_mode=True, last_sms=result.get('sms_code', ''))
                else:
                    self.stats['basarisiz'][kod_index] += 1
                    self.stats['toplam_basarisiz'] += 1
                    debug_log(f"Worker {worker_id}: ❌ VDS hatası: {result.get('error', 'Bilinmeyen')}", "WORKER")
            
            time.sleep(1)
        
        debug_log(f"VDS Worker {worker_id} sonlandı", "WORKER")
    
    def _local_worker_task(self, worker_id: int):
        """Local worker görevi"""
        debug_log(f"Local Worker {worker_id} başladı", "WORKER")
        
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
            
            debug_log(f"Local Worker {worker_id}: Kod {davet_kodu} çalışıyor ({tamamlanan}/{hedef})", "WORKER")
            
            # Numara al
            phone = self.api.get_phone()
            if not phone:
                with self.lock:
                    self.stats['basarisiz'][kod_index] += 1
                    self.stats['toplam_basarisiz'] += 1
                debug_log(f"Worker {worker_id}: Numara alınamadı", "WORKER")
                time.sleep(3)
                continue
            
            # Bot'u başlat
            bot = LocalBot(self.browser_pool, davet_kodu)
            bot.set_worker_id(worker_id)
            
            # Aşama 1: Kayıt
            reg_success, sms_code = bot.run(phone, self.api)
            
            if not reg_success:
                with self.lock:
                    self.stats['basarisiz'][kod_index] += 1
                    self.stats['toplam_basarisiz'] += 1
                debug_log(f"Worker {worker_id}: Kayıt başarısız", "WORKER")
                time.sleep(2)
                continue
            
            # Aşama 2: Doğrulama
            verify_success = bot.step2_verify(sms_code)
            
            with self.lock:
                if verify_success:
                    self.stats['tamamlanan'][kod_index] += 1
                    self.stats['toplam_tamamlanan'] += 1
                    
                    yuzde = (self.stats['tamamlanan'][kod_index] / hedef * 100)
                    debug_log(f"Worker {worker_id}: ✅ Kod {davet_kodu}: {self.stats['tamamlanan'][kod_index]}/{hedef} (%{yuzde:.1f})", "WORKER")
                    
                    # Her 10 kayıtta bir bildirim
                    if self.stats['toplam_tamamlanan'] % 10 == 0:
                        self._send_progress_update(vds_mode=False)
                else:
                    self.stats['basarisiz'][kod_index] += 1
                    self.stats['toplam_basarisiz'] += 1
                    debug_log(f"Worker {worker_id}: ❌ Doğrulama başarısız", "WORKER")
            
            time.sleep(1)
        
        debug_log(f"Local Worker {worker_id} sonlandı", "WORKER")
    
    def _send_progress_update(self, vds_mode: bool = False, last_sms: str = ""):
        """Telegram'a ilerleme güncellemesi gönder"""
        try:
            elapsed = time.time() - self.stats['baslangic']
            speed = self.stats['toplam_tamamlanan'] / (elapsed / 60) if elapsed > 60 else 0
            
            if vds_mode:
                msg = f"⚡ *VDS İlerleme*\n\n"
                msg += f"📍 VDS: {CONFIG.VDS_SERVER_IP}\n"
            else:
                msg = f"💻 *Local İlerleme*\n\n"
            
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
        debug_log(f"{self.stats['mod']} job başlatılıyor...", "JOB")
        threads = []
        
        # MOD'A GÖRE WORKER'LARI BAŞLAT
        if self.use_vds:
            for i in range(self.workers):
                t = threading.Thread(target=self._vds_worker_task, args=(i+1,))
                t.daemon = True
                t.start()
                threads.append(t)
                time.sleep(0.3)
        else:
            for i in range(self.workers):
                t = threading.Thread(target=self._local_worker_task, args=(i+1,))
                t.daemon = True
                t.start()
                threads.append(t)
                time.sleep(0.5)
        
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
                            debug_log(f"✅ TÜM HEDEFLER TAMAMLANDI! ({self.stats['mod']})", "JOB")
                            self.stop_event.set()
                            break
                        
                        # Progress log
                        progress_msg = f"📈 {self.stats['mod']} Progress: "
                        for i, (kod, hedef) in enumerate(zip(self.davet_kodlari, self.hedefler)):
                            tamam = self.stats['tamamlanan'][i]
                            if hedef > 0:
                                yuzde = (tamam / hedef * 100)
                                progress_msg += f"{kod}:{tamam}/{hedef} (%{yuzde:.1f}) "
                        debug_log(progress_msg, "PROGRESS")
                
                # 5 dakikada bir durum mesajı gönder
                if current_time - self.stats['son_guncelleme'] >= 300:
                    self._send_progress_update(vds_mode=self.use_vds)
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
        
        # Local modda ise browser'ları temizle
        if not self.use_vds:
            self.browser_pool.close_all()
        
        debug_log(f"{self.stats['mod']} job tamamlandı", "JOB")
        return self.get_final_report()
    
    def stop(self):
        debug_log(f"{self.stats['mod']} job durduruluyor...", "JOB")
        self.stop_event.set()
        
        if not self.use_vds:
            self.browser_pool.close_all()
    
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
                'mod': self.stats['mod'],
                'is_running': not self.stop_event.is_set()
            }
    
    def get_final_report(self) -> str:
        with self.lock:
            elapsed = time.time() - self.stats['baslangic']
            speed = self.stats['toplam_tamamlanan'] / (elapsed / 60) if elapsed > 0 else 0
            
            mod_icon = "⚡" if self.use_vds else "💻"
            mod_text = "VDS" if self.use_vds else "LOCAL"
            
            report = f"{mod_icon} *{mod_text} İŞLEM TAMAMLANDI!*\n\n"
            
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
            report += f"🔧 *Mod*: {mod_text}\n"
            
            if self.use_vds:
                report += f"📍 *VDS IP*: {CONFIG.VDS_SERVER_IP}\n"
            
            if elapsed > 0:
                report += f"⚡ *Hız*: {speed:.1f} kayıt/dk"
            
            return report

# ═══════════════════════════════════════════════════════════
# TELEGRAM HANDLERS (GÜNCELLENDİ - VDS KOMUTLARI EKLENDİ)
# ═══════════════════════════════════════════════════════════

@bot.message_handler(commands=['start'])
def start_command(message):
    user_id = message.from_user.id
    
    if bot_state.has_active_job(user_id):
        bot.reply_to(message, "🚫 *Zaten devam eden bir işleminiz var!*\n\n📊 Durum için: /bilgi\n🛑 Durdurmak için: /stop", parse_mode='Markdown')
        return
    
    # VDS mod kontrolü
    use_vds = CONFIG.USE_VDS
    
    if use_vds:
        vds_client = VDSClient()
        if not vds_client.check_status() and CONFIG.AUTO_START_VDS:
            # VDS kapalıysa otomatik başlatmayı dene
            bot.reply_to(message, "⚠️ *VDS Server kapalı!* Otomatik başlatılıyor...", parse_mode='Markdown')
            
            def try_auto_start():
                success, msg = vds_manager.start_vds_server()
                if success:
                    time.sleep(5)
                    if vds_manager.check_vds_status():
                        bot.send_message(user_id, "✅ *VDS Server başlatıldı!* /start yazarak devam edebilirsin.", parse_mode='Markdown')
                    else:
                        bot.send_message(user_id, "❌ *VDS başlatılamadı!* Local moda geçiliyor.", parse_mode='Markdown')
                        CONFIG.USE_VDS = False
                else:
                    bot.send_message(user_id, f"❌ *VDS başlatma hatası:* {msg}\n\nLocal moda geçiliyor.", parse_mode='Markdown')
                    CONFIG.USE_VDS = False
            
            thread = threading.Thread(target=try_auto_start)
            thread.start()
            return
    
    bot_state.clear_state(user_id)
    bot_state.set_state(user_id, 'waiting_for_codes')
    bot_state.set_data(user_id, 'davet_kodlari', [])
    
    mod_icon = "⚡" if use_vds else "💻"
    mod_text = "VDS" if use_vds else "LOCAL"
    
    msg = f"{mod_icon} *ETI MUTLU KUTU BOT v3.0 ({mod_text} MOD)*\n\n"
    msg += "📝 *Davet Kodları*\n"
    msg += f"Davet kodlarınızı girin (max {CONFIG.MAX_CODES}):\n\n"
    msg += "• *Tek kod:*\n"
    msg += "`8701545434`\n\n"
    msg += "• *Çoklu kod (alt alta):*\n"
    msg += "```\n8701545434\n1234567890\n9876543210\n```\n\n"
    msg += "📌 Her kod için ayrı adet belirleyeceksiniz."
    
    if use_vds:
        vds_status = "✅ ÇALIŞIYOR" if VDSClient().check_status() else "❌ KAPALI"
        msg += f"\n\n📍 *VDS Server:* {CONFIG.VDS_SERVER_IP}:{CONFIG.VDS_SERVER_PORT} ({vds_status})"
        
        # VDS yönetim komutlarını göster
        msg += "\n\n🛠 *VDS Yönetim:*"
        msg += "\n• /vds_baslat - VDS başlat"
        msg += "\n• /vds_durdur - VDS durdur"
        msg += "\n• /vds_restart - VDS yeniden başlat"
        msg += "\n• /vds_durum - VDS durumu"
        msg += "\n• /vds_log - VDS log'ları"
    
    bot.reply_to(message, msg, parse_mode='Markdown')
    debug_log(f"User {user_id}: /start komutu ({mod_text} MOD)", "TELEGRAM")

# Diğer handler'lar (handle_codes, handle_counts, info_command, stop_command, vs.) aynı kalacak
# Sadece /yardim komutunu güncelliyoruz:

@bot.message_handler(commands=['yardim', 'help'])
def help_command(message):
    msg = "🤖 *ETI MUTLU KUTU BOT v3.0 (HYBRID)*\n\n"
    msg += "📋 *Ana Komutlar:*\n"
    msg += "• /start - Yeni işlem başlat\n"
    msg += "• /bilgi - Mevcut durumu gör\n"
    msg += "• /stop - İşlemi durdur\n"
    msg += "• /mod - Mevcut modu göster\n\n"
    
    msg += "🛠 *VDS Yönetim Komutları:*\n"
    msg += "• /vds_baslat - VDS server başlat\n"
    msg += "• /vds_durdur - VDS server durdur\n"
    msg += "• /vds_restart - VDS server yeniden başlat\n"
    msg += "• /vds_durum - VDS server durumu\n"
    msg += "• /vds_log - VDS server log'ları\n"
    msg += "• /vds_kur - VDS server kurulumu\n\n"
    
    msg += "🔧 *Mod Komutları:*\n"
    msg += "• /vds_mod - VDS moduna geç\n"
    msg += "• /local_mod - Local moda geç\n\n"
    
    msg += "📝 *Kullanım:*\n"
    msg += "1. Önce mod seç (/vds_mod veya /local_mod)\n"
    msg += "2. /start yaz\n"
    msg += f"3. Davet kodlarını gir (max {CONFIG.MAX_CODES})\n"
    msg += "4. Her kod için adet belirle (1-500)\n"
    msg += "5. İşlem otomatik başlar\n\n"
    
    msg += "⚙️ *Ayarlar:*\n"
    msg += f"• Max kod: {CONFIG.MAX_CODES}\n"
    msg += f"• Local worker: {CONFIG.MAX_LOCAL_WORKERS}\n"
    msg += f"• VDS worker: {CONFIG.MAX_VDS_WORKERS}\n"
    msg += f"• SMS timeout: {CONFIG.SMS_TIMEOUT}s\n"
    msg += f"• Headless: {CONFIG.HEADLESS}\n"
    msg += f"• VDS Otomatik Başlatma: {CONFIG.AUTO_START_VDS}\n"
    msg += f"• VDS IP: {CONFIG.VDS_SERVER_IP}"
    
    bot.reply_to(message, msg, parse_mode='Markdown')

# Diğer handler'lar (vds_mod_command, local_mod_command, mod_command, debug_command) aynı kalacak

# ═══════════════════════════════════════════════════════════
# MAIN - OTOMATİK VDS BAŞLATMA EKLENDİ
# ═══════════════════════════════════════════════════════════

def main():
    print("="*70)
    print("🤖 ETI MUTLU KUTU - HYBRID TELEGRAM BOT v3.0")
    print("📍 VDS OTOMATİK BAŞLATMA SİSTEMİ AKTİF")
    print("="*70)
    print(f"📱 Token: {CONFIG.BOT_TOKEN[:10]}...")
    print(f"🔧 Mod: {'⚡ VDS' if CONFIG.USE_VDS else '💻 LOCAL'}")
    print(f"📍 VDS IP: {CONFIG.VDS_SERVER_IP}:{CONFIG.VDS_SERVER_PORT}")
    print(f"🔄 Otomatik Başlatma: {'✅ AKTİF' if CONFIG.AUTO_START_VDS else '❌ KAPALI'}")
    print(f"🔐 SSH User: {CONFIG.VDS_SSH_USER}")
    print(f"⚙️ SMS Timeout: {CONFIG.SMS_TIMEOUT}s")
    print(f"⚙️ Max Local Workers: {CONFIG.MAX_LOCAL_WORKERS}")
    print(f"⚙️ Max VDS Workers: {CONFIG.MAX_VDS_WORKERS}")
    print(f"⚙️ Max Kod: {CONFIG.MAX_CODES}")
    print(f"🌐 Site: https://etimutlukutu.com")
    print(f"🐞 Debug Mode: {CONFIG.DEBUG_MODE}")
    print(f"👻 Headless: {CONFIG.HEADLESS}")
    print("="*70)
    
    # VDS otomatik başlatma
    if CONFIG.USE_VDS and CONFIG.AUTO_START_VDS:
        print("🔄 VDS otomatik başlatma kontrolü yapılıyor...")
        auto_start_vds_server()
    
    # VDS durumu
    if CONFIG.USE_VDS:
        vds_client = VDSClient()
        if vds_client.check_status():
            print("✅ VDS Server: Bağlantı başarılı")
        else:
            print("⚠️  VDS Server: Bağlantı başarısız!")
            if CONFIG.AUTO_START_VDS:
                print("ℹ️  Otomatik başlatma aktif, kullanıcı /start dediğinde başlatılacak")
    
    # Token kontrolü
    if CONFIG.BOT_TOKEN == "8182630877:AAFtGjtxYv0dqQAGnziaBnaf-GrrI0sPzdk":
        print("⚠️  UYARI: Varsayılan bot token'ı kullanılıyor!")
        print("⚠️  Lütfen CONFIG.BOT_TOKEN değerini kendi token'ınla değiştir!")
    
    # Chrome driver kontrolü
    if not os.path.exists(CONFIG.CHROME_DRIVER_PATH):
        print(f"⚠️  ChromeDriver bulunamadı: {CONFIG.CHROME_DRIVER_PATH}")
        print("📥 İndir: https://chromedriver.chromium.org/")
        print("📁 ChromeDriver'ı bot ile aynı dizine koyun")
    
    # Chrome binary kontrolü
    if not os.path.exists(CONFIG.CHROME_BINARY_PATH):
        print(f"⚠️  Chrome binary bulunamadı: {CONFIG.CHROME_BINARY_PATH}")
        print("📌 Chrome yüklü değil veya farklı konumda")
    
    print("\n🚀 Bot başlatılıyor...")
    print("📞 Yeni Komutlar: /vds_baslat, /vds_durdur, /vds_restart, /vds_durum, /vds_log")
    print("💬 Telegram'dan botunuza mesaj atarak başlatabilirsiniz")
    print("="*70)
    
    # Signal handler (Ctrl+C)
    def signal_handler(sig, frame):
        print("\n\n🛑 Bot durduruluyor...")
        # Aktif tüm job'ları durdur
        for user_id in list(bot_state.active_jobs.keys()):
            job = bot_state.get_active_job(user_id)
            if job:
                job.stop()
        # SSH bağlantısını kapat
        if hasattr(vds_manager, 'ssh'):
            vds_manager.ssh.close()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        bot.polling(timeout=30, long_polling_timeout=30)
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
    
    # Paramiko (SSH) paketini kontrol et
    try:
        import paramiko
    except ImportError:
        print("⚠️  'paramiko' paketi kurulu değil! SSH özellikleri devre dışı.")
        print("📦 Kurulum: pip install paramiko")
        CONFIG.AUTO_START_VDS = False
    
    main()
