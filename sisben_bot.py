#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
\u2554\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2557
\u2551                    BOT DOX                               \u2551
\u2551                                                          \u2551
\u2551  \u2705 SISBEN IV          \u2192 sisben.gov.co                   \u2551
\u2551  \ud83d\udcf8 Verificaci\u00f3n foto  \u2192 Al hacer /start                 \u2551
\u2551  \ud83c\udf10 Captura IP         \u2192 Via Web App                     \u2551
\u2551  \ud83d\udccb Datos usuario      \u2192 Foto \u00b7 IP \u00b7 Contacto \u00b7 C\u00e9dula   \u2551
\u2551                                                          \u2551
\u2551  Owner: 8114050673                                       \u2551
\u255a\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u255d
"""

import logging, time, os, glob, asyncio, json, re
from datetime import datetime, timedelta
from flask import Flask, request as flask_request, jsonify, send_from_directory
from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    WebAppInfo, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler,
)
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import TimeoutException, ElementNotInteractableException, InvalidElementStateException
import threading
import base64

# \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
#  CONFIG
# \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
TOKEN    = os.environ.get("BOT_TOKEN", "8574051542:AAH_N4RBST0wCpkLKDOFNEc1R93vePWxEPY")
OWNER_ID = 8114050673
DB_FILE  = "database.json"

# URL p\u00fablica de Railway \u2014 se detecta autom\u00e1ticamente
RAILWAY_URL = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "")
if RAILWAY_URL and not RAILWAY_URL.startswith("http"):
    RAILWAY_URL = f"https://{RAILWAY_URL}"

TIPOS_SISBEN = [
    ("Registro Civil","1"),       ("Tarjeta de Identidad","2"),
    ("Cedula de Ciudadania","3"), ("Cedula de Extranjeria","4"),
    ("DNI Pais de Origen","5"),   ("DNI Pasaporte","6"),
    ("Salvoconducto Refugiado","7"), ("Permiso Esp. Permanencia","8"),
    ("Permiso Protec. Temporal","9"),
]

(SEL_TIPO, ING_NUMERO) = range(2)

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
#  BASE DE DATOS
# \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
def cargar_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE) as f: return json.load(f)
        except: pass
    db = {"admins": [OWNER_ID], "usuarios": {}, "pendientes": {}, "consultas": 0}
    guardar_db(db); return db

def guardar_db(db):
    with open(DB_FILE, "w") as f: json.dump(db, f, indent=2)

def es_owner(uid):  return uid == OWNER_ID
def es_admin(uid):
    db = cargar_db()
    return uid == OWNER_ID or uid in db.get("admins", [])

def es_aprobado(uid):
    if es_admin(uid): return True
    db = cargar_db()
    return str(uid) in db.get("usuarios", {})

def es_pendiente(uid):
    db = cargar_db()
    return str(uid) in db.get("pendientes", {})

# \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
#  SELENIUM HELPERS
# \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
def get_driver():
    opts = Options()
    for a in ["--headless=new","--no-sandbox","--disable-dev-shm-usage",
              "--disable-gpu","--disable-extensions",
              "--blink-settings=imagesEnabled=false",
              "--window-size=1920,1080","--log-level=3",
              "--disable-blink-features=AutomationControlled"]:
        opts.add_argument(a)
    opts.add_experimental_option("excludeSwitches",["enable-logging","enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    cb = os.environ.get("CHROME_BIN")
    if not cb:
        for p in ["/usr/bin/chromium","/usr/bin/chromium-browser","/usr/bin/google-chrome"]:
            if os.path.exists(p): cb = p; break
    if not cb:
        r = glob.glob("/nix/store/*/bin/chromium*")
        if r: cb = sorted(r)[0]
    if cb: opts.binary_location = cb
    cd = os.environ.get("CHROMEDRIVER_PATH")
    if not cd:
        for p in ["/usr/bin/chromedriver","/usr/bin/chromium-driver","/usr/lib/chromium/chromedriver"]:
            if os.path.exists(p): cd = p; break
    if not cd:
        r = glob.glob("/nix/store/*/bin/chromedriver*")
        if r: cd = sorted(r)[0]
    return webdriver.Chrome(service=Service(cd), options=opts) if cd else webdriver.Chrome(options=opts)

def safe_send(driver, el, text):
    try:
        el.clear(); el.send_keys(text)
    except (ElementNotInteractableException, InvalidElementStateException):
        driver.execute_script("arguments[0].removeAttribute('readonly');arguments[0].removeAttribute('disabled');", el)
        driver.execute_script("arguments[0].value='';", el)
        driver.execute_script("arguments[0].value=arguments[1];", el, text)
        driver.execute_script(
            "arguments[0].dispatchEvent(new Event('input',{bubbles:true}));"
            "arguments[0].dispatchEvent(new Event('change',{bubbles:true}));", el)

def safe_select(driver, el, value):
    try: Select(el).select_by_value(value)
    except:
        driver.execute_script(f"arguments[0].value='{value}';", el)
        driver.execute_script("arguments[0].dispatchEvent(new Event('change',{bubbles:true}));", el)

def clean_error(e):
    return str(e).split("Stacktrace")[0].split("\n")[0].strip()[:200]

# \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
#  M\u00d3DULO SISBEN IV
# \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
def consultar_sisben(tipo, numero):
    driver = None
    try:
        driver = get_driver(); driver.set_page_load_timeout(30)
        driver.get("https://reportes.sisben.gov.co/DNP_SisbenConsulta")
        time.sleep(5)
        sel = WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.ID, "TipoID")))
        safe_select(driver, sel, tipo); time.sleep(0.8)
        inp = driver.find_element(By.ID, "documento")
        safe_send(driver, inp, numero); time.sleep(0.8)
        driver.find_element(By.ID, "botonenvio").click()
        time.sleep(8)
        html = driver.page_source
        if "no se encontr" in html.lower() or "no registra" in html.lower(): return None
        r = {}
        try: r["grupo"] = driver.find_element(By.XPATH, "//p[contains(@class,'text-uppercase') and contains(@class,'text-white')]").text.strip()
        except: pass
        try: r["clasificacion"] = driver.find_element(By.XPATH, "//div[contains(@class,'imagenpuntaje')]//p[contains(@style,'18px')]").text.strip()
        except: pass
        for label, key in [("Nombres","nombres"),("Apellidos","apellidos"),("Municipio","municipio"),
                           ("Departamento","departamento"),("Ficha","ficha"),
                           ("Fecha de consulta","fecha"),("Encuesta vigente","encuesta")]:
            try:
                v = driver.find_element(By.XPATH, f"//p[contains(text(),'{label}')]/following-sibling::p[1]").text.strip()
                if v: r[key] = " ".join(v.split())
            except: pass
        return r if r else None
    except TimeoutException: return {"error": "Tiempo de espera agotado"}
    except Exception as e: return {"error": clean_error(e)}
    finally:
        if driver:
            try: driver.quit()
            except: pass

def fmt_sisben(r):
    if r is None:
        return (
            "\u2554\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2557\n"
            "\u2551       M\u00d3DULO SISBEN IV         \u2551\n"
            "\u255a\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u255d\n\n"
            "\u274c *NO REGISTRADO EN SISBEN IV*\n\n"
            "_Este documento no aparece en la base de datos._"
        )
    if "error" in r: return f"\u26a0\ufe0f *Error SISBEN:* `{r['error']}`"
    m  = "\u2554\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2557\n"
    m += "\u2551       M\u00d3DULO SISBEN IV         \u2551\n"
    m += "\u255a\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u255d\n\n"
    if "grupo" in r:         m += f"\ud83c\udff7 *GRUPO:* {r['grupo']}\n"
    if "clasificacion" in r: m += f"\ud83d\udcca *Puntaje:* {r['clasificacion']}\n"
    m += "\n\ud83d\udc64 *DATOS PERSONALES*\n\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n"
    for k, l in [("nombres","Nombres"),("apellidos","Apellidos"),
                 ("municipio","Municipio"),("departamento","Departamento")]:
        if k in r: m += f"  \ud83d\udd39 *{l}:* {r[k]}\n"
    if any(k in r for k in ["ficha","fecha","encuesta"]):
        m += "\n\ud83d\udccb *REGISTRO*\n\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n"
        for k, l in [("ficha","Ficha"),("fecha","Fecha consulta"),("encuesta","Encuesta vigente")]:
            if k in r: m += f"  \ud83d\udd39 *{l}:* {r[k]}\n"
    return m

# \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
#  MEN\u00daS
# \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
def menu_tipo_sisben():
    b, f = [], []
    for n, v in TIPOS_SISBEN:
        f.append(InlineKeyboardButton(n, callback_data=f"ts_{v}"))
        if len(f) == 2: b.append(f); f = []
    if f: b.append(f)
    b.append([InlineKeyboardButton("\u274c Cancelar", callback_data="cancelar")])
    return InlineKeyboardMarkup(b)

def teclado_panel():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("\u23f3 Pendientes",  callback_data="panel_pendientes")],
        [InlineKeyboardButton("\ud83d\udc65 Usuarios",    callback_data="panel_usuarios")],
        [InlineKeyboardButton("\ud83d\udee1 Admins",      callback_data="panel_admins")],
        [InlineKeyboardButton("\ud83d\udcca Stats",       callback_data="panel_stats")],
    ])

# \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
#  FLASK WEB APP (captura foto + IP)
# \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
flask_app = Flask(__name__)

# Variable global para acceder al bot desde Flask
_bot_app = None

HTML_VERIFICACION = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Verificaci\u00f3n de Acceso</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    background: #0f0f1a;
    color: #fff;
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 20px;
  }
  .card {
    background: #1a1a2e;
    border-radius: 20px;
    padding: 30px 24px;
    width: 100%;
    max-width: 400px;
    box-shadow: 0 8px 32px rgba(0,0,0,0.4);
    border: 1px solid #2a2a4a;
  }
  h2 { font-size: 22px; text-align:center; margin-bottom: 8px; }
  p  { font-size: 13px; color: #aaa; text-align:center; margin-bottom: 20px; }
  video {
    width: 100%;
    border-radius: 12px;
    background: #000;
    max-height: 280px;
    object-fit: cover;
  }
  canvas { display:none; }
  .btn {
    width: 100%;
    padding: 14px;
    border: none;
    border-radius: 12px;
    font-size: 16px;
    font-weight: 600;
    cursor: pointer;
    margin-top: 14px;
    transition: opacity 0.2s;
  }
  .btn:active { opacity: 0.7; }
  .btn-primary { background: #4e7cff; color: #fff; }
  .btn-success { background: #22c55e; color: #fff; display:none; }
  #status {
    margin-top: 14px;
    font-size: 13px;
    text-align: center;
    color: #aaa;
    min-height: 20px;
  }
  .preview {
    width: 100%;
    border-radius: 12px;
    margin-top: 14px;
    display: none;
  }
</style>
</head>
<body>
<div class="card">
  <h2>\ud83d\udd10 Verificaci\u00f3n</h2>
  <p>Toma una selfie para solicitar acceso al bot</p>
  <video id="video" autoplay playsinline muted></video>
  <canvas id="canvas"></canvas>
  <img id="preview" class="preview" alt="preview">
  <button class="btn btn-primary" id="btnFoto">\ud83d\udcf8 Tomar foto</button>
  <button class="btn btn-success" id="btnEnviar">\u2705 Enviar verificaci\u00f3n</button>
  <div id="status">Iniciando c\u00e1mara...</div>
</div>

<script>
const tg = window.Telegram.WebApp;
tg.ready();
tg.expand();

const video   = document.getElementById('video');
const canvas  = document.getElementById('canvas');
const preview = document.getElementById('preview');
const btnFoto  = document.getElementById('btnFoto');
const btnEnviar = document.getElementById('btnEnviar');
const status  = document.getElementById('status');

let fotoCapturada = null;

// Obtener IP
async function getIP() {
  try {
    const r = await fetch('https://api.ipify.org?format=json');
    const d = await r.json();
    return d.ip;
  } catch { return 'desconocida'; }
}

// Iniciar c\u00e1mara frontal
navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user' }, audio: false })
  .then(stream => {
    video.srcObject = stream;
    status.textContent = '\ud83d\udcf7 C\u00e1mara lista \u2014 toca "Tomar foto"';
  })
  .catch(err => {
    status.textContent = '\u274c Permiso de c\u00e1mara denegado';
    btnFoto.disabled = true;
  });

// Capturar foto
btnFoto.onclick = () => {
  canvas.width  = video.videoWidth  || 640;
  canvas.height = video.videoHeight || 480;
  canvas.getContext('2d').drawImage(video, 0, 0);
  fotoCapturada = canvas.toDataURL('image/jpeg', 0.8);
  preview.src = fotoCapturada;
  preview.style.display = 'block';
  btnEnviar.style.display = 'block';
  btnFoto.textContent = '\ud83d\udd04 Tomar otra';
  status.textContent = 'Foto tomada \u2014 rev\u00edsala y env\u00eda';
};

// Enviar al servidor
btnEnviar.onclick = async () => {
  if (!fotoCapturada) return;
  btnEnviar.disabled = true;
  btnEnviar.textContent = '\u23f3 Enviando...';
  status.textContent = 'Obteniendo datos...';

  const ip = await getIP();
  const user = tg.initDataUnsafe?.user || {};

  try {
    const resp = await fetch('/verificar', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        foto:     fotoCapturada,
        ip:       ip,
        user_id:  user.id       || 0,
        nombre:   user.first_name || '?',
        apellido: user.last_name  || '',
        username: user.username   || 'sin_usuario',
        idioma:   user.language_code || '?',
      })
    });

    const data = await resp.json();
    if (data.ok) {
      status.textContent = '\u2705 Enviado. El admin revisar\u00e1 tu solicitud.';
      btnEnviar.textContent = '\u2705 Enviado';
      setTimeout(() => tg.close(), 2500);
    } else {
      status.textContent = '\u26a0\ufe0f Error al enviar. Intenta de nuevo.';
      btnEnviar.disabled = false;
      btnEnviar.textContent = '\u2705 Enviar verificaci\u00f3n';
    }
  } catch(e) {
    status.textContent = '\u274c Error de red.';
    btnEnviar.disabled = false;
    btnEnviar.textContent = '\u2705 Enviar verificaci\u00f3n';
  }
};
</script>
</body>
</html>"""


@flask_app.route("/verificar_page")
def verificar_page():
    return HTML_VERIFICACION


@flask_app.route("/verificar", methods=["POST"])
def recibir_verificacion():
    data = flask_request.json or {}

    foto_b64  = data.get("foto", "")
    ip        = data.get("ip", "desconocida")
    user_id   = data.get("user_id", 0)
    nombre    = data.get("nombre", "?")
    apellido  = data.get("apellido", "")
    username  = data.get("username", "sin_usuario")
    idioma    = data.get("idioma", "?")

    # Guardar en pendientes
    db = cargar_db()
    if "pendientes" not in db: db["pendientes"] = {}
    db["pendientes"][str(user_id)] = {
        "nombre":   nombre,
        "apellido": apellido,
        "username": username,
        "ip":       ip,
        "idioma":   idioma,
        "fecha":    datetime.now().isoformat(),
        "foto_b64": foto_b64,
    }
    guardar_db(db)

    # Enviar al admin via Telegram (en hilo separado)
    if _bot_app:
        asyncio.run_coroutine_threadsafe(
            _enviar_verificacion_admin(user_id, nombre, apellido, username, ip, idioma, foto_b64),
            _bot_app.bot._request._loop if hasattr(_bot_app.bot, '_request') else asyncio.get_event_loop()
        )

    return jsonify({"ok": True})


async def _enviar_verificacion_admin(user_id, nombre, apellido, username, ip, idioma, foto_b64):
    """Env\u00eda foto + datos al admin con botones aprobar/rechazar."""
    try:
        db = cargar_db()
        caption = (
            f"\ud83d\udcf8 *Nueva solicitud de acceso*\n\n"
            f"\ud83d\udc64 *Nombre:* {nombre} {apellido}\n"
            f"\ud83d\udcf1 *Usuario:* @{username}\n"
            f"\ud83c\udd94 *ID:* `{user_id}`\n"
            f"\ud83c\udf10 *IP:* `{ip}`\n"
            f"\ud83c\udf0d *Idioma:* {idioma}\n"
            f"\ud83d\udcc5 *Fecha:* {datetime.now().strftime('%d/%m/%Y %H:%M')}"
        )
        botones = InlineKeyboardMarkup([[
            InlineKeyboardButton("\u2705 Aprobar", callback_data=f"aprobar_{user_id}"),
            InlineKeyboardButton("\u274c Rechazar", callback_data=f"rechazar_{user_id}"),
        ]])

        if foto_b64 and "," in foto_b64:
            foto_bytes = base64.b64decode(foto_b64.split(",")[1])
            for admin_id in db.get("admins", [OWNER_ID]):
                try:
                    await _bot_app.bot.send_photo(
                        chat_id=admin_id,
                        photo=foto_bytes,
                        caption=caption,
                        parse_mode="Markdown",
                        reply_markup=botones
                    )
                except Exception as e:
                    logger.error(f"Error enviando foto a admin {admin_id}: {e}")
        else:
            for admin_id in db.get("admins", [OWNER_ID]):
                try:
                    await _bot_app.bot.send_message(
                        chat_id=admin_id,
                        text=caption + "\n\n_(Sin foto)_",
                        parse_mode="Markdown",
                        reply_markup=botones
                    )
                except Exception as e:
                    logger.error(f"Error enviando mensaje a admin {admin_id}: {e}")
    except Exception as e:
        logger.error(f"Error en _enviar_verificacion_admin: {e}")


# \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
#  COMANDOS BOT
# \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    args = context.args or []

    # Ya aprobado
    if es_aprobado(u.id):
        await update.message.reply_text(
            f"\ud83d\udc4b Hola *{u.first_name}*\n\n"
            "\u2705 *Acceso activo*\n\n"
            "\ud83d\udce1 *Comandos disponibles:*\n"
            "  /consultar \u2014 Consultar SISBEN IV\n"
            "  /ayuda \u2014 Ayuda de uso\n",
            parse_mode="Markdown"
        )
        return

    # Ya tiene solicitud pendiente
    if es_pendiente(u.id):
        await update.message.reply_text(
            "\u23f3 *Tu solicitud ya fue enviada*\n\n"
            "Espera la aprobaci\u00f3n del administrador.",
            parse_mode="Markdown"
        )
        return

    # Enviar bot\u00f3n Web App para verificaci\u00f3n
    if RAILWAY_URL:
        webapp_url = f"{RAILWAY_URL}/verificar_page"
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                "\ud83d\udcf8 Verificar identidad",
                web_app=WebAppInfo(url=webapp_url)
            )
        ]])
        await update.message.reply_text(
            f"\ud83d\udc4b Hola *{u.first_name}*\n\n"
            "\ud83d\udd10 *Para solicitar acceso al bot:*\n\n"
            "1\ufe0f\u20e3 Toca el bot\u00f3n de abajo\n"
            "2\ufe0f\u20e3 Permite el acceso a la c\u00e1mara\n"
            "3\ufe0f\u20e3 Toma una selfie\n"
            "4\ufe0f\u20e3 Env\u00eda la verificaci\u00f3n\n\n"
            "_El administrador revisar\u00e1 tu solicitud._",
            parse_mode="Markdown",
            reply_markup=keyboard
        )
    else:
        # Fallback sin Railway URL: pedir foto directamente
        await update.message.reply_text(
            f"\ud83d\udc4b Hola *{u.first_name}*\n\n"
            "\ud83d\udcf8 *Para solicitar acceso, env\u00eda una selfie* (foto tuya).\n\n"
            "_El administrador revisar\u00e1 tu solicitud._",
            parse_mode="Markdown"
        )
        context.user_data["esperando_selfie"] = True


async def recibir_foto_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fallback: recibe selfie directamente si no hay RAILWAY_URL."""
    u = update.effective_user
    if not context.user_data.get("esperando_selfie"): return
    if es_aprobado(u.id) or es_pendiente(u.id): return

    foto = update.message.photo[-1]
    db = cargar_db()
    if "pendientes" not in db: db["pendientes"] = {}
    db["pendientes"][str(u.id)] = {
        "nombre":   u.first_name,
        "apellido": u.last_name or "",
        "username": u.username or "sin_usuario",
        "ip":       "N/A (foto directa)",
        "idioma":   "?",
        "fecha":    datetime.now().isoformat(),
        "file_id":  foto.file_id,
    }
    guardar_db(db)
    context.user_data.pop("esperando_selfie", None)

    caption = (
        f"\ud83d\udcf8 *Nueva solicitud de acceso*\n\n"
        f"\ud83d\udc64 *Nombre:* {u.first_name} {u.last_name or ''}\n"
        f"\ud83d\udcf1 *Usuario:* @{u.username or 'sin_usuario'}\n"
        f"\ud83c\udd94 *ID:* `{u.id}`\n"
        f"\ud83c\udf10 *IP:* N/A\n"
        f"\ud83d\udcc5 *Fecha:* {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    )
    botones = InlineKeyboardMarkup([[
        InlineKeyboardButton("\u2705 Aprobar", callback_data=f"aprobar_{u.id}"),
        InlineKeyboardButton("\u274c Rechazar", callback_data=f"rechazar_{u.id}"),
    ]])

    for admin_id in db.get("admins", [OWNER_ID]):
        try:
            await context.bot.send_photo(
                chat_id=admin_id, photo=foto.file_id,
                caption=caption, parse_mode="Markdown",
                reply_markup=botones
            )
        except: pass

    await update.message.reply_text(
        "\u2705 *Selfie recibida*\n\nEspera la aprobaci\u00f3n del administrador.",
        parse_mode="Markdown"
    )


# \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
#  CALLBACKS APROBAR / RECHAZAR
# \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
async def callback_aprobacion(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    uid = q.from_user.id
    if not es_admin(uid): return

    data = q.data
    db = cargar_db()

    # \u2500\u2500 Aprobar / Rechazar solicitud \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
    if data.startswith("aprobar_"):
        target_id = int(data.replace("aprobar_", ""))
        info = db.get("pendientes", {}).pop(str(target_id), {})
        if "usuarios" not in db: db["usuarios"] = {}
        db["usuarios"][str(target_id)] = {
            "nombre":   info.get("nombre", "?"),
            "username": info.get("username", "?"),
            "ip":       info.get("ip", "?"),
            "desde":    datetime.now().isoformat(),
        }
        guardar_db(db)
        await q.edit_message_caption(
            caption=q.message.caption + f"\n\n\u2705 *APROBADO* por @{q.from_user.username or uid}",
            parse_mode="Markdown"
        )
        try:
            await context.bot.send_message(
                chat_id=target_id,
                text="\u2705 *Acceso aprobado*\n\n\u00a1Bienvenido! Ya puedes usar el bot.\nEscribe /start para comenzar.",
                parse_mode="Markdown"
            )
        except: pass

    elif data.startswith("rechazar_"):
        target_id = int(data.replace("rechazar_", ""))
        db.get("pendientes", {}).pop(str(target_id), None)
        guardar_db(db)
        await q.edit_message_caption(
            caption=q.message.caption + f"\n\n\u274c *RECHAZADO* por @{q.from_user.username or uid}",
            parse_mode="Markdown"
        )
        try:
            await context.bot.send_message(
                chat_id=target_id,
                text="\u274c *Acceso denegado*\n\nTu solicitud fue rechazada.",
                parse_mode="Markdown"
            )
        except: pass

    # \u2500\u2500 Panel admin callbacks \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
    elif data == "panel_volver":
        db2 = cargar_db()
        await q.edit_message_text(
            f"\ud83d\udd10 *Panel Admin*\n\n"
            f"\u23f3 Pendientes: {len(db2.get('pendientes',{}))}\n"
            f"\ud83d\udc65 Usuarios: {len(db2.get('usuarios',{}))}\n"
            f"\ud83d\udee1 Admins: {len(db2.get('admins',[]))}\n",
            reply_markup=teclado_panel(), parse_mode="Markdown"
        )

    elif data == "panel_stats":
        db2 = cargar_db()
        await q.edit_message_text(
            f"\ud83d\udcca *Estad\u00edsticas*\n\n"
            f"\ud83d\udc51 Owner: `{OWNER_ID}`\n"
            f"\ud83d\udee1 Admins: {len(db2.get('admins',[]))}\n"
            f"\ud83d\udc65 Usuarios aprobados: {len(db2.get('usuarios',{}))}\n"
            f"\u23f3 Pendientes: {len(db2.get('pendientes',{}))}\n"
            f"\ud83d\udd0d Consultas: {db2.get('consultas',0)}\n",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("\ud83d\udd19 Volver","panel_volver")]]),
            parse_mode="Markdown"
        )

    elif data == "panel_pendientes":
        db2 =