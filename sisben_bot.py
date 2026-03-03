#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
╔══════════════════════════════════════════════════════════╗
║        BOT COLOMBIA - CONSULTAS GOBIERNO REAL            ║
║                                                          ║
║  Módulos reales confirmados:                             ║
║  🔎 SISBEN IV          → sisben.gov.co                   ║
║  🏥 RUAF/SISPRO        → ruaf.sispro.gov.co              ║
║  ⚖️ Rama Judicial      → ramajudicial.gov.co             ║
║  🚦 SIMIT              → fcm.org.co/simit                ║
║  📋 DIAN RUT           → muisca.dian.gov.co              ║
║                                                          ║
║  Sistema: Planes por días / semanas / mes / permanente   ║
║  Owner fijo: 8114050673                                  ║
╚══════════════════════════════════════════════════════════╝
"""

import logging, time, os, glob, asyncio, json, re
from datetime import datetime, timedelta
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
from selenium.common.exceptions import (
    TimeoutException, ElementNotInteractableException,
    InvalidElementStateException
)

# ══════════════════════════════════════════════════════════
#  CONFIG
# ══════════════════════════════════════════════════════════
TOKEN    = os.environ.get("BOT_TOKEN", "8574051542:AAH_N4RBST0wCpkLKDOFNEc1R93vePWxEPY")
OWNER_ID = 8114050673
DB_FILE  = "database.json"

PLANES = {
    "dia":        {"nombre": "1 Día",     "dias": 1},
    "semana":     {"nombre": "1 Semana",  "dias": 7},
    "mes":        {"nombre": "1 Mes",     "dias": 30},
    "permanente": {"nombre": "Permanente","dias": 99999},
}

(SEL_MODULO, SEL_TIPO, ING_NUMERO, ING_FECHA, ING_PLACA) = range(5)

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

TIPOS_SISBEN = [
    ("Registro Civil","1"),       ("Tarjeta de Identidad","2"),
    ("Cedula de Ciudadania","3"), ("Cedula de Extranjeria","4"),
    ("DNI Pais de Origen","5"),   ("DNI Pasaporte","6"),
    ("Salvoconducto Refugiado","7"), ("Permiso Esp. Permanencia","8"),
    ("Permiso Protec. Temporal","9"),
]
TIPOS_RUAF = [
    ("Cédula de Ciudadanía","CC"), ("Tarjeta de Identidad","TI"),
    ("Registro Civil","RC"),       ("Cédula de Extranjería","CE"),
    ("Pasaporte","PA"),
]

# ══════════════════════════════════════════════════════════
#  BASE DE DATOS
# ══════════════════════════════════════════════════════════
def cargar_db():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE) as f: return json.load(f)
        except: pass
    db = {"admins": [OWNER_ID], "usuarios": {}, "consultas": 0}
    guardar_db(db); return db

def guardar_db(db):
    with open(DB_FILE, "w") as f: json.dump(db, f, indent=2)

def es_owner(uid): return uid == OWNER_ID
def es_admin(uid):
    db = cargar_db()
    return uid == OWNER_ID or uid in db["admins"]
def es_activo(uid):
    if es_admin(uid): return True
    db = cargar_db()
    info = db.get("usuarios", {}).get(str(uid))
    if not info: return False
    if info.get("plan") == "permanente": return True
    exp = info.get("expira")
    return bool(exp and datetime.now() < datetime.fromisoformat(exp))
def agregar_usuario_plan(uid, plan_key):
    db = cargar_db()
    if "usuarios" not in db: db["usuarios"] = {}
    plan = PLANES[plan_key]
    exp = None if plan_key == "permanente" else (datetime.now() + timedelta(days=plan["dias"])).isoformat()
    db["usuarios"][str(uid)] = {
        "plan": plan_key, "nombre_plan": plan["nombre"],
        "expira": exp, "desde": datetime.now().isoformat()
    }
    guardar_db(db)
def eliminar_usuario(uid):
    db = cargar_db()
    db.get("usuarios", {}).pop(str(uid), None)
    guardar_db(db)

# ══════════════════════════════════════════════════════════
#  SELENIUM HELPERS
# ══════════════════════════════════════════════════════════
def get_driver():
    opts = Options()
    for a in ["--headless=new", "--no-sandbox", "--disable-dev-shm-usage",
              "--disable-gpu", "--disable-extensions",
              "--blink-settings=imagesEnabled=false",
              "--window-size=1920,1080", "--log-level=3",
              "--disable-blink-features=AutomationControlled"]:
        opts.add_argument(a)
    opts.add_experimental_option("excludeSwitches", ["enable-logging", "enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    cb = os.environ.get("CHROME_BIN")
    if not cb:
        for p in ["/usr/bin/chromium", "/usr/bin/chromium-browser", "/usr/bin/google-chrome"]:
            if os.path.exists(p): cb = p; break
    if not cb:
        r = glob.glob("/nix/store/*/bin/chromium*")
        if r: cb = sorted(r)[0]
    if cb: opts.binary_location = cb
    cd = os.environ.get("CHROMEDRIVER_PATH")
    if not cd:
        for p in ["/usr/bin/chromedriver", "/usr/bin/chromium-driver", "/usr/lib/chromium/chromedriver"]:
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

def find_first(driver, xpaths, timeout=12):
    for xp in xpaths:
        try:
            el = WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.XPATH, xp)))
            if el.is_displayed(): return el
        except: continue
    return None

def click_safe(driver, el):
    try: el.click()
    except: driver.execute_script("arguments[0].click();", el)

def clean_error(e):
    return str(e).split("Stacktrace")[0].split("\n")[0].strip()[:200]

# ══════════════════════════════════════════════════════════
#  MÓDULO 1 — SISBEN IV
#  URL: reportes.sisben.gov.co
#  Datos: Grupo, puntaje, nombres, apellidos, municipio,
#         departamento, ficha, fecha encuesta
# ══════════════════════════════════════════════════════════
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
        click_safe(driver, driver.find_element(By.ID, "botonenvio"))
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
    if r is None: return (
        "╔════════════════════════════════╗\n"
        "║       MÓDULO SISBEN IV         ║\n"
        "╚════════════════════════════════╝\n\n"
        "❌ *NO REGISTRADO EN SISBEN IV*\n\n"
        "_Este documento no aparece en la base de datos del SISBEN IV._"
    )
    if "error" in r: return f"⚠️ *Error SISBEN:* `{r['error']}`"
    m  = "╔════════════════════════════════╗\n"
    m += "║       MÓDULO SISBEN IV         ║\n"
    m += "╚════════════════════════════════╝\n\n"
    if "grupo" in r:         m += f"🏷 *GRUPO:* {r['grupo']}\n"
    if "clasificacion" in r: m += f"📊 *Puntaje:* {r['clasificacion']}\n"
    m += "\n👤 *DATOS PERSONALES*\n──────────────────────\n"
    for k, l in [("nombres","Nombres"),("apellidos","Apellidos"),
                 ("municipio","Municipio"),("departamento","Departamento")]:
        if k in r: m += f"  🔹 *{l}:* {r[k]}\n"
    if any(k in r for k in ["ficha","fecha","encuesta"]):
        m += "\n📋 *REGISTRO*\n──────────────────────\n"
        for k, l in [("ficha","Ficha"),("fecha","Fecha consulta"),("encuesta","Encuesta vigente")]:
            if k in r: m += f"  🔹 *{l}:* {r[k]}\n"
    return m

# ══════════════════════════════════════════════════════════
#  MÓDULO 2 — RUAF / SISPRO
#  URL: ruaf.sispro.gov.co
#  Datos: EPS, Pensión, ARL, Cesantías, Caja Compensación
#  Requiere: tipo doc + número + fecha expedición
# ══════════════════════════════════════════════════════════
def consultar_ruaf(tipo_doc, numero, fecha_exp):
    driver = None
    try:
        driver = get_driver(); driver.set_page_load_timeout(40)
        driver.get("https://ruaf.sispro.gov.co/"); time.sleep(4)
        try:
            btn = find_first(driver, ["//input[@value='Acepto']","//button[contains(text(),'Acepto')]"], timeout=5)
            if btn: click_safe(driver, btn); time.sleep(1)
            btn2 = find_first(driver, ["//input[@value='Enviar']","//button[contains(text(),'Enviar')]"], timeout=3)
            if btn2: click_safe(driver, btn2); time.sleep(2)
        except: pass
        sel = find_first(driver, ["//select[contains(@id,'Tipo') or contains(@name,'Tipo') or contains(@id,'tipo')]"], timeout=10)
        if sel: safe_select(driver, sel, tipo_doc); time.sleep(0.5)
        inp_num = find_first(driver, [
            "//input[contains(@id,'umero') or contains(@id,'ocumento')]",
            "//input[@type='text'][1]"], timeout=10)
        if inp_num: safe_send(driver, inp_num, numero); time.sleep(0.5)
        inp_fec = find_first(driver, [
            "//input[contains(@id,'echa') or contains(@name,'echa')]",
            "//input[@type='text'][2]"], timeout=8)
        if inp_fec: safe_send(driver, inp_fec, fecha_exp); time.sleep(0.5)
        btn = find_first(driver, [
            "//input[@value='Consultar']","//button[contains(text(),'Consultar')]",
            "//input[@type='submit']","//button[@type='submit']"], timeout=8)
        if btn: click_safe(driver, btn)
        time.sleep(10)
        html = driver.page_source
        if "no se encontr" in html.lower() or "no existen" in html.lower(): return None
        r = {}
        try:
            ne = find_first(driver, ["//td[contains(text(),'Nombre')]/following-sibling::td"], timeout=4)
            if ne: r["nombre"] = ne.text.strip()
        except: pass
        sistemas = ["Salud","Pensión","Riesgos Laborales","Cesantías","Caja Compensación"]
        for sis in sistemas:
            try:
                fila = driver.find_element(By.XPATH, f"//tr[contains(.,'{sis}')]")
                celdas = fila.find_elements(By.TAG_NAME, "td")
                if len(celdas) >= 2:
                    r[sis] = {
                        "entidad": celdas[1].text.strip() if len(celdas)>1 else "",
                        "estado":  celdas[2].text.strip() if len(celdas)>2 else "",
                        "regimen": celdas[3].text.strip() if len(celdas)>3 else "",
                    }
            except: pass
        if not r:
            body = driver.find_element(By.TAG_NAME,"body").text
            if len(body) > 200: r["raw"] = body[:1500]
        return r if r else None
    except TimeoutException: return {"error": "Tiempo de espera agotado"}
    except Exception as e: return {"error": clean_error(e)}
    finally:
        if driver:
            try: driver.quit()
            except: pass

def fmt_ruaf(r, numero):
    if r is None: return (
        "╔════════════════════════════════╗\n"
        "║      MÓDULO RUAF / SISPRO      ║\n"
        "╚════════════════════════════════╝\n\n"
        f"🔢 *Documento:* `{numero}`\n\n"
        "❌ *NO REGISTRADO EN RUAF*\n\n"
        "_No se encontraron afiliaciones en el sistema._"
    )
    if "error" in r: return f"⚠️ *Error RUAF:* `{r['error']}`"
    m  = "╔════════════════════════════════╗\n"
    m += "║      MÓDULO RUAF / SISPRO      ║\n"
    m += "╚════════════════════════════════╝\n\n"
    m += f"🔢 *Documento:* `{numero}`\n"
    if "nombre" in r: m += f"👤 *Nombre:* {r['nombre']}\n"
    iconos = {"Salud":"🏥","Pensión":"🏦","Riesgos Laborales":"🦺","Cesantías":"💰","Caja Compensación":"🏠"}
    found = False
    for sis, ico in iconos.items():
        if sis in r:
            found = True
            d = r[sis]
            m += f"\n{ico} *{sis}*\n──────────────────────\n"
            if d.get("entidad"): m += f"  🏢 *Entidad:* {d['entidad']}\n"
            if d.get("estado"):
                em = "🟢" if "activ" in d["estado"].lower() else "🔴"
                m += f"  📌 *Estado:* {em} {d['estado']}\n"
            if d.get("regimen"): m += f"  📋 *Régimen:* {d['regimen']}\n"
    if not found and "raw" in r:
        m += f"\n📄 *Datos encontrados:*\n`{r['raw'][:800]}`\n"
    return m

# ══════════════════════════════════════════════════════════
#  MÓDULO 3 — RAMA JUDICIAL
#  URL: consultaprocesos.ramajudicial.gov.co
#  Datos: Procesos judiciales, radicado, despacho,
#         tipo proceso, medidas de aseguramiento
# ══════════════════════════════════════════════════════════
def consultar_rama_judicial(numero_doc):
    driver = None
    try:
        from selenium.webdriver.common.action_chains import ActionChains
        driver = get_driver(); driver.set_page_load_timeout(45)
        driver.get("https://consultaprocesos.ramajudicial.gov.co/procesos/NumeroIdentificacion")
        time.sleep(8)
        try:
            WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.XPATH, "//input | //select")))
        except: pass
        time.sleep(2)

        # Seleccionar Persona Natural
        try:
            sels = driver.find_elements(By.TAG_NAME, "select")
            for s in sels:
                opts = [o.get_attribute("value") for o in s.find_elements(By.TAG_NAME, "option")]
                if any(v in opts for v in ["PN","Natural","1"]):
                    for v in ["PN","Natural","1"]:
                        try: safe_select(driver, s, v); break
                        except: continue
                    time.sleep(0.5); break
        except: pass

        # Seleccionar CC
        try:
            sels = driver.find_elements(By.TAG_NAME, "select")
            for s in sels[1:]:
                opts = [o.get_attribute("value") for o in s.find_elements(By.TAG_NAME, "option")]
                if any(v in opts for v in ["CC","cc","1"]):
                    for v in ["CC","cc","1"]:
                        try: safe_select(driver, s, v); break
                        except: continue
                    time.sleep(0.5); break
        except: pass

        # Ingresar número por JS (SPA Angular)
        ok = driver.execute_script("""
            var inputs = document.querySelectorAll('input[type="text"],input[type="number"],input:not([type])');
            for(var i=0;i<inputs.length;i++){
                if(inputs[i].offsetWidth>0){
                    inputs[i].focus();
                    var s=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;
                    s.call(inputs[i],arguments[0]);
                    inputs[i].dispatchEvent(new Event('input',{bubbles:true}));
                    inputs[i].dispatchEvent(new Event('change',{bubbles:true}));
                    return true;
                }
            }
            return false;
        """, numero_doc)
        if not ok: return {"error": "No se pudo ingresar el número (SPA Angular)"}
        time.sleep(1)

        # Slider seguridad
        try:
            slider = find_first(driver, [
                "//div[contains(@class,'slider') or contains(@class,'drag')]",
                "//span[contains(@class,'handle')]"], timeout=4)
            if slider:
                ActionChains(driver).click_and_hold(slider).move_by_offset(260, 0).release().perform()
                time.sleep(2)
        except: pass

        # Click CONSULTAR por JS
        driver.execute_script("""
            var btns=document.querySelectorAll('button');
            for(var i=0;i<btns.length;i++){
                if(btns[i].textContent.trim().toUpperCase().includes('CONSULTAR')){
                    btns[i].click(); return;
                }
            }
            var subs=document.querySelectorAll('input[type="submit"]');
            if(subs.length) subs[0].click();
        """)
        time.sleep(12)

        page_text = driver.find_element(By.TAG_NAME, "body").text
        html = page_text.lower()

        if any(x in html for x in ["no se encontraron","no existen procesos","0 procesos","sin resultados","no hay registros"]):
            return None

        procesos = []
        try:
            filas = driver.find_elements(By.XPATH, "//table//tbody/tr")
            for fila in filas[:15]:
                celdas = fila.find_elements(By.TAG_NAME, "td")
                if len(celdas) >= 2:
                    datos = [c.text.strip() for c in celdas if c.text.strip()]
                    if datos:
                        procesos.append({
                            "numero":   datos[0] if len(datos)>0 else "",
                            "despacho": datos[1] if len(datos)>1 else "",
                            "tipo":     datos[2] if len(datos)>2 else "",
                            "fecha":    datos[3] if len(datos)>3 else "",
                        })
        except: pass

        preso = any(kw in html for kw in [
            "privación de libertad","detención preventiva","medida de aseguramiento",
            "detención domiciliaria","capturado","detenido","imputado"])

        if procesos:
            return {"procesos": procesos, "preso": preso, "total": len(procesos)}
        elif len(page_text) > 300:
            lineas = [l.strip() for l in page_text.split("\n")
                      if l.strip() and len(l.strip())>8
                      and not any(x in l.lower() for x in ["visitantes","teléfono","calle","correo","politica"])]
            return {"raw": "\n".join(lineas[:25]), "preso": preso}
        return None
    except TimeoutException: return {"error": "Tiempo de espera agotado"}
    except Exception as e: return {"error": clean_error(e)}
    finally:
        if driver:
            try: driver.quit()
            except: pass

def fmt_rama(r, doc):
    cabecera = ("╔════════════════════════════════╗\n"
                "║     MÓDULO RAMA JUDICIAL       ║\n"
                "╚════════════════════════════════╝\n\n"
                f"🔢 *Documento:* `{doc}`\n\n")
    if r is None:
        return cabecera + "✅ *SIN PROCESOS JUDICIALES*\n🟢 *Estado:* Libre — sin procesos activos"
    if "error" in r:
        return f"⚠️ *Error Rama Judicial:* `{r['error']}`"
    m = cabecera
    if r.get("preso"):
        m += "🔴 *ALERTA:* Posible privación de libertad detectada\n\n"
    else:
        m += "🟢 *Sin medidas de aseguramiento detectadas*\n\n"
    if "procesos" in r and r["procesos"]:
        m += f"⚖️ *Procesos encontrados:* {r['total']}\n──────────────────────\n"
        for i, p in enumerate(r["procesos"][:8], 1):
            m += f"\n*Proceso {i}*\n"
            if p.get("numero"):   m += f"  📁 *Radicado:* `{p['numero']}`\n"
            if p.get("despacho"): m += f"  🏛 *Despacho:* {p['despacho']}\n"
            if p.get("tipo"):     m += f"  📋 *Tipo:* {p['tipo']}\n"
            if p.get("fecha"):    m += f"  📅 *Fecha:* {p['fecha']}\n"
        if r["total"] > 8: m += f"\n_...y {r['total']-8} proceso(s) más_\n"
    elif "raw" in r:
        m += f"📄 *Información:*\n{r['raw'][:1000]}\n"
    return m

# ══════════════════════════════════════════════════════════
#  MÓDULO 4 — SIMIT
#  URL: fcm.org.co/simit
#  Datos: Multas, comparendos, deuda total (cédula o placa)
# ══════════════════════════════════════════════════════════
def consultar_simit(consulta):
    driver = None
    try:
        driver = get_driver(); driver.set_page_load_timeout(40)
        driver.get("https://fcm.org.co/simit/#/estado-cuenta"); time.sleep(6)
        inp = find_first(driver, [
            "//input[contains(@placeholder,'documento') or contains(@placeholder,'Documento')]",
            "//input[contains(@placeholder,'placa') or contains(@placeholder,'Placa')]",
            "//input[@type='text'][1]","//input[@type='search'][1]"], timeout=12)
        if not inp: return {"error": "No se encontró campo en SIMIT"}
        safe_send(driver, inp, consulta); time.sleep(0.5)
        btn = find_first(driver, [
            "//button[contains(text(),'Buscar') or contains(text(),'Ver estado')]",
            "//button[contains(@class,'btn-primary')]",
            "//input[@type='submit']"], timeout=8)
        if btn: click_safe(driver, btn)
        else:
            from selenium.webdriver.common.keys import Keys
            inp.send_keys(Keys.RETURN)
        time.sleep(9)
        html = driver.page_source.lower()
        page_text = driver.find_element(By.TAG_NAME, "body").text
        if any(x in html for x in ["sin comparendo","no tiene multas","no se encontr","sin resultado"]):
            return {"sin_multas": True}
        r = {}
        try:
            te = find_first(driver, ["//*[contains(text(),'$')]",
                "//td[contains(@class,'total')]"], timeout=5)
            if te: r["total"] = te.text.strip()
        except: pass
        multas = []
        try:
            filas = driver.find_elements(By.XPATH, "//tbody/tr")
            for fila in filas[:15]:
                celdas = fila.find_elements(By.TAG_NAME, "td")
                if len(celdas) >= 2:
                    txt = " | ".join([c.text.strip() for c in celdas if c.text.strip()])
                    if txt: multas.append(txt)
        except: pass
        if multas: r["multas"] = multas
        if not r:
            if len(page_text) > 100: r["raw"] = page_text[:1500]
            else: return {"sin_multas": True}
        return r
    except TimeoutException: return {"error": "Tiempo de espera agotado"}
    except Exception as e: return {"error": clean_error(e)}
    finally:
        if driver:
            try: driver.quit()
            except: pass

def fmt_simit(r, consulta):
    cabecera = ("╔════════════════════════════════╗\n"
                "║    MÓDULO SIMIT — MULTAS       ║\n"
                "╚════════════════════════════════╝\n\n"
                f"🔢 *Consultado:* `{consulta}`\n\n")
    if "error" in r: return f"⚠️ *Error SIMIT:* `{r['error']}`"
    if r.get("sin_multas"):
        return cabecera + "✅ *SIN MULTAS NI COMPARENDOS*\n🟢 No tiene infracciones activas en SIMIT."
    m = cabecera
    if "total" in r: m += f"💰 *Total deuda:* {r['total']}\n"
    if "multas" in r:
        m += f"\n🚦 *Infracciones ({len(r['multas'])})* :\n──────────────────────\n"
        for i, mul in enumerate(r["multas"][:10], 1):
            m += f"*{i}.* `{mul[:200]}`\n\n"
    elif "raw" in r:
        m += f"📄 *Datos:*\n`{r['raw'][:1000]}`\n"
    return m

# ══════════════════════════════════════════════════════════
#  MÓDULO 5 — DIAN RUT
#  URL: muisca.dian.gov.co
#  Datos: Estado RUT, nombre/razón social, actividad
#         económica, dirección, ciudad, departamento
# ══════════════════════════════════════════════════════════
def consultar_dian_rut(nit):
    driver = None
    try:
        driver = get_driver(); driver.set_page_load_timeout(40)
        driver.get("https://muisca.dian.gov.co/WebRutMuisca/DefConsultaEstadoRUT.faces"); time.sleep(5)
        inp = find_first(driver, [
            "//input[contains(@id,'nit') or contains(@id,'Nit')]",
            "//input[contains(@id,'numero') or contains(@id,'identificacion')]",
            "//input[@type='text'][1]"], timeout=12)
        if not inp: return {"error": "Campo no encontrado en DIAN"}
        safe_send(driver, inp, nit); time.sleep(0.5)
        btn = find_first(driver, [
            "//input[@type='submit']","//button[@type='submit']",
            "//button[contains(text(),'Buscar')]"], timeout=8)
        if btn: click_safe(driver, btn)
        time.sleep(7)
        html = driver.page_source.lower()
        if "no se encontr" in html or "no existe" in html: return None
        r = {}
        for label, key in [("Nombre","nombre"),("Razón Social","razon_social"),
                            ("Estado","estado"),("Tipo","tipo"),
                            ("Dirección","direccion"),("Ciudad","ciudad"),
                            ("Departamento","departamento"),("Actividad","actividad")]:
            try:
                el = find_first(driver, [
                    f"//td[contains(text(),'{label}')]/following-sibling::td[1]",
                    f"//label[contains(text(),'{label}')]/following-sibling::span[1]",
                    f"//th[contains(text(),'{label}')]/following-sibling::td[1]"], timeout=3)
                if el and el.text.strip(): r[key] = el.text.strip()
            except: pass
        if not r:
            body = driver.find_element(By.TAG_NAME, "body").text
            if len(body) > 200: r["raw"] = body[:1500]
        return r if r else None
    except TimeoutException: return {"error": "Tiempo de espera agotado"}
    except Exception as e: return {"error": clean_error(e)}
    finally:
        if driver:
            try: driver.quit()
            except: pass

def fmt_dian(r, nit):
    cabecera = ("╔════════════════════════════════╗\n"
                "║       MÓDULO DIAN — RUT        ║\n"
                "╚════════════════════════════════╝\n\n"
                f"🔢 *NIT/Cédula:* `{nit}`\n\n")
    if r is None: return cabecera + "❌ *NO ENCONTRADO*\n_No registra en DIAN RUT._"
    if "error" in r: return f"⚠️ *Error DIAN:* `{r['error']}`"
    m = cabecera
    for k, l, emo in [("nombre","Nombre","👤"),("razon_social","Razón Social","🏢"),
                      ("tipo","Tipo Persona","🪪"),("actividad","Actividad Económica","🔧"),
                      ("estado","Estado","📌"),("direccion","Dirección","📍"),
                      ("ciudad","Ciudad","🏙"),("departamento","Departamento","🗺")]:
        if k in r:
            if k == "estado":
                em = "🟢" if "activ" in r[k].lower() else "🔴"
                m += f"{emo} *{l}:* {em} {r[k]}\n"
            else:
                m += f"{emo} *{l}:* {r[k]}\n"
    if "raw" in r and len(r) == 1:
        m += f"\n📄 *Datos:*\n`{r['raw'][:800]}`\n"
    return m

# ══════════════════════════════════════════════════════════
#  MENÚS
# ══════════════════════════════════════════════════════════
def menu_modulos():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔎 SISBEN IV",                callback_data="m_sisben")],
        [InlineKeyboardButton("🏥 RUAF (EPS·Pensión·ARL)",  callback_data="m_ruaf")],
        [InlineKeyboardButton("⚖️ Rama Judicial",            callback_data="m_rama")],
        [InlineKeyboardButton("🚦 SIMIT (Multas / Placa)",   callback_data="m_simit")],
        [InlineKeyboardButton("📋 DIAN — RUT",               callback_data="m_dian")],
        [InlineKeyboardButton("❌ Cancelar",                  callback_data="cancelar")],
    ])

def menu_tipo_sisben():
    b, f = [], []
    for n, v in TIPOS_SISBEN:
        f.append(InlineKeyboardButton(n, callback_data=f"ts_{v}"))
        if len(f) == 2: b.append(f); f = []
    if f: b.append(f)
    b.append([InlineKeyboardButton("❌ Cancelar", callback_data="cancelar")])
    return InlineKeyboardMarkup(b)

def menu_tipo_ruaf():
    b = [[InlineKeyboardButton(n, callback_data=f"tr_{v}")] for n, v in TIPOS_RUAF]
    b.append([InlineKeyboardButton("❌ Cancelar", callback_data="cancelar")])
    return InlineKeyboardMarkup(b)

def menu_planes():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📅 1 Día",       callback_data="plan_dia")],
        [InlineKeyboardButton("📆 1 Semana",    callback_data="plan_semana")],
        [InlineKeyboardButton("🗓 1 Mes",       callback_data="plan_mes")],
        [InlineKeyboardButton("♾ Permanente",  callback_data="plan_permanente")],
        [InlineKeyboardButton("🔙 Volver",      callback_data="panel_volver")],
    ])

def teclado_panel():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛡 Admins",   callback_data="panel_admins")],
        [InlineKeyboardButton("👥 Usuarios", callback_data="panel_usuarios")],
        [InlineKeyboardButton("📊 Stats",    callback_data="panel_stats")],
    ])

# ══════════════════════════════════════════════════════════
#  COMANDOS GENERALES
# ══════════════════════════════════════════════════════════
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    if not es_activo(u.id):
        db = cargar_db(); info = db.get("usuarios", {}).get(str(u.id))
        msg = ("⛔ *Plan vencido*\n\nTu acceso expiró.\n"
               "Contacta al administrador para renovar.") if info else \
              "⛔ *Acceso restringido*\n\nContacta al administrador para obtener acceso."
        await update.message.reply_text(msg, parse_mode="Markdown"); return

    txt = (
        f"👋 Hola *{u.first_name}*\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🤖 *Bot de Consultas Colombia*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "📡 *Módulos disponibles:*\n"
        "  🔎 *SISBEN IV* — Grupo y puntaje\n"
        "  🏥 *RUAF* — EPS · Pensión · ARL · Cesantías\n"
        "  ⚖️ *Rama Judicial* — Procesos judiciales\n"
        "  🚦 *SIMIT* — Multas y comparendos\n"
        "  📋 *DIAN* — Estado RUT\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "📌 *Comandos:*\n"
        "  /consultar — Iniciar consulta\n"
        "  /info — Información del bot\n"
        "  /ayuda — Ayuda de uso\n"
    )
    if es_admin(u.id):
        txt += "  /adminpanel — Panel admin\n  /stats — Estadísticas\n"
    else:
        info = cargar_db().get("usuarios", {}).get(str(u.id))
        if info:
            exp = info.get("expira")
            exp_txt = "Permanente ♾" if not exp else datetime.fromisoformat(exp).strftime("%d/%m/%Y %H:%M")
            txt += f"\n━━━━━━━━━━━━━━━━━━━━━━━━\n📋 *Tu plan:* {info['nombre_plan']}\n⏰ *Expira:* {exp_txt}\n"
    await update.message.reply_text(txt, parse_mode="Markdown")


async def info_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Información completa del bot y recomendaciones de uso."""
    txt = (
        "╔══════════════════════════════════╗\n"
        "║   ℹ️  INFORMACIÓN DEL BOT         ║\n"
        "╚══════════════════════════════════╝\n\n"
        "🤖 *Bot de Consultas Gobierno Colombia*\n"
        "_Consultas reales a bases de datos oficiales_\n\n"

        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "📡 *MÓDULOS Y LO QUE DAN*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

        "🔎 *SISBEN IV* `sisben.gov.co`\n"
        "  › Grupo SISBEN (A, B, C, D)\n"
        "  › Puntaje de clasificación\n"
        "  › Nombres, apellidos, municipio\n"
        "  › Número de ficha y fecha de encuesta\n\n"

        "🏥 *RUAF / SISPRO* `ruaf.sispro.gov.co`\n"
        "  › Afiliación EPS · estado · régimen\n"
        "  › Fondo de pensión · estado\n"
        "  › ARL (Riesgos Laborales)\n"
        "  › Fondo de cesantías\n"
        "  › Caja de compensación familiar\n"
        "  ⚠️ _Requiere fecha de expedición de cédula_\n\n"

        "⚖️ *Rama Judicial* `ramajudicial.gov.co`\n"
        "  › Procesos judiciales activos\n"
        "  › Número de radicado\n"
        "  › Despacho judicial\n"
        "  › Detecta medidas de aseguramiento\n"
        "  › Indica si hay privación de libertad\n\n"

        "🚦 *SIMIT* `fcm.org.co/simit`\n"
        "  › Multas y comparendos de tránsito\n"
        "  › Deuda total acumulada\n"
        "  › Consulta por cédula O por placa\n\n"

        "📋 *DIAN RUT* `muisca.dian.gov.co`\n"
        "  › Estado del RUT (activo/inactivo)\n"
        "  › Nombre o razón social\n"
        "  › Tipo de persona (natural/jurídica)\n"
        "  › Actividad económica (CIIU)\n"
        "  › Dirección y ciudad registrada\n\n"

        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "💡 *RECOMENDACIONES DE USO*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "✅ Consulta *SISBEN* primero — es la más rápida\n"
        "✅ Para EPS usa *RUAF* con la fecha correcta\n"
        "✅ *SIMIT* funciona con cédula o placa del vehículo\n"
        "✅ *DIAN* es útil para empresas y trabajadores\n"
        "⏱ Cada consulta toma *15-30 segundos* aprox.\n"
        "🔄 Si hay error, intenta de nuevo — puede ser lentitud del servidor oficial\n\n"

        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "❌ *QUÉ NO PUEDE HACER*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "❌ SOAT — tiene CAPTCHA\n"
        "❌ Registraduría — tiene reCAPTCHA Google\n"
        "❌ ADRES directo — tiene reCAPTCHA Google\n"
        "❌ Colpensiones — requiere login personal\n\n"

        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "📞 *SOPORTE*\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Si un módulo falla constantemente,\n"
        "puede ser que el servidor del gobierno\n"
        "esté en mantenimiento. Intenta más tarde.\n"
    )
    await update.message.reply_text(txt, parse_mode="Markdown")


async def ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *Guía rápida*\n\n"
        "*1.* Escribe /consultar\n"
        "*2.* Selecciona el módulo\n"
        "*3.* Selecciona tipo de documento\n"
        "*4.* Escribe el número\n"
        "_Para RUAF también pedirá fecha de expedición_\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "/consultar — Iniciar consulta\n"
        "/info — Información detallada\n"
        "/cancelar — Cancelar operación\n",
        parse_mode="Markdown")


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not es_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Sin permisos."); return
    db = cargar_db()
    usuarios = db.get("usuarios", {})
    activos = sum(1 for u in usuarios if es_activo(int(u)))
    await update.message.reply_text(
        f"📊 *Estadísticas del Bot*\n\n"
        f"👑 Owner: `{OWNER_ID}`\n"
        f"🛡 Admins: {len(db['admins'])}\n"
        f"👥 Usuarios: {len(usuarios)} ({activos} activos)\n"
        f"🔍 Consultas totales: {db.get('consultas', 0)}\n",
        parse_mode="Markdown")

# ══════════════════════════════════════════════════════════
#  FLUJO CONSULTA
# ══════════════════════════════════════════════════════════
async def consultar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not es_activo(update.effective_user.id):
        await update.message.reply_text("⛔ Sin acceso activo. Contacta al administrador.")
        return ConversationHandler.END
    await update.message.reply_text("📡 *Selecciona el módulo de consulta:*",
        reply_markup=menu_modulos(), parse_mode="Markdown")
    return SEL_MODULO


async def sel_modulo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if q.data == "cancelar": await q.edit_message_text("❌ Cancelado."); return ConversationHandler.END
    if q.data == "m_sisben":
        context.user_data["modulo"] = "sisben"
        await q.edit_message_text("🔎 *SISBEN IV*\n\nSelecciona tipo de documento:",
            reply_markup=menu_tipo_sisben(), parse_mode="Markdown"); return SEL_TIPO
    elif q.data == "m_ruaf":
        context.user_data["modulo"] = "ruaf"
        await q.edit_message_text("🏥 *RUAF / SISPRO*\n\nSelecciona tipo de documento:",
            reply_markup=menu_tipo_ruaf(), parse_mode="Markdown"); return SEL_TIPO
    elif q.data == "m_rama":
        context.user_data["modulo"] = "rama"
        await q.edit_message_text("⚖️ *Rama Judicial*\n\nIngresa el número de cédula:",
            parse_mode="Markdown"); return ING_NUMERO
    elif q.data == "m_simit":
        context.user_data["modulo"] = "simit"
        await q.edit_message_text("🚦 *SIMIT*\n\nIngresa cédula o placa del vehículo:\n_(Ej: 1076350826 o ABC123)_",
            parse_mode="Markdown"); return ING_PLACA
    elif q.data == "m_dian":
        context.user_data["modulo"] = "dian"
        await q.edit_message_text("📋 *DIAN RUT*\n\nIngresa NIT o número de cédula:",
            parse_mode="Markdown"); return ING_NUMERO
    return SEL_MODULO


async def sel_tipo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    if q.data == "cancelar": await q.edit_message_text("❌ Cancelado."); return ConversationHandler.END
    if q.data.startswith("ts_"):
        v = q.data.replace("ts_", ""); n = next((x for x,y in TIPOS_SISBEN if y==v), v)
    elif q.data.startswith("tr_"):
        v = q.data.replace("tr_", ""); n = next((x for x,y in TIPOS_RUAF if y==v), v)
    else: await q.edit_message_text("❌ Cancelado."); return ConversationHandler.END
    context.user_data["tipo_doc"] = v; context.user_data["tipo_nombre"] = n
    if context.user_data.get("modulo") == "ruaf":
        await q.edit_message_text(f"🏥 *RUAF* | *{n}*\n\nIngresa el número de documento:",
            parse_mode="Markdown")
    else:
        await q.edit_message_text(f"📄 Tipo: *{n}*\n\nIngresa el número de documento:",
            parse_mode="Markdown")
    return ING_NUMERO


async def ing_numero(update: Update, context: ContextTypes.DEFAULT_TYPE):
    numero = update.message.text.strip()
    if not numero or not numero.replace("-","").replace(" ","").isalnum():
        await update.message.reply_text("⚠️ Número inválido. Intenta de nuevo:"); return ING_NUMERO
    context.user_data["numero"] = numero
    if context.user_data.get("modulo") == "ruaf":
        await update.message.reply_text(
            "📅 Ingresa la *fecha de expedición* de la cédula:\n_(Formato: DD/MM/YYYY — Ej: 15/03/2010)_",
            parse_mode="Markdown"); return ING_FECHA
    await _ejecutar(update, context, numero)
    return ConversationHandler.END


async def ing_fecha(update: Update, context: ContextTypes.DEFAULT_TYPE):
    fecha = update.message.text.strip()
    if not re.match(r'^\d{2}/\d{2}/\d{4}$', fecha):
        await update.message.reply_text("⚠️ Formato incorrecto. Usa DD/MM/YYYY\nEj: 15/03/2010")
        return ING_FECHA
    context.user_data["fecha_exp"] = fecha
    await _ejecutar(update, context, context.user_data["numero"])
    return ConversationHandler.END


async def ing_placa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _ejecutar(update, context, update.message.text.strip())
    return ConversationHandler.END


async def _ejecutar(update, context, valor):
    modulo = context.user_data.get("modulo", "")
    tipo   = context.user_data.get("tipo_doc", "3")
    tipo_n = context.user_data.get("tipo_nombre", "Cédula")
    fecha  = context.user_data.get("fecha_exp", "")
    nombres = {
        "sisben": "SISBEN IV", "ruaf": "RUAF/SISPRO",
        "rama": "Rama Judicial", "simit": "SIMIT", "dian": "DIAN RUT"
    }
    msg = await update.message.reply_text(
        f"⏳ Consultando *{nombres.get(modulo, modulo)}*...\n_Esto puede tardar ~20 segundos_",
        parse_mode="Markdown")
    if   modulo == "sisben": res = await asyncio.to_thread(consultar_sisben, tipo, valor);       txt = fmt_sisben(res)
    elif modulo == "ruaf":   res = await asyncio.to_thread(consultar_ruaf, tipo, valor, fecha);  txt = fmt_ruaf(res, valor)
    elif modulo == "rama":   res = await asyncio.to_thread(consultar_rama_judicial, valor);       txt = fmt_rama(res, valor)
    elif modulo == "simit":  res = await asyncio.to_thread(consultar_simit, valor);               txt = fmt_simit(res, valor)
    elif modulo == "dian":   res = await asyncio.to_thread(consultar_dian_rut, valor);            txt = fmt_dian(res, valor)
    else: res = None; txt = "❌ Módulo desconocido."
    await msg.edit_text(txt, parse_mode="Markdown")
    await _notificar(update, context, nombres.get(modulo, modulo), tipo_n, valor, res)


async def _notificar(update, context, modulo, tipo, valor, resultado):
    db = cargar_db()
    db["consultas"] = db.get("consultas", 0) + 1
    guardar_db(db)
    u = update.effective_user
    ok = resultado is not None and isinstance(resultado, dict) and "error" not in resultado
    for aid in db["admins"]:
        try:
            await context.bot.send_message(
                chat_id=aid,
                text=(f"📌 *Nueva Consulta*\n\n"
                      f"👤 [{u.full_name}](tg://user?id={u.id})\n"
                      f"🆔 `{u.id}`\n"
                      f"📡 *Módulo:* {modulo}\n"
                      f"📄 *Tipo:* {tipo}\n"
                      f"🔢 *Valor:* `{valor}`\n"
                      f"{'✅ Encontrado' if ok else '❌ No encontrado'}"),
                parse_mode="Markdown")
        except: pass

# ══════════════════════════════════════════════════════════
#  PANEL ADMIN
# ══════════════════════════════════════════════════════════
async def adminpanel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not es_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Sin permisos."); return
    db = cargar_db()
    await update.message.reply_text(
        f"🔐 *Panel de Administración*\n\n"
        f"🛡 Admins: {len(db['admins'])}  |  👥 Usuarios: {len(db.get('usuarios', {}))}\n\nElige:",
        reply_markup=teclado_panel(), parse_mode="Markdown")


async def panel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    uid = q.from_user.id
    if not es_admin(uid): await q.edit_message_text("⛔ Sin permisos."); return
    db = cargar_db(); data = q.data
    VOLVER = [[InlineKeyboardButton("🔙 Volver", callback_data="panel_volver")]]

    if data == "panel_volver":
        await q.edit_message_text(
            f"🔐 *Panel de Administración*\n\n"
            f"🛡 Admins: {len(db['admins'])}  |  👥 Usuarios: {len(db.get('usuarios', {}))}\n\nElige:",
            reply_markup=teclado_panel(), parse_mode="Markdown")

    elif data == "panel_stats":
        usuarios = db.get("usuarios", {})
        activos = sum(1 for u in usuarios if es_activo(int(u)))
        await q.edit_message_text(
            f"📊 *Estadísticas*\n\n"
            f"👑 Owner: `{OWNER_ID}`\n"
            f"🛡 Admins: {len(db['admins'])}\n"
            f"👥 Usuarios: {len(usuarios)} ({activos} activos)\n"
            f"🔍 Consultas: {db.get('consultas', 0)}\n",
            reply_markup=InlineKeyboardMarkup(VOLVER), parse_mode="Markdown")

    elif data == "panel_admins":
        lista = "\n".join([f"  • `{a}`" + (" 👑" if a==OWNER_ID else "") for a in db["admins"]])
        btns = [[InlineKeyboardButton("➕ Agregar", callback_data="add_admin")]]
        if es_owner(uid) and any(a != OWNER_ID for a in db["admins"]):
            btns.append([InlineKeyboardButton("➖ Eliminar", callback_data="del_list_admin")])
        btns += VOLVER
        await q.edit_message_text(f"🛡 *Admins* ({len(db['admins'])}):\n{lista}",
            reply_markup=InlineKeyboardMarkup(btns), parse_mode="Markdown")

    elif data == "panel_usuarios":
        usuarios = db.get("usuarios", {})
        if usuarios:
            lines = []
            for uid_s, info in usuarios.items():
                ok = es_activo(int(uid_s))
                exp = "♾" if not info.get("expira") else datetime.fromisoformat(info["expira"]).strftime("%d/%m/%y")
                lines.append(f"  {'✅' if ok else '❌'} `{uid_s}` — {info['nombre_plan']} ({exp})")
            lista_txt = "\n".join(lines)
        else:
            lista_txt = "  _Sin usuarios registrados_"
        btns = [[InlineKeyboardButton("➕ Agregar Usuario", callback_data="add_usuario")]]
        if usuarios: btns.append([InlineKeyboardButton("➖ Eliminar Usuario", callback_data="del_list_usuario")])
        btns += VOLVER
        await q.edit_message_text(f"👥 *Usuarios* ({len(usuarios)}):\n{lista_txt}",
            reply_markup=InlineKeyboardMarkup(btns), parse_mode="Markdown")

    elif data == "add_admin":
        context.user_data["accion"] = "agregar_admin"
        await q.edit_message_text("➕ Envía el *ID de Telegram* del nuevo admin:\n_(o /cancelar)_",
            parse_mode="Markdown")

    elif data == "add_usuario":
        context.user_data["accion"] = "agregar_usuario_id"
        await q.edit_message_text("➕ Envía el *ID de Telegram* del nuevo usuario:\n_(o /cancelar)_",
            parse_mode="Markdown")

    elif data.startswith("plan_"):
        plan_key = data.replace("plan_", "")
        target = context.user_data.get("usuario_target")
        if target and plan_key in PLANES:
            agregar_usuario_plan(target, plan_key)
            await q.edit_message_text(
                f"✅ Usuario `{target}` activado con plan *{PLANES[plan_key]['nombre']}*",
                reply_markup=InlineKeyboardMarkup(VOLVER), parse_mode="Markdown")
            context.user_data.pop("usuario_target", None)
            context.user_data.pop("accion", None)

    elif data == "del_list_admin":
        if not es_owner(uid): await q.answer("⛔ Solo el owner puede hacer esto.", show_alert=True); return
        elim = [a for a in db["admins"] if a != OWNER_ID]
        if not elim: await q.answer("No hay admins para eliminar.", show_alert=True); return
        btns = [[InlineKeyboardButton(f"🗑 {a}", callback_data=f"del_admin_{a}")] for a in elim] + VOLVER
        await q.edit_message_text("Selecciona el admin a *eliminar*:",
            reply_markup=InlineKeyboardMarkup(btns), parse_mode="Markdown")

    elif data == "del_list_usuario":
        usuarios = db.get("usuarios", {})
        if not usuarios: await q.answer("Sin usuarios.", show_alert=True); return
        btns = [[InlineKeyboardButton(f"🗑 {u}", callback_data=f"del_usuario_{u}")] for u in usuarios] + VOLVER
        await q.edit_message_text("Selecciona el usuario a *eliminar*:",
            reply_markup=InlineKeyboardMarkup(btns), parse_mode="Markdown")

    elif data.startswith("del_admin_"):
        if not es_owner(uid): await q.answer("⛔ Solo el owner.", show_alert=True); return
        target = int(data.replace("del_admin_", ""))
        db["admins"] = [a for a in db["admins"] if a != target]; guardar_db(db)
        await q.edit_message_text(f"✅ Admin `{target}` eliminado.",
            reply_markup=InlineKeyboardMarkup(VOLVER), parse_mode="Markdown")

    elif data.startswith("del_usuario_"):
        target = data.replace("del_usuario_", "")
        eliminar_usuario(int(target))
        await q.edit_message_text(f"✅ Usuario `{target}` eliminado.",
            reply_markup=InlineKeyboardMarkup(VOLVER), parse_mode="Markdown")


async def recibir_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    accion = context.user_data.get("accion")
    if not es_admin(uid) or not accion: return
    try: nuevo_id = int(update.message.text.strip())
    except: await update.message.reply_text("⚠️ ID inválido. Debe ser un número."); return
    db = cargar_db()
    if accion == "agregar_admin":
        if nuevo_id in db["admins"]:
            await update.message.reply_text(f"ℹ️ `{nuevo_id}` ya es admin.", parse_mode="Markdown")
        else:
            db["admins"].append(nuevo_id); guardar_db(db)
            await update.message.reply_text(f"✅ Admin `{nuevo_id}` agregado 🛡", parse_mode="Markdown")
        context.user_data.pop("accion", None)
    elif accion == "agregar_usuario_id":
        context.user_data["usuario_target"] = nuevo_id
        context.user_data["accion"] = "eligiendo_plan"
        await update.message.reply_text(
            f"👤 ID: `{nuevo_id}`\n\n📋 *Selecciona el plan de acceso:*",
            reply_markup=menu_planes(), parse_mode="Markdown")


async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Cancelado.")
    return ConversationHandler.END

# ══════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════
def main():
    app = Application.builder().token(TOKEN).build()
    conv = ConversationHandler(
        entry_points=[CommandHandler("consultar", consultar)],
        states={
            SEL_MODULO: [CallbackQueryHandler(sel_modulo)],
            SEL_TIPO:   [CallbackQueryHandler(sel_tipo)],
            ING_NUMERO: [MessageHandler(filters.TEXT & ~filters.COMMAND, ing_numero)],
            ING_FECHA:  [MessageHandler(filters.TEXT & ~filters.COMMAND, ing_fecha)],
            ING_PLACA:  [MessageHandler(filters.TEXT & ~filters.COMMAND, ing_placa)],
        },
        fallbacks=[CommandHandler("cancelar", cancelar)],
        per_message=False,
    )
    app.add_handler(CommandHandler("start",      start))
    app.add_handler(CommandHandler("info",       info_bot))
    app.add_handler(CommandHandler("ayuda",      ayuda))
    app.add_handler(CommandHandler("stats",      stats))
    app.add_handler(CommandHandler("adminpanel", adminpanel))
    app.add_handler(conv)
    app.add_handler(CallbackQueryHandler(panel_callback, pattern="^(panel_|add_|del_|plan_)"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_id))
    logger.info("✅ Bot Colombia iniciado | Owner: %s", OWNER_ID)
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
