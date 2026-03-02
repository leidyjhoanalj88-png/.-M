#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
==============================================================================
                    CONSULTA SISBEN - BOT DE TELEGRAM
                    + Soporte Base de Datos ANI
==============================================================================
Version: 2.0
==============================================================================
"""

import logging
import time
import os
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    ConversationHandler,
)
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import TimeoutException

# ── Configuracion ─────────────────────────────────────────────────────────────
TOKEN    = "8574051542:AAH_N4RBST0wCpkLKDOFNEc1R93vePWxEPY"
ADMIN_ID = 8114050673

# ── Configuracion Base de Datos ANI (llenar cuando tengas acceso) ─────────────
DB_HOST     = "TU_IP_SERVIDOR"   # Ej: "192.168.1.100"
DB_PORT     = 3306
DB_USER     = "root"
DB_PASSWORD = "TU_CONTRASENA"
DB_NAME     = "ani"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Estados conversacion
ELIGIENDO_TIPO, INGRESANDO_NUMERO, CONFIRMANDO = range(3)

TIPOS_DOCUMENTO = {
    "1️⃣ Registro Civil":               "1",
    "2️⃣ Tarjeta de Identidad":         "2",
    "3️⃣ Cedula de Ciudadania":         "3",
    "4️⃣ Cedula de Extranjeria":        "4",
    "5️⃣ DNI (Pais de origen)":         "5",
    "6️⃣ DNI (Pasaporte)":              "6",
    "7️⃣ Salvoconducto Refugiado":      "7",
    "8️⃣ Permiso Especial Permanencia": "8",
    "9️⃣ Permiso Proteccion Temporal":  "9",
}

URL_PAGINA = "https://www.sisben.gov.co/Paginas/consulta-tu-grupo.html"


# ── Base de Datos ANI ─────────────────────────────────────────────────────────
def consultar_bd_ani(numero_documento):
    """
    Consulta datos adicionales del ciudadano en la BD ANI.
    Retorna dict con datos o None si no hay conexion.
    """
    try:
        import pymysql
        conn = pymysql.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=DB_PASSWORD,
            database=DB_NAME,
            connect_timeout=5
        )
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        cursor.execute("""
            SELECT
                ANINombresExtenso    AS nombre,
                ANIFchNacimiento     AS fecha_nacimiento,
                ANISexo              AS sexo,
                ANIEstatura          AS estatura,
                ANIFchExpedicion     AS fecha_expedicion,
                ANIDireccion         AS direccion
            FROM ani
            WHERE ANINuip = %s
            LIMIT 1
        """, (numero_documento,))
        fila = cursor.fetchone()
        cursor.close()
        conn.close()
        return fila
    except Exception as e:
        logger.warning(f"BD ANI no disponible: {e}")
        return None


# ── Selenium ──────────────────────────────────────────────────────────────────
def configurar_navegador():
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--log-level=3")
    chrome_options.add_argument("--silent")
    chrome_options.add_argument("--disable-logging")
    chrome_options.add_experimental_option("excludeSwitches", ["enable-logging", "enable-automation"])
    chrome_options.add_experimental_option("useAutomationExtension", False)
    try:
        from webdriver_manager.chrome import ChromeDriverManager
        driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=chrome_options
        )
    except Exception:
        driver = webdriver.Chrome(options=chrome_options)
    return driver


def realizar_consulta_sisben(tipo_documento, numero_documento):
    driver = configurar_navegador()
    resultado = {}
    try:
        driver.get(URL_PAGINA)
        time.sleep(8)

        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        for iframe in iframes:
            try:
                driver.switch_to.frame(iframe)
                if driver.find_elements(By.ID, "TipoID"):
                    break
                driver.switch_to.default_content()
            except Exception:
                driver.switch_to.default_content()

        wait = WebDriverWait(driver, 20)
        try:
            select_elem = wait.until(EC.presence_of_element_located((By.ID, "TipoID")))
        except Exception:
            select_elem = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "select[name='TipoID']")))

        Select(select_elem).select_by_value(tipo_documento)
        time.sleep(1)

        input_doc = driver.find_element(By.ID, "documento")
        input_doc.clear()
        input_doc.send_keys(numero_documento)
        time.sleep(1)

        boton = driver.find_element(By.ID, "botonenvio")
        driver.execute_script("arguments[0].click();", boton)
        time.sleep(8)

        html = driver.page_source
        if "no se encontr" in html.lower():
            return None

        try:
            grupo = driver.find_element(By.XPATH,
                "//p[contains(@class, 'text-uppercase') and contains(@class, 'text-white')]")
            resultado["grupo"] = grupo.text.strip()
        except Exception:
            pass

        try:
            clasif = driver.find_element(By.XPATH,
                "//div[contains(@class, 'imagenpuntaje')]//p[contains(@style, '18px')]")
            resultado["clasificacion"] = clasif.text.strip()
        except Exception:
            pass

        campos = {
            "Fecha de consulta":   "fecha",
            "Ficha":               "ficha",
            "Nombres":             "nombres",
            "Apellidos":           "apellidos",
            "Tipo de documento":   "tipo_doc",
            "Número de documento": "num_doc",
            "Municipio":           "municipio",
            "Departamento":        "departamento",
            "Encuesta vigente":    "encuesta",
            "Nombre administrador":"admin",
            "Dirección":           "direccion",
            "Teléfono":            "telefono",
            "Correo":              "correo",
        }

        for texto, key in campos.items():
            try:
                elem = driver.find_element(By.XPATH,
                    f"//p[contains(text(), '{texto}')]/following-sibling::p")
                valor = elem.text.strip()
                if valor:
                    resultado[key] = " ".join(valor.split())
            except Exception:
                pass

    except Exception as e:
        logger.error(f"Error Selenium: {e}")
        resultado["error"] = str(e)
    finally:
        driver.quit()

    return resultado


# ── Formatear resultado ───────────────────────────────────────────────────────
def formatear_resultado(sisben, ani):
    if not sisben:
        return (
            "❌ *NO SE ENCONTRARON RESULTADOS*\n\n"
            "El documento NO está en el SISBEN IV\n"
            "o los datos ingresados son incorrectos."
        )

    if "error" in sisben:
        return f"⚠️ *Error al consultar:*\n`{sisben['error']}`"

    msg = "✅ *RESULTADO DE LA CONSULTA SISBEN IV*\n"
    msg += "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

    if "grupo" in sisben:
        msg += f"🏷️ *GRUPO SISBEN:* `{sisben['grupo']}`\n"
        if "clasificacion" in sisben:
            msg += f"📊 *Clasificacion:* `{sisben['clasificacion']}`\n"
        msg += "\n"

    msg += "👤 *DATOS PERSONALES*\n"
    msg += "━━━━━━━━━━━━━━━━━━━━━━━━\n"
    if "nombres"      in sisben: msg += f"• Nombres: `{sisben['nombres']}`\n"
    if "apellidos"    in sisben: msg += f"• Apellidos: `{sisben['apellidos']}`\n"
    if "tipo_doc"     in sisben: msg += f"• Tipo Doc: `{sisben['tipo_doc']}`\n"
    if "num_doc"      in sisben: msg += f"• Numero: `{sisben['num_doc']}`\n"
    if "municipio"    in sisben: msg += f"• Municipio: `{sisben['municipio']}`\n"
    if "departamento" in sisben: msg += f"• Departamento: `{sisben['departamento']}`\n"

    # Datos extra BD ANI
    if ani:
        msg += "\n📁 *DATOS ADICIONALES (ANI)*\n"
        msg += "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        if ani.get("fecha_nacimiento"): msg += f"• Fecha Nacimiento: `{ani['fecha_nacimiento']}`\n"
        if ani.get("sexo"):             msg += f"• Sexo: `{ani['sexo']}`\n"
        if ani.get("estatura"):         msg += f"• Estatura: `{ani['estatura']} cm`\n"
        if ani.get("fecha_expedicion"): msg += f"• Fecha Expedicion: `{ani['fecha_expedicion']}`\n"
        if ani.get("direccion"):        msg += f"• Dirección: `{ani['direccion']}`\n"

    if any(k in sisben for k in ["ficha", "fecha", "encuesta"]):
        msg += "\n📋 *INFORMACION DEL REGISTRO*\n"
        msg += "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        if "ficha"    in sisben: msg += f"• Ficha: `{sisben['ficha']}`\n"
        if "fecha"    in sisben: msg += f"• Fecha Consulta: `{sisben['fecha']}`\n"
        if "encuesta" in sisben: msg += f"• Encuesta Vigente: `{sisben['encuesta']}`\n"

    if any(k in sisben for k in ["admin", "telefono", "correo"]):
        msg += "\n📞 *CONTACTO OFICINA SISBEN*\n"
        msg += "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        if "admin"    in sisben: msg += f"• Admin: `{sisben['admin']}`\n"
        if "telefono" in sisben: msg += f"• Teléfono: `{sisben['telefono']}`\n"
        if "correo"   in sisben: msg += f"• Correo: `{sisben['correo']}`\n"

    return msg


# ── Handlers Telegram ─────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *Bienvenido al Bot de Consulta SISBEN IV*\n\n"
        "🇨🇴 Republica de Colombia\n"
        "🏛️ Departamento Nacional de Planeacion - DNP\n\n"
        "Usa /consultar para iniciar.\n"
        "Usa /cancelar para cancelar.",
        parse_mode="Markdown"
    )


async def consultar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    teclado = [[t] for t in TIPOS_DOCUMENTO.keys()]
    await update.message.reply_text(
        "📋 *Selecciona el tipo de documento:*",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(teclado, one_time_keyboard=True, resize_keyboard=True)
    )
    return ELIGIENDO_TIPO


async def elegir_tipo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text
    if texto not in TIPOS_DOCUMENTO:
        await update.message.reply_text("❌ Opción inválida. Selecciona una del menú.")
        return ELIGIENDO_TIPO

    context.user_data["tipo_doc"]    = TIPOS_DOCUMENTO[texto]
    context.user_data["tipo_nombre"] = texto

    await update.message.reply_text(
        f"✅ Seleccionado: *{texto}*\n\n🔢 Ingresa el *número de documento:*",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove()
    )
    return INGRESANDO_NUMERO


async def ingresar_numero(update: Update, context: ContextTypes.DEFAULT_TYPE):
    numero = update.message.text.strip()
    if not numero or not numero.replace("-", "").replace(" ", "").isalnum():
        await update.message.reply_text("❌ Número inválido. Intenta de nuevo:")
        return INGRESANDO_NUMERO

    context.user_data["num_doc"] = numero
    teclado = [["✅ Si, consultar", "❌ Cancelar"]]
    await update.message.reply_text(
        f"🔍 *Confirmar consulta:*\n\n"
        f"• Tipo: `{context.user_data['tipo_nombre']}`\n"
        f"• Número: `{numero}`\n\n¿Deseas continuar?",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(teclado, one_time_keyboard=True, resize_keyboard=True)
    )
    return CONFIRMANDO


async def confirmar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "Cancelar" in update.message.text:
        await update.message.reply_text("❌ Consulta cancelada.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    await update.message.reply_text(
        "⏳ *Consultando...*\n\nEspera un momento por favor.",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove()
    )

    tipo   = context.user_data["tipo_doc"]
    numero = context.user_data["num_doc"]

    sisben = realizar_consulta_sisben(tipo, numero)
    ani    = consultar_bd_ani(numero)

    mensaje = formatear_resultado(sisben, ani)
    await update.message.reply_text(mensaje, parse_mode="Markdown")

    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"📊 *Nueva consulta*\n"
                 f"• Usuario: `{update.effective_user.id}`\n"
                 f"• Nombre: {update.effective_user.full_name}\n"
                 f"• Documento: `{numero}`",
            parse_mode="Markdown"
        )
    except Exception:
        pass

    return ConversationHandler.END


async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "❌ Cancelado. Usa /consultar para una nueva consulta.",
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END


async def ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ℹ️ *Comandos disponibles:*\n\n"
        "/start - Iniciar el bot\n"
        "/consultar - Hacer una consulta SISBEN\n"
        "/cancelar - Cancelar consulta actual\n"
        "/ayuda - Ver esta ayuda",
        parse_mode="Markdown"
    )


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    app = Application.builder().token(TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("consultar", consultar)],
        states={
            ELIGIENDO_TIPO:    [MessageHandler(filters.TEXT & ~filters.COMMAND, elegir_tipo)],
            INGRESANDO_NUMERO: [MessageHandler(filters.TEXT & ~filters.COMMAND, ingresar_numero)],
            CONFIRMANDO:       [MessageHandler(filters.TEXT & ~filters.COMMAND, confirmar)],
        },
        fallbacks=[CommandHandler("cancelar", cancelar)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ayuda", ayuda))
    app.add_handler(conv)

    print("🤖 Bot SISBEN v2.0 iniciado...")
    app.run_polling()


if __name__ == "__main__":
    main()
