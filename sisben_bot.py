#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging, time, os, glob, subprocess
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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
from selenium.common.exceptions import TimeoutException

TOKEN    = "8574051542:AAH_N4RBST0wCpkLKDOFNEc1R93vePWxEPY"
ADMIN_ID = 8114050673
URL_PAGINA = "https://reportes.sisben.gov.co/DNP_SisbenConsulta"
ELIGIENDO_TIPO, INGRESANDO_NUMERO = range(2)

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

TIPOS = [
    ("Registro Civil","1"),("Tarjeta de Identidad","2"),
    ("Cedula de Ciudadania","3"),("Cedula de Extranjeria","4"),
    ("DNI Pais de Origen","5"),("DNI Pasaporte","6"),
    ("Salvoconducto Refugiado","7"),("Permiso Esp. Permanencia","8"),
    ("Permiso Protec. Temporal","9"),
]

def get_driver():
    opts = Options()
    for arg in ["--headless=new","--no-sandbox","--disable-dev-shm-usage",
                "--disable-gpu","--disable-extensions",
                "--blink-settings=imagesEnabled=false",
                "--window-size=1920,1080","--log-level=3"]:
        opts.add_argument(arg)
    opts.add_experimental_option("excludeSwitches",["enable-logging","enable-automation"])
    opts.add_experimental_option("useAutomationExtension",False)

    chrome_bin = os.environ.get("CHROME_BIN")
    if not chrome_bin:
        for path in ["/usr/bin/chromium","/usr/bin/chromium-browser",
                     "/usr/bin/google-chrome","/usr/bin/chrome"]:
            if os.path.exists(path):
                chrome_bin = path
                break
    if not chrome_bin:
        resultados = glob.glob("/nix/store/*/bin/chromium*")
        if resultados:
            chrome_bin = sorted(resultados)[0]
    if chrome_bin:
        opts.binary_location = chrome_bin

    chromedriver = os.environ.get("CHROMEDRIVER_PATH")
    if not chromedriver:
        for path in ["/usr/bin/chromedriver","/usr/bin/chromium-driver",
                     "/usr/lib/chromium/chromedriver",
                     "/usr/lib/chromium-browser/chromedriver"]:
            if os.path.exists(path):
                chromedriver = path
                break
    if not chromedriver:
        resultados = glob.glob("/nix/store/*/bin/chromedriver*")
        if resultados:
            chromedriver = sorted(resultados)[0]

    if chromedriver:
        return webdriver.Chrome(service=Service(chromedriver), options=opts)
    return webdriver.Chrome(options=opts)


def consultar_sisben(tipo, numero):
    driver = None
    try:
        driver = get_driver()
        driver.set_page_load_timeout(30)
        driver.get(URL_PAGINA)
        time.sleep(5)

        wait = WebDriverWait(driver, 20)
        Select(wait.until(EC.presence_of_element_located((By.ID, "TipoID")))).select_by_value(tipo)
        time.sleep(1)

        inp = driver.find_element(By.ID, "documento")
        inp.clear()
        inp.send_keys(numero)
        time.sleep(1)

        driver.execute_script("arguments[0].click();", driver.find_element(By.ID, "botonenvio"))
        time.sleep(8)

        html = driver.page_source
        if "no se encontr" in html.lower() or "no registra" in html.lower():
            return None

        r = {}
        try: r["grupo"] = driver.find_element(By.XPATH,"//p[contains(@class,'text-uppercase') and contains(@class,'text-white')]").text.strip()
        except: pass
        try: r["clasificacion"] = driver.find_element(By.XPATH,"//div[contains(@class,'imagenpuntaje')]//p[contains(@style,'18px')]").text.strip()
        except: pass

        for label, key in [("Nombres","nombres"),("Apellidos","apellidos"),
                           ("Municipio","municipio"),("Departamento","departamento"),
                           ("Ficha","ficha"),("Fecha de consulta","fecha"),
                           ("Encuesta vigente","encuesta")]:
            try:
                v = driver.find_element(By.XPATH,f"//p[contains(text(),'{label}')]/following-sibling::p[1]").text.strip()
                if v: r[key] = " ".join(v.split())
            except: pass

        return r if r else None

    except TimeoutException:
        return {"error":"Tiempo de espera agotado"}
    except Exception as e:
        return {"error":str(e)}
    finally:
        if driver:
            try: driver.quit()
            except: pass


def fmt(r):
    if r is None: return "❌ NO ENCONTRADO\n\nDocumento no registrado en SISBEN IV."
    if "error" in r: return f"⚠️ Error: {r['error']}"
    m = "✅ RESULTADO SISBEN IV\n\n"
    if "grupo" in r: m += f"🏷 GRUPO: {r['grupo']}\n"
    if "clasificacion" in r: m += f"📊 Puntaje: {r['clasificacion']}\n"
    m += "\n👤 DATOS\n"
    for k,l in [("nombres","Nombres"),("apellidos","Apellidos"),("municipio","Municipio"),("departamento","Depto")]:
        if k in r: m += f"- {l}: {r[k]}\n"
    if any(k in r for k in ["ficha","fecha","encuesta"]):
        m += "\n📋 REGISTRO\n"
        for k,l in [("ficha","Ficha"),("fecha","Fecha"),("encuesta","Encuesta")]:
            if k in r: m += f"- {l}: {r[k]}\n"
    return m


def menu():
    b,f=[],[]
    for nombre,valor in TIPOS:
        f.append(InlineKeyboardButton(nombre,callback_data=f"t_{valor}"))
        if len(f)==2: b.append(f); f=[]
    if f: b.append(f)
    b.append([InlineKeyboardButton("❌ Cancelar",callback_data="cancelar")])
    return InlineKeyboardMarkup(b)


async def start(u, c):
    out = subprocess.getoutput(
        "which chromium; which chromedriver; ls /usr/bin/chrom*; chromium --version 2>&1; chromedriver --version 2>&1"
    )
    await u.message.reply_text(f"🔍 Info del sistema:\n\n{out}")

async def ayuda(u,c): await u.message.reply_text("/consultar\n/cancelar\n/ayuda")

async def consultar(u,c):
    await u.message.reply_text("Selecciona tipo de documento:",reply_markup=menu())
    return ELIGIENDO_TIPO

async def elegir_tipo(u,c):
    q=u.callback_query; await q.answer()
    if q.data=="cancelar": await q.edit_message_text("Cancelado."); return ConversationHandler.END
    valor=q.data.replace("t_",""); nombre=next((n for n,v in TIPOS if v==valor),valor)
    c.user_data["tipo"]=valor
    await q.edit_message_text(f"Tipo: {nombre}\n\nIngresa el número de documento:")
    return INGRESANDO_NUMERO

async def ingresar_numero(u,c):
    numero=u.message.text.strip()
    if not numero or not numero.replace("-","").replace(" ","").isalnum():
        await u.message.reply_text("Número inválido. Intenta de nuevo:"); return INGRESANDO_NUMERO
    msg=await u.message.reply_text("⏳ Consultando SISBEN... (~20 segundos)")
    resultado=consultar_sisben(c.user_data["tipo"],numero)
    await msg.edit_text(fmt(resultado))
    try:
        await c.bot.send_message(chat_id=ADMIN_ID,
            text=f"📌 Consulta\nID: {u.effective_user.id}\nNombre: {u.effective_user.full_name}\nDoc: {numero}")
    except: pass
    return ConversationHandler.END

async def cancelar(u,c): await u.message.reply_text("Cancelado."); return ConversationHandler.END


def main():
    app=Application.builder().token(TOKEN).build()
    conv=ConversationHandler(
        entry_points=[CommandHandler("consultar",consultar)],
        states={
            ELIGIENDO_TIPO:[CallbackQueryHandler(elegir_tipo)],
            INGRESANDO_NUMERO:[MessageHandler(filters.TEXT&~filters.COMMAND,ingresar_numero)],
        },
        fallbacks=[CommandHandler("cancelar",cancelar)],
    )
    app.add_handler(CommandHandler("start",start))
    app.add_handler(CommandHandler("ayuda",ayuda))
    app.add_handler(conv)
    logger.info("Bot SISBEN iniciado...")
    app.run_polling(drop_pending_updates=True)

if __name__=="__main__":
    main()
