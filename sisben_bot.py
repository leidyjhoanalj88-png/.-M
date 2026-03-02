#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
==============================================================================
                    CONSULTA SISBEN - BOT DE TELEGRAM v4.0
                    URL corregida: reportes.sisben.gov.co
==============================================================================
"""

import logging
import requests
from bs4 import BeautifulSoup
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)

# ── Configuracion ─────────────────────────────────────────────────────────────
TOKEN    = "8574051542:AAH_N4RBST0wCpkLKDOFNEc1R93vePWxEPY"
ADMIN_ID = 8114050673

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Estados
ELIGIENDO_TIPO, INGRESANDO_NUMERO = range(2)

TIPOS_DOCUMENTO = [
    ("📄 Registro Civil",           "1"),
    ("🪪 Tarjeta de Identidad",     "2"),
    ("🆔 Cédula de Ciudadanía",     "3"),
    ("🌐 Cédula de Extranjería",    "4"),
    ("📋 DNI País de Origen",       "5"),
    ("📘 DNI Pasaporte",            "6"),
    ("🛡️ Salvoconducto Refugiado",  "7"),
    ("📝 Permiso Esp. Permanencia", "8"),
    ("🔖 Permiso Protec. Temporal", "9"),
]

# URLs correctas
URL_BASE     = "https://reportes.sisben.gov.co/dnp_sisbenconsulta"
URL_PAGINA   = "https://portal-sisben.sisben.gov.co/Paginas/consulta-tu-grupo.html"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "es-CO,es;q=0.9",
    "Content-Type": "application/x-www-form-urlencoded",
    "Referer": URL_PAGINA,
    "Origin": "https://reportes.sisben.gov.co",
}


# ── Consulta rápida ───────────────────────────────────────────────────────────
def consultar_sisben(tipo_doc, numero_doc):
    try:
        session = requests.Session()
        session.headers.update(HEADERS)

        # Obtener cookies
        session.get(URL_PAGINA, timeout=10)

        # Hacer consulta
        data = {
            "TipoID":     tipo_doc,
            "documento":  numero_doc,
        }

        resp = session.post(URL_BASE, data=data, timeout=15)
        resp.raise_for_status()

        html = resp.text

        if "no se encontr" in html.lower() or "no encontrado" in html.lower():
            return None

        soup = BeautifulSoup(html, "html.parser")
        resultado = {}

        # Grupo SISBEN
        grupo = soup.find("p", class_=lambda c: c and "text-uppercase" in c and "text-white" in c)
        if grupo:
            resultado["grupo"] = grupo.get_text(strip=True)

        # Puntaje/Clasificacion
        div_puntaje = soup.find("div", class_=lambda c: c and "imagenpuntaje" in c)
        if div_puntaje:
            p = div_puntaje.find("p", style=lambda s: s and "18px" in s)
            if p:
                resultado["clasificacion"] = p.get_text(strip=True)

        # Campos de datos
        campos = {
            "Fecha de consulta":    "fecha",
            "Ficha":                "ficha",
            "Nombres":              "nombres",
            "Apellidos":            "apellidos",
            "Tipo de documento":    "tipo_doc",
            "Número de documento":  "num_doc",
            "Municipio":            "municipio",
            "Departamento":         "departamento",
            "Encuesta vigente":     "encuesta",
            "Nombre administrador": "admin",
            "Dirección":            "direccion",
            "Teléfono":             "telefono",
            "Correo":               "correo",
        }

        parrafos = soup.find_all("p")
        for i, p in enumerate(parrafos):
            texto = p.get_text(strip=True)
            for campo, key in campos.items():
                if campo in texto and i + 1 < len(parrafos):
                    valor = parrafos[i + 1].get_text(strip=True)
                    if valor and valor != texto:
                        resultado[key] = " ".join(valor.split())

        return resultado if resultado else None

    except Exception as e:
        logger.error(f"Error consulta: {e}")
        return {"error": str(e)}


def formatear_resultado(r):
    if not r:
        return (
            "❌ *NO ENCONTRADO*\n\n"
            "Este documento no está en el SISBEN IV\n"
            "o los datos son incorrectos."
        )

    if "error" in r:
        return f"⚠️ *Error:*\n`{r['error']}`"

    msg = "✅ *RESULTADO SISBEN IV*\n"
    msg += "━━━━━━━━━━━━━━━━━━━━\n\n"

    if "grupo" in r:
        msg += f"🏷 *GRUPO:* `{r['grupo']}`\n"
    if "clasificacion" in r:
        msg += f"📊 *Puntaje:* `{r['clasificacion']}`\n"

    msg += "\n👤 *DATOS PERSONALES*\n"
    msg += "━━━━━━━━━━━━━━━━━━━━\n"
    if "nombres"      in r: msg += f"• Nombres: `{r['nombres']}`\n"
    if "apellidos"    in r: msg += f"• Apellidos: `{r['apellidos']}`\n"
    if "num_doc"      in r: msg += f"• Documento: `{r['num_doc']}`\n"
    if "municipio"    in r: msg += f"• Municipio: `{r['municipio']}`\n"
    if "departamento" in r: msg += f"• Dpto: `{r['departamento']}`\n"

    if any(k in r for k in ["ficha", "fecha", "encuesta"]):
        msg += "\n📋 *REGISTRO*\n"
        msg += "━━━━━━━━━━━━━━━━━━━━\n"
        if "ficha"    in r: msg += f"• Ficha: `{r['ficha']}`\n"
        if "fecha"    in r: msg += f"• Fecha: `{r['fecha']}`\n"
        if "encuesta" in r: msg += f"• Encuesta: `{r['encuesta']}`\n"

    if any(k in r for k in ["admin", "telefono", "correo"]):
        msg += "\n📞 *OFICINA SISBEN*\n"
        msg += "━━━━━━━━━━━━━━━━━━━━\n"
        if "admin"    in r: msg += f"• Admin: `{r['admin']}`\n"
        if "telefono" in r: msg += f"• Tel: `{r['telefono']}`\n"
        if "correo"   in r: msg += f"• Correo: `{r['correo']}`\n"

    return msg


# ── Teclado inline ────────────────────────────────────────────────────────────
def teclado_tipos():
    botones = []
    fila = []
    for i, (nombre, valor) in enumerate(TIPOS_DOCUMENTO):
        fila.append(InlineKeyboardButton(nombre, callback_data=f"tipo_{valor}"))
        if len(fila) == 2:
            botones.append(fila)
            fila = []
    if fila:
        botones.append(fila)
    botones.append([InlineKeyboardButton("❌ Cancelar", callback_data="cancelar")])
    return InlineKeyboardMarkup(botones)


# ── Handlers ──────────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *Bot Consulta SISBEN IV*\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "🇨🇴 DNP — República de Colombia\n\n"
        "📌 *Comandos:*\n"
        "• /consultar — Consultar SISBEN\n"
        "• /ayuda — Ver ayuda\n"
        "• /cancelar — Cancelar consulta",
        parse_mode="Markdown"
    )


async def consultar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📋 *Selecciona el tipo de documento:*",
        parse_mode="Markdown",
        reply_markup=teclado_tipos()
    )
    return ELIGIENDO_TIPO


async def elegir_tipo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "cancelar":
        await query.edit_message_text("❌ Consulta cancelada.")
        return ConversationHandler.END

    valor  = query.data.replace("tipo_", "")
    nombre = next((n for n, v in TIPOS_DOCUMENTO if v == valor), valor)

    context.user_data["tipo_doc"]    = valor
    context.user_data["tipo_nombre"] = nombre

    await query.edit_message_text(
        f"✅ *{nombre}*\n\n🔢 Ingresa el número de documento:",
        parse_mode="Markdown"
    )
    return INGRESANDO_NUMERO


async def ingresar_numero(update: Update, context: ContextTypes.DEFAULT_TYPE):
    numero = update.message.text.strip()

    if not numero or not numero.replace("-", "").replace(" ", "").isalnum():
        await update.message.reply_text("❌ Número inválido. Intenta de nuevo:")
        return INGRESANDO_NUMERO

    msg = await update.message.reply_text("⏳ *Consultando SISBEN...*", parse_mode="Markdown")

    tipo      = context.user_data["tipo_doc"]
    resultado = consultar_sisben(tipo, numero)
    mensaje   = formatear_resultado(resultado)

    await msg.edit_text(mensaje, parse_mode="Markdown")

    # Notificar admin
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"📊 *Nueva consulta*\n"
                 f"• Usuario: `{update.effective_user.id}`\n"
                 f"• Nombre: {update.effective_user.full_name}\n"
                 f"• Doc: `{numero}`",
            parse_mode="Markdown"
        )
    except Exception:
        pass

    return ConversationHandler.END


async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Cancelado. Usa /consultar para una nueva consulta.")
    return ConversationHandler.END


async def ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ℹ️ *Ayuda — Bot SISBEN IV*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "• /consultar — Iniciar consulta\n"
        "• /cancelar — Cancelar\n"
        "• /ayuda — Esta ayuda\n\n"
        "💡 La consulta tarda solo unos segundos.",
        parse_mode="Markdown"
    )


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    app = Application.builder().token(TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("consultar", consultar)],
        states={
            ELIGIENDO_TIPO:    [CallbackQueryHandler(elegir_tipo)],
            INGRESANDO_NUMERO: [MessageHandler(filters.TEXT & ~filters.COMMAND, ingresar_numero)],
        },
        fallbacks=[CommandHandler("cancelar", cancelar)],
    )

    app.add_handler(CommandHandler("start",   start))
    app.add_handler(CommandHandler("ayuda",   ayuda))
    app.add_handler(conv)

    print("🤖 Bot SISBEN v4.0 iniciado...")
    app.run_polling()


if __name__ == "__main__":
    main()
