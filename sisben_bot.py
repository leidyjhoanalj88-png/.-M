#!/usr/bin/env python
# -*- coding: utf-8 -*-

import logging, time, os, glob, asyncio, json
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

# ══════════════════════════════════════════════════════════
#  CONFIG
# ══════════════════════════════════════════════════════════
TOKEN      = os.environ.get("BOT_TOKEN", "8574051542:AAH_N4RBST0wCpkLKDOFNEc1R93vePWxEPY")
OWNER_ID   = 8114050673          # ← Super admin fijo, NUNCA se puede eliminar
DB_FILE    = "database.json"
URL_PAGINA = "https://reportes.sisben.gov.co/DNP_SisbenConsulta"

# Estados de conversación
(ELIGIENDO_TIPO, INGRESANDO_NUMERO,
 ESPERANDO_ID_ADMIN, ESPERANDO_ID_USUARIO) = range(4)

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

TIPOS = [
    ("Registro Civil","1"),     ("Tarjeta de Identidad","2"),
    ("Cedula de Ciudadania","3"),("Cedula de Extranjeria","4"),
    ("DNI Pais de Origen","5"), ("DNI Pasaporte","6"),
    ("Salvoconducto Refugiado","7"),("Permiso Esp. Permanencia","8"),
    ("Permiso Protec. Temporal","9"),
]

# ══════════════════════════════════════════════════════════
#  BASE DE DATOS  (admins + usuarios)
# ══════════════════════════════════════════════════════════
def cargar_db() -> dict:
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE) as f:
                return json.load(f)
        except:
            pass
    db = {"admins": [OWNER_ID], "usuarios": [], "consultas": 0}
    guardar_db(db)
    return db

def guardar_db(db: dict):
    with open(DB_FILE, "w") as f:
        json.dump(db, f, indent=2)

def es_owner(uid: int) -> bool:
    return uid == OWNER_ID

def es_admin(uid: int) -> bool:
    db = cargar_db()
    return uid == OWNER_ID or uid in db["admins"]

def es_usuario(uid: int) -> bool:
    """Usuarios autorizados para usar /consultar."""
    db = cargar_db()
    return uid == OWNER_ID or uid in db["admins"] or uid in db["usuarios"]

# ══════════════════════════════════════════════════════════
#  SELENIUM
# ══════════════════════════════════════════════════════════
def get_driver():
    opts = Options()
    for arg in ["--headless=new","--no-sandbox","--disable-dev-shm-usage",
                "--disable-gpu","--disable-extensions",
                "--blink-settings=imagesEnabled=false",
                "--window-size=1920,1080","--log-level=3"]:
        opts.add_argument(arg)
    opts.add_experimental_option("excludeSwitches", ["enable-logging","enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)

    chrome_bin = os.environ.get("CHROME_BIN")
    if not chrome_bin:
        for p in ["/usr/bin/chromium","/usr/bin/chromium-browser",
                  "/usr/bin/google-chrome","/usr/bin/chrome"]:
            if os.path.exists(p): chrome_bin = p; break
    if not chrome_bin:
        r = glob.glob("/nix/store/*/bin/chromium*")
        if r: chrome_bin = sorted(r)[0]
    if chrome_bin:
        opts.binary_location = chrome_bin

    cdriver = os.environ.get("CHROMEDRIVER_PATH")
    if not cdriver:
        for p in ["/usr/bin/chromedriver","/usr/bin/chromium-driver",
                  "/usr/lib/chromium/chromedriver",
                  "/usr/lib/chromium-browser/chromedriver"]:
            if os.path.exists(p): cdriver = p; break
    if not cdriver:
        r = glob.glob("/nix/store/*/bin/chromedriver*")
        if r: cdriver = sorted(r)[0]

    if cdriver:
        return webdriver.Chrome(service=Service(cdriver), options=opts)
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
        inp.clear(); inp.send_keys(numero)
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
        return {"error": "Tiempo de espera agotado"}
    except Exception as e:
        return {"error": str(e)}
    finally:
        if driver:
            try: driver.quit()
            except: pass


def fmt(r):
    if r is None:
        return "❌ *NO ENCONTRADO*\n\nDocumento no registrado en SISBEN IV."
    if "error" in r:
        return f"⚠️ *Error:* {r['error']}"
    m = "✅ *RESULTADO SISBEN IV*\n\n"
    if "grupo" in r:         m += f"🏷 *GRUPO:* {r['grupo']}\n"
    if "clasificacion" in r: m += f"📊 *Puntaje:* {r['clasificacion']}\n"
    m += "\n👤 *DATOS PERSONALES*\n"
    for k, l in [("nombres","Nombres"),("apellidos","Apellidos"),
                 ("municipio","Municipio"),("departamento","Depto")]:
        if k in r: m += f"  • {l}: {r[k]}\n"
    if any(k in r for k in ["ficha","fecha","encuesta"]):
        m += "\n📋 *REGISTRO*\n"
        for k, l in [("ficha","Ficha"),("fecha","Fecha"),("encuesta","Encuesta")]:
            if k in r: m += f"  • {l}: {r[k]}\n"
    return m


def menu_tipo():
    b, f = [], []
    for nombre, valor in TIPOS:
        f.append(InlineKeyboardButton(nombre, callback_data=f"t_{valor}"))
        if len(f) == 2: b.append(f); f = []
    if f: b.append(f)
    b.append([InlineKeyboardButton("❌ Cancelar", callback_data="cancelar")])
    return InlineKeyboardMarkup(b)


# ══════════════════════════════════════════════════════════
#  COMANDOS GENERALES
# ══════════════════════════════════════════════════════════
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not es_usuario(user.id):
        await update.message.reply_text(
            "⛔ *Acceso restringido.*\n\nContacta a un administrador para obtener acceso.",
            parse_mode="Markdown"
        )
        return

    texto = (
        f"👋 Hola *{user.first_name}*\n\n"
        "🔎 Bot de consulta *SISBEN IV*\n\n"
        "📋 *Comandos:*\n"
        "  /consultar — Consultar en SISBEN\n"
        "  /ayuda — Ayuda\n"
    )
    if es_admin(user.id):
        texto += (
            "\n🔐 *Panel Admin:*\n"
            "  /adminpanel — Gestionar admins y usuarios\n"
            "  /stats — Estadísticas del bot\n"
        )
    await update.message.reply_text(texto, parse_mode="Markdown")


async def ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *Ayuda*\n\n"
        "/consultar — Inicia consulta SISBEN\n"
        "/cancelar — Cancela operación actual\n"
        "/ayuda — Este mensaje\n",
        parse_mode="Markdown"
    )


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not es_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Sin permisos.")
        return
    db = cargar_db()
    await update.message.reply_text(
        f"📊 *Estadísticas*\n\n"
        f"👑 Owner: `{OWNER_ID}`\n"
        f"🛡 Admins: {len(db['admins'])}\n"
        f"👥 Usuarios: {len(db['usuarios'])}\n"
        f"🔍 Consultas totales: {db.get('consultas', 0)}\n",
        parse_mode="Markdown"
    )


# ══════════════════════════════════════════════════════════
#  PANEL ADMIN  (inline)
# ══════════════════════════════════════════════════════════
def teclado_panel():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛡 Gestionar Admins",   callback_data="panel_admins")],
        [InlineKeyboardButton("👥 Gestionar Usuarios", callback_data="panel_usuarios")],
        [InlineKeyboardButton("📊 Stats",             callback_data="panel_stats")],
    ])


def teclado_seccion(seccion: str, items: list, puede_eliminar: bool):
    """Genera teclado para sección admins o usuarios."""
    b = []
    for item in items:
        label = f"👑 {item}" if item == OWNER_ID else f"🆔 {item}"
        b.append([InlineKeyboardButton(label, callback_data="noop")])
    b.append([InlineKeyboardButton(f"➕ Agregar {seccion}", callback_data=f"add_{seccion}")])
    if puede_eliminar and items:
        b.append([InlineKeyboardButton(f"➖ Eliminar {seccion}", callback_data=f"del_list_{seccion}")])
    b.append([InlineKeyboardButton("🔙 Volver", callback_data="panel_volver")])
    return InlineKeyboardMarkup(b)


async def adminpanel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not es_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Sin permisos.")
        return
    db = cargar_db()
    await update.message.reply_text(
        f"🔐 *Panel de Administración*\n\n"
        f"🛡 Admins: {len(db['admins'])}  |  👥 Usuarios: {len(db['usuarios'])}\n\n"
        f"Elige una opción:",
        reply_markup=teclado_panel(),
        parse_mode="Markdown"
    )


async def panel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id

    if not es_admin(uid):
        await q.edit_message_text("⛔ Sin permisos.")
        return

    db = cargar_db()
    data = q.data

    # ── VOLVER ──
    if data == "panel_volver":
        await q.edit_message_text(
            f"🔐 *Panel de Administración*\n\n"
            f"🛡 Admins: {len(db['admins'])}  |  👥 Usuarios: {len(db['usuarios'])}\n\n"
            f"Elige una opción:",
            reply_markup=teclado_panel(), parse_mode="Markdown"
        )

    # ── STATS ──
    elif data == "panel_stats":
        await q.edit_message_text(
            f"📊 *Estadísticas*\n\n"
            f"👑 Owner: `{OWNER_ID}`\n"
            f"🛡 Admins: {len(db['admins'])}\n"
            f"👥 Usuarios: {len(db['usuarios'])}\n"
            f"🔍 Consultas: {db.get('consultas',0)}\n",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Volver", callback_data="panel_volver")]]),
            parse_mode="Markdown"
        )

    # ── SECCIÓN ADMINS ──
    elif data == "panel_admins":
        lista = db["admins"]
        puede_el = es_owner(uid)  # Solo owner puede eliminar admins
        await q.edit_message_text(
            f"🛡 *Admins* ({len(lista)})\n{''.join([chr(10)+f'  • `{a}`' + (' 👑' if a==OWNER_ID else '') for a in lista])}",
            reply_markup=teclado_seccion("admin", lista, puede_el),
            parse_mode="Markdown"
        )

    # ── SECCIÓN USUARIOS ──
    elif data == "panel_usuarios":
        lista = db["usuarios"]
        await q.edit_message_text(
            f"👥 *Usuarios* ({len(lista)})\n" +
            ("  _Sin usuarios agregados_" if not lista else
             "".join([f"\n  • `{u}`" for u in lista])),
            reply_markup=teclado_seccion("usuario", lista, True),
            parse_mode="Markdown"
        )

    # ── AGREGAR ADMIN ──
    elif data == "add_admin":
        context.user_data["accion"] = "agregar_admin"
        await q.edit_message_text(
            "➕ Envía el *ID de Telegram* del nuevo admin:\n\n_(o /cancelar para salir)_",
            parse_mode="Markdown"
        )

    # ── AGREGAR USUARIO ──
    elif data == "add_usuario":
        context.user_data["accion"] = "agregar_usuario"
        await q.edit_message_text(
            "➕ Envía el *ID de Telegram* del nuevo usuario:\n\n_(o /cancelar para salir)_",
            parse_mode="Markdown"
        )

    # ── LISTAR PARA ELIMINAR ADMIN ──
    elif data == "del_list_admin":
        if not es_owner(uid):
            await q.answer("⛔ Solo el owner puede eliminar admins.", show_alert=True)
            return
        eliminables = [a for a in db["admins"] if a != OWNER_ID]
        if not eliminables:
            await q.answer("No hay admins para eliminar.", show_alert=True)
            return
        botones = [[InlineKeyboardButton(f"🗑 {a}", callback_data=f"del_admin_{a}")] for a in eliminables]
        botones.append([InlineKeyboardButton("🔙 Volver", callback_data="panel_admins")])
        await q.edit_message_text(
            "Selecciona el admin a *eliminar*:",
            reply_markup=InlineKeyboardMarkup(botones),
            parse_mode="Markdown"
        )

    # ── LISTAR PARA ELIMINAR USUARIO ──
    elif data == "del_list_usuario":
        lista = db["usuarios"]
        if not lista:
            await q.answer("No hay usuarios para eliminar.", show_alert=True)
            return
        botones = [[InlineKeyboardButton(f"🗑 {u}", callback_data=f"del_usuario_{u}")] for u in lista]
        botones.append([InlineKeyboardButton("🔙 Volver", callback_data="panel_usuarios")])
        await q.edit_message_text(
            "Selecciona el usuario a *eliminar*:",
            reply_markup=InlineKeyboardMarkup(botones),
            parse_mode="Markdown"
        )

    # ── CONFIRMAR ELIMINAR ADMIN ──
    elif data.startswith("del_admin_"):
        if not es_owner(uid):
            await q.answer("⛔ Solo el owner.", show_alert=True)
            return
        target = int(data.replace("del_admin_", ""))
        if target == OWNER_ID:
            await q.answer("⛔ No se puede eliminar al owner.", show_alert=True)
            return
        db["admins"] = [a for a in db["admins"] if a != target]
        guardar_db(db)
        await q.edit_message_text(
            f"✅ Admin `{target}` eliminado.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Volver", callback_data="panel_admins")]]),
            parse_mode="Markdown"
        )

    # ── CONFIRMAR ELIMINAR USUARIO ──
    elif data.startswith("del_usuario_"):
        target = int(data.replace("del_usuario_", ""))
        db["usuarios"] = [u for u in db["usuarios"] if u != target]
        guardar_db(db)
        await q.edit_message_text(
            f"✅ Usuario `{target}` eliminado.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Volver", callback_data="panel_usuarios")]]),
            parse_mode="Markdown"
        )

    elif data == "noop":
        pass


async def recibir_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Recibe IDs nuevos de admin o usuario según contexto."""
    uid = update.effective_user.id
    if not es_admin(uid):
        return

    accion = context.user_data.get("accion")
    if accion not in ("agregar_admin", "agregar_usuario"):
        return

    texto = update.message.text.strip()
    try:
        nuevo_id = int(texto)
    except ValueError:
        await update.message.reply_text("⚠️ ID inválido. Debe ser un número entero.")
        return

    db = cargar_db()

    if accion == "agregar_admin":
        if nuevo_id in db["admins"]:
            await update.message.reply_text(f"ℹ️ `{nuevo_id}` ya es admin.", parse_mode="Markdown")
        else:
            db["admins"].append(nuevo_id)
            guardar_db(db)
            await update.message.reply_text(f"✅ Admin `{nuevo_id}` agregado. 🛡", parse_mode="Markdown")

    elif accion == "agregar_usuario":
        if nuevo_id in db["usuarios"] or nuevo_id in db["admins"]:
            await update.message.reply_text(f"ℹ️ `{nuevo_id}` ya tiene acceso.", parse_mode="Markdown")
        else:
            db["usuarios"].append(nuevo_id)
            guardar_db(db)
            await update.message.reply_text(f"✅ Usuario `{nuevo_id}` agregado. 👥", parse_mode="Markdown")

    context.user_data.pop("accion", None)


# ══════════════════════════════════════════════════════════
#  FLUJO CONSULTA SISBEN
# ══════════════════════════════════════════════════════════
async def consultar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not es_usuario(update.effective_user.id):
        await update.message.reply_text("⛔ Sin acceso. Contacta a un administrador.")
        return ConversationHandler.END
    await update.message.reply_text("Selecciona tipo de documento:", reply_markup=menu_tipo())
    return ELIGIENDO_TIPO


async def elegir_tipo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "cancelar":
        await q.edit_message_text("❌ Cancelado.")
        return ConversationHandler.END
    valor = q.data.replace("t_", "")
    nombre = next((n for n, v in TIPOS if v == valor), valor)
    context.user_data["tipo"] = valor
    await q.edit_message_text(
        f"📄 Tipo: *{nombre}*\n\nIngresa el número de documento:",
        parse_mode="Markdown"
    )
    return INGRESANDO_NUMERO


async def ingresar_numero(update: Update, context: ContextTypes.DEFAULT_TYPE):
    numero = update.message.text.strip()
    if not numero or not numero.replace("-","").replace(" ","").isalnum():
        await update.message.reply_text("⚠️ Número inválido. Intenta de nuevo:")
        return INGRESANDO_NUMERO

    msg = await update.message.reply_text("⏳ Consultando SISBEN IV... (~20 seg)")

    # Selenium en hilo separado → no bloquea el bot
    resultado = await asyncio.to_thread(consultar_sisben, context.user_data["tipo"], numero)

    await msg.edit_text(fmt(resultado), parse_mode="Markdown")

    # Incrementar contador
    db = cargar_db()
    db["consultas"] = db.get("consultas", 0) + 1
    guardar_db(db)

    # Notificar a todos los admins
    user = update.effective_user
    tipo_nombre = next((n for n, v in TIPOS if v == context.user_data["tipo"]), context.user_data["tipo"])
    encontrado = resultado is not None and "error" not in resultado
    for admin_id in db["admins"]:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=(
                    f"📌 *Nueva Consulta*\n\n"
                    f"👤 [{user.full_name}](tg://user?id={user.id})\n"
                    f"🆔 ID: `{user.id}`\n"
                    f"📄 Tipo: {tipo_nombre}\n"
                    f"🔢 Doc: `{numero}`\n"
                    f"📊 Resultado: {'✅ Encontrado' if encontrado else '❌ No encontrado'}"
                ),
                parse_mode="Markdown"
            )
        except:
            pass

    return ConversationHandler.END


async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("accion", None)
    await update.message.reply_text("❌ Cancelado.")
    return ConversationHandler.END


# ══════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════
def main():
    app = Application.builder().token(TOKEN).build()

    # Conversación SISBEN
    conv_sisben = ConversationHandler(
        entry_points=[CommandHandler("consultar", consultar)],
        states={
            ELIGIENDO_TIPO:   [CallbackQueryHandler(elegir_tipo)],
            INGRESANDO_NUMERO:[MessageHandler(filters.TEXT & ~filters.COMMAND, ingresar_numero)],
        },
        fallbacks=[CommandHandler("cancelar", cancelar)],
        per_message=False,
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ayuda", ayuda))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("adminpanel", adminpanel))
    app.add_handler(conv_sisben)
    app.add_handler(CallbackQueryHandler(panel_callback, pattern="^(panel_|add_|del_|noop)"))
    # Handler para recibir IDs nuevos (fuera de conversación)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_id))

    logger.info("✅ Bot SISBEN iniciado (Owner: %s)", OWNER_ID)
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
