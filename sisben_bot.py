#!/usr/bin/env python
# -*- coding: utf-8 -*-
import logging, time, os
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

TOKEN    = "8574051542:AAH_N4RBST0wCpkLKDOFNEc1R93vePWxEPY"
ADMIN_ID = 8114050673
ELIGIENDO_TIPO, INGRESANDO_NUMERO = range(2)
URL = "https://www.sisben.gov.co/Paginas/consulta-tu-grupo.html"

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

TIPOS = [
    ("📄 Registro Civil","1"),("🪪 Tarjeta de Identidad","2"),
    ("🆔 Cédula de Ciudadanía","3"),("🌐 Cédula de Extranjería","4"),
    ("📋 DNI País de Origen","5"),("📘 DNI Pasaporte","6"),
    ("🛡️ Salvoconducto Refugiado","7"),("📝 Permiso Esp. Permanencia","8"),
    ("🔖 Permiso Protec. Temporal","9"),
]

def get_driver():
    opts = Options()
    for a in ["--headless=new","--no-sandbox","--disable-dev-shm-usage",
              "--disable-gpu","--disable-extensions",
              "--blink-settings=imagesEnabled=false",
              "--window-size=1280,720","--log-level=3"]:
        opts.add_argument(a)
    opts.add_experimental_option("excludeSwitches",["enable-logging","enable-automation"])
    opts.add_experimental_option("useAutomationExtension",False)
    chrome_bin = None
    for path in ["/usr/bin/chromium","/usr/bin/chromium-browser",
                 "/usr/bin/google-chrome","/usr/bin/chrome"]:
        if os.path.exists(path):
            chrome_bin = path
            break
    if not chrome_bin and os.path.exists("/nix/store"):
        for root, dirs, files in os.walk("/nix/store"):
            for f in files:
                if f in ("chromium","chrome","chromium-browser"):
                    chrome_bin = os.path.join(root,f); break
            if chrome_bin: break
    if chrome_bin:
        opts.binary_location = chrome_bin
    for drv in ["/usr/bin/chromedriver","/usr/local/bin/chromedriver"]:
        if os.path.exists(drv):
            return webdriver.Chrome(service=Service(drv),options=opts)
    try:
        from webdriver_manager.chrome import ChromeDriverManager
        return webdriver.Chrome(service=Service(ChromeDriverManager().install()),options=opts)
    except:
        return webdriver.Chrome(options=opts)

def consultar_sisben(tipo, numero):
    driver = None
    try:
        driver = get_driver()
        driver.set_page_load_timeout(30)
        driver.get(URL)
        time.sleep(5)
        iframes = driver.find_elements(By.TAG_NAME,"iframe")
        ok = False
        for f in iframes:
            try:
                driver.switch_to.frame(f)
                if driver.find_elements(By.ID,"TipoID"): ok=True; break
                driver.switch_to.default_content()
            except: driver.switch_to.default_content()
        if not ok and not driver.find_elements(By.ID,"TipoID"):
            return {"error":"Formulario no encontrado"}
        wait = WebDriverWait(driver,15)
        Select(wait.until(EC.presence_of_element_located((By.ID,"TipoID")))).select_by_value(tipo)
        time.sleep(0.5)
        inp = driver.find_element(By.ID,"documento"); inp.clear(); inp.send_keys(numero)
        time.sleep(0.5)
        driver.execute_script("arguments[0].click();",driver.find_element(By.ID,"botonenvio"))
        time.sleep(6)
        html = driver.page_source
        if "no se encontr" in html.lower(): return None
        r = {}
        try: r["grupo"]=driver.find_element(By.XPATH,"//p[contains(@class,'text-uppercase') and contains(@class,'text-white')]").text.strip()
        except: pass
        try: r["clasificacion"]=driver.find_element(By.XPATH,"//div[contains(@class,'imagenpuntaje')]//p[contains(@style,'18px')]").text.strip()
        except: pass
        for label,key in {"Nombres":"nombres","Apellidos":"apellidos","Número de documento":"num_doc","Municipio":"municipio","Departamento":"departamento","Ficha":"ficha","Fecha de consulta":"fecha","Encuesta vigente":"encuesta","Nombre administrador":"admin","Dirección":"direccion","Teléfono":"telefono","Correo":"correo"}.items():
            try:
                v=driver.find_element(By.XPATH,f"//p[contains(text(),'{label}')]/following-sibling::p[1]").text.strip()
                if v: r[key]=" ".join(v.split())
            except: pass
        return r if r else None
    except Exception as e:
        logger.error(f"Error: {e}"); return {"error":str(e)}
    finally:
        if driver:
            try: driver.quit()
            except: pass

def fmt(r):
    if not r: return "❌ *NO ENCONTRADO*\n\nDocumento no registrado en SISBEN IV."
    if "error" in r: return f"⚠️ *Error:*\n`{r['error']}`"
    m = "✅ *RESULTADO SISBEN IV*\n━━━━━━━━━━━━━━━━━━━━\n\n"
    if "grupo" in r: m+=f"🏷 *GRUPO:* `{r['grupo']}`\n"
    if "clasificacion" in r: m+=f"📊 *Puntaje:* `{r['clasificacion']}`\n"
    m+="\n👤 *DATOS*\n━━━━━━━━━━━━━━━━━━━━\n"
    for k,l in [("nombres","Nombres"),("apellidos","Apellidos"),("num_doc","Doc"),("municipio","Municipio"),("departamento","Dpto")]:
        if k in r: m+=f"• {l}: `{r[k]}`\n"
    if any(k in r for k in ["ficha","fecha","encuesta"]):
        m+="\n📋 *REGISTRO*\n━━━━━━━━━━━━━━━━━━━━\n"
        for k,l in [("ficha","Ficha"),("fecha","Fecha"),("encuesta","Encuesta")]:
            if k in r: m+=f"• {l}: `{r[k]}`\n"
    if any(k in r for k in ["admin","telefono","correo"]):
        m+="\n📞 *OFICINA*\n━━━━━━━━━━━━━━━━━━━━\n"
        for k,l in [("admin","Admin"),("telefono","Tel"),("correo","Correo")]:
            if k in r: m+=f"• {l}: `{r[k]}`\n"
    return m

def menu():
    b,f=[],[]
    for n,v in TIPOS:
        f.append(InlineKeyboardButton(n,callback_data=f"t_{v}"))
        if len(f)==2: b.append(f); f=[]
    if f: b.append(f)
    b.append([InlineKeyboardButton("❌ Cancelar",callback_data="cancelar")])
    return InlineKeyboardMarkup(b)

async def start(u,c): await u.message.reply_text("👋 *Bot Consulta SISBEN IV*\n━━━━━━━━━━━━━━━━━━━━\n🇨🇴 DNP — República de Colombia\n\n• /consultar\n• /ayuda",parse_mode="Markdown")
async def consultar(u,c):
    await u.message.reply_text("📋 *Tipo de documento:*",parse_mode="Markdown",reply_markup=menu())
    return ELIGIENDO_TIPO
async def elegir_tipo(u,c):
    q=u.callback_query; await q.answer()
    if q.data=="cancelar": await q.edit_message_text("❌ Cancelado."); return ConversationHandler.END
    v=q.data.replace("t_",""); n=next((x for x,y in TIPOS if y==v),v)
    c.user_data["tipo"]=v
    await q.edit_message_text(f"✅ *{n}*\n\n🔢 Número de documento:",parse_mode="Markdown")
    return INGRESANDO_NUMERO
async def ingresar_numero(u,c):
    num=u.message.text.strip()
    if not num or not num.replace("-","").replace(" ","").isalnum():
        await u.message.reply_text("❌ Número inválido. Intenta de nuevo:"); return INGRESANDO_NUMERO
    msg=await u.message.reply_text("⏳ *Consultando...*\n_~15 segundos_",parse_mode="Markdown")
    r=consultar_sisben(c.user_data["tipo"],num)
    await msg.edit_text(fmt(r),parse_mode="Markdown")
    try: await c.bot.send_message(chat_id=ADMIN_ID,text=f"📊 *Consulta*\n• ID: `{u.effective_user.id}`\n• Nombre: {u.effective_user.full_name}\n• Doc: `{num}`",parse_mode="Markdown")
    except: pass
    return ConversationHandler.END
async def cancelar(u,c): await u.message.reply_text("❌ Cancelado."); return ConversationHandler.END
async def ayuda(u,c): await u.message.reply_text("ℹ️ /consultar /cancelar /ayuda",parse_mode="Markdown")

def main():
    app=Application.builder().token(TOKEN).build()
    conv=ConversationHandler(
        entry_points=[CommandHandler("consultar",consultar)],
        states={ELIGIENDO_TIPO:[CallbackQueryHandler(elegir_tipo)],INGRESANDO_NUMERO:[MessageHandler(filters.TEXT&~filters.COMMAND,ingresar_numero)]},
        fallbacks=[CommandHandler("cancelar",cancelar)],
    )
    app.add_handler(CommandHandler("start",start))
    app.add_handler(CommandHandler("ayuda",ayuda))
    app.add_handler(conv)
    print("🤖 Bot SISBEN v5.0"); app.run_polling()

if __name__=="__main__": main()