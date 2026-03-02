#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging, time, os, requests
from bs4 import BeautifulSoup
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler,
)

TOKEN    = "8574051542:AAH_N4RBST0wCpkLKDOFNEc1R93vePWxEPY"
ADMIN_ID = 8114050673
URL_PAGINA = "https://www.sisben.gov.co/Paginas/consulta-tu-grupo.html"
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

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-CO,es;q=0.9,en;q=0.8",
    "Referer": URL_PAGINA,
}

def consultar_sisben(tipo, numero):
    try:
        session = requests.Session()
        session.headers.update(HEADERS)

        # Primero cargamos la página para obtener tokens/cookies
        r = session.get(URL_PAGINA, timeout=30)
        r.raise_for_status()

        soup = BeautifulSoup(r.text, "html.parser")

        # Buscar el iframe con el formulario
        iframe = soup.find("iframe")
        iframe_url = None
        if iframe:
            src = iframe.get("src","")
            if src.startswith("http"):
                iframe_url = src
            elif src:
                iframe_url = "https://www.sisben.gov.co" + src

        # Si hay iframe, cargarlo
        if iframe_url:
            r2 = session.get(iframe_url, timeout=30)
            soup = BeautifulSoup(r2.text, "html.parser")

        # Buscar campos ocultos del formulario
        form = soup.find("form")
        data = {}
        if form:
            for inp in form.find_all("input", {"type": ["hidden"]}):
                name = inp.get("name")
                val  = inp.get("value","")
                if name:
                    data[name] = val

        # Datos principales del formulario
        data["TipoID"]   = tipo
        data["documento"] = numero

        # Determinar URL de envío
        action = None
        if form:
            action = form.get("action","")
        if not action:
            action = iframe_url or URL_PAGINA
        elif not action.startswith("http"):
            action = "https://www.sisben.gov.co" + action

        # Enviar formulario
        resp = session.post(action, data=data, timeout=30)
        resp.raise_for_status()

        result_soup = BeautifulSoup(resp.text, "html.parser")
        html = resp.text.lower()

        if "no se encontr" in html or "no registra" in html:
            return None

        r = {}

        # Extraer grupo
        grupo_tag = result_soup.find(lambda t: t.name=="p" and "text-uppercase" in t.get("class",[]) and "text-white" in t.get("class",[]))
        if grupo_tag:
            r["grupo"] = grupo_tag.text.strip()

        # Extraer puntaje/clasificación
        puntaje = result_soup.find(lambda t: t.name=="p" and t.get("style","") and "18px" in t.get("style",""))
        if puntaje:
            r["clasificacion"] = puntaje.text.strip()

        # Extraer campos por etiqueta
        for label, key in [
            ("Nombres","nombres"),("Apellidos","apellidos"),
            ("Municipio","municipio"),("Departamento","departamento"),
            ("Ficha","ficha"),("Fecha de consulta","fecha"),
            ("Encuesta vigente","encuesta"),
        ]:
            tag = result_soup.find(lambda t, l=label: t.name=="p" and l in t.text)
            if tag:
                sib = tag.find_next_sibling("p")
                if sib and sib.text.strip():
                    r[key] = " ".join(sib.text.strip().split())

        return r if r else None

    except requests.exceptions.Timeout:
        return {"error": "Tiempo de espera agotado"}
    except requests.exceptions.RequestException as e:
        return {"error": f"Error de conexión: {str(e)}"}
    except Exception as e:
        return {"error": str(e)}


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


async def start(u,c): await u.message.reply_text("🤖 Bot SISBEN IV\n/consultar - Consultar\n/ayuda - Ayuda")
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
    msg=await u.message.reply_text("⏳ Consultando SISBEN... (~10 segundos)")
    resultado=consultar_sisben(c.user_data["tipo"],numero)
    await msg.edit_text(fmt(resultado))
    try:
        await c.bot.send_message(chat_id=ADMIN_ID,
            text=f"📌 Consulta\nID: {u.effective_user.id}\nNombre: {u.effective_user.full_name}\nDoc: {numero}")
    except Exception: pass
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
    print("Bot SISBEN v6.0 (sin Selenium) iniciado...")
    app.run_polling()

if __name__=="__main__": main()
