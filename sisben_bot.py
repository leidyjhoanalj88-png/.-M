#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Bot Colombia - Consultas Gobierno Real
Módulos: SISBEN IV | RUAF/SISPRO | Rama Judicial | SIMIT | DIAN RUT
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
from selenium.common.exceptions import TimeoutException, NoSuchElementException

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

# Estados conversación
(SEL_MODULO, SEL_TIPO, ING_NUMERO,
 ING_FECHA, ING_PLACA, ING_NOMBRE,
 ESP_ADM_ID, ESP_USR_ID) = range(8)

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

TIPOS_SISBEN = [
    ("Registro Civil","1"),      ("Tarjeta de Identidad","2"),
    ("Cedula de Ciudadania","3"),("Cedula de Extranjeria","4"),
    ("DNI Pais de Origen","5"),  ("DNI Pasaporte","6"),
    ("Salvoconducto Refugiado","7"),("Permiso Esp. Permanencia","8"),
    ("Permiso Protec. Temporal","9"),
]
TIPOS_RUAF = [
    ("Cédula de Ciudadanía","CC"),("Tarjeta de Identidad","TI"),
    ("Registro Civil","RC"),      ("Cédula de Extranjería","CE"),
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
    db = {"admins":[OWNER_ID], "usuarios":{}, "consultas":0}
    guardar_db(db); return db

def guardar_db(db):
    with open(DB_FILE,"w") as f: json.dump(db,f,indent=2)

def es_owner(uid): return uid == OWNER_ID
def es_admin(uid):
    db = cargar_db()
    return uid == OWNER_ID or uid in db["admins"]
def es_activo(uid):
    if es_admin(uid): return True
    db = cargar_db()
    info = db.get("usuarios",{}).get(str(uid))
    if not info: return False
    if info.get("plan") == "permanente": return True
    exp = info.get("expira")
    return bool(exp and datetime.now() < datetime.fromisoformat(exp))
def agregar_usuario_plan(uid, plan_key):
    db = cargar_db()
    if "usuarios" not in db: db["usuarios"] = {}
    plan = PLANES[plan_key]
    exp = None if plan_key=="permanente" else (datetime.now()+timedelta(days=plan["dias"])).isoformat()
    db["usuarios"][str(uid)] = {"plan":plan_key,"nombre_plan":plan["nombre"],"expira":exp,"desde":datetime.now().isoformat()}
    guardar_db(db)
def eliminar_usuario(uid):
    db = cargar_db()
    db.get("usuarios",{}).pop(str(uid),None)
    guardar_db(db)

# ══════════════════════════════════════════════════════════
#  SELENIUM DRIVER
# ══════════════════════════════════════════════════════════
def get_driver():
    opts = Options()
    for a in ["--headless=new","--no-sandbox","--disable-dev-shm-usage",
              "--disable-gpu","--disable-extensions",
              "--blink-settings=imagesEnabled=false",
              "--window-size=1920,1080","--log-level=3"]:
        opts.add_argument(a)
    opts.add_experimental_option("excludeSwitches",["enable-logging","enable-automation"])
    opts.add_experimental_option("useAutomationExtension",False)
    cb = os.environ.get("CHROME_BIN")
    if not cb:
        for p in ["/usr/bin/chromium","/usr/bin/chromium-browser","/usr/bin/google-chrome"]:
            if os.path.exists(p): cb=p; break
    if not cb:
        r=glob.glob("/nix/store/*/bin/chromium*")
        if r: cb=sorted(r)[0]
    if cb: opts.binary_location=cb
    cd = os.environ.get("CHROMEDRIVER_PATH")
    if not cd:
        for p in ["/usr/bin/chromedriver","/usr/bin/chromium-driver","/usr/lib/chromium/chromedriver"]:
            if os.path.exists(p): cd=p; break
    if not cd:
        r=glob.glob("/nix/store/*/bin/chromedriver*")
        if r: cd=sorted(r)[0]
    return webdriver.Chrome(service=Service(cd),options=opts) if cd else webdriver.Chrome(options=opts)

# ══════════════════════════════════════════════════════════
#  MÓDULO 1 - SISBEN IV
# ══════════════════════════════════════════════════════════
def consultar_sisben(tipo, numero):
    driver=None
    try:
        driver=get_driver(); driver.set_page_load_timeout(30)
        driver.get("https://reportes.sisben.gov.co/DNP_SisbenConsulta")
        time.sleep(5)
        wait=WebDriverWait(driver,20)
        Select(wait.until(EC.presence_of_element_located((By.ID,"TipoID")))).select_by_value(tipo)
        time.sleep(1)
        inp=driver.find_element(By.ID,"documento"); inp.clear(); inp.send_keys(numero)
        time.sleep(1)
        driver.execute_script("arguments[0].click();",driver.find_element(By.ID,"botonenvio"))
        time.sleep(8)
        html=driver.page_source
        if "no se encontr" in html.lower() or "no registra" in html.lower(): return None
        r={}
        try: r["grupo"]=driver.find_element(By.XPATH,"//p[contains(@class,'text-uppercase') and contains(@class,'text-white')]").text.strip()
        except: pass
        try: r["clasificacion"]=driver.find_element(By.XPATH,"//div[contains(@class,'imagenpuntaje')]//p[contains(@style,'18px')]").text.strip()
        except: pass
        for label,key in [("Nombres","nombres"),("Apellidos","apellidos"),("Municipio","municipio"),
                          ("Departamento","departamento"),("Ficha","ficha"),
                          ("Fecha de consulta","fecha"),("Encuesta vigente","encuesta")]:
            try:
                v=driver.find_element(By.XPATH,f"//p[contains(text(),'{label}')]/following-sibling::p[1]").text.strip()
                if v: r[key]=" ".join(v.split())
            except: pass
        return r if r else None
    except TimeoutException: return {"error":"Tiempo de espera agotado"}
    except Exception as e: return {"error":str(e)}
    finally:
        if driver:
            try: driver.quit()
            except: pass

def fmt_sisben(r):
    if r is None: return "❌ *NO ENCONTRADO*\n\nDocumento no registrado en SISBEN IV."
    if "error" in r: return f"⚠️ *Error:* `{r['error']}`"
    m ="╔════════════════════════════════╗\n"
    m+="║      MÓDULO SISBEN IV          ║\n"
    m+="╚════════════════════════════════╝\n\n"
    if "grupo" in r:          m+=f"🏷 *GRUPO:* {r['grupo']}\n"
    if "clasificacion" in r:  m+=f"📊 *Puntaje:* {r['clasificacion']}\n"
    m+="\n👤 *DATOS PERSONALES*\n──────────────────────\n"
    for k,l in [("nombres","Nombres"),("apellidos","Apellidos"),("municipio","Municipio"),("departamento","Depto")]:
        if k in r: m+=f"  • *{l}:* {r[k]}\n"
    if any(k in r for k in ["ficha","fecha","encuesta"]):
        m+="\n📋 *REGISTRO*\n──────────────────────\n"
        for k,l in [("ficha","Ficha"),("fecha","Fecha"),("encuesta","Encuesta")]:
            if k in r: m+=f"  • *{l}:* {r[k]}\n"
    return m

# ══════════════════════════════════════════════════════════
#  MÓDULO 2 - RUAF / SISPRO  (EPS + Pensión + ARL + Cesantías)
# ══════════════════════════════════════════════════════════
def consultar_ruaf(tipo_doc, numero, fecha_exp):
    """fecha_exp formato: DD/MM/YYYY"""
    driver=None
    try:
        driver=get_driver(); driver.set_page_load_timeout(40)
        driver.get("https://ruaf.sispro.gov.co/")
        time.sleep(4)
        wait=WebDriverWait(driver,20)

        # Aceptar términos
        try:
            btn_acepto=wait.until(EC.element_to_be_clickable((By.XPATH,"//input[@value='Acepto'] | //button[contains(text(),'Acepto')] | //a[contains(text(),'Acepto')]")))
            btn_acepto.click(); time.sleep(1)
            try:
                btn_enviar=driver.find_element(By.XPATH,"//input[@value='Enviar'] | //button[contains(text(),'Enviar')]")
                btn_enviar.click(); time.sleep(2)
            except: pass
        except: pass

        # Seleccionar tipo documento
        try:
            sel=wait.until(EC.presence_of_element_located((By.XPATH,"//select[contains(@id,'tipo') or contains(@name,'tipo') or contains(@id,'TipoDocumento')]")))
            Select(sel).select_by_value(tipo_doc)
        except:
            try:
                sels=driver.find_elements(By.TAG_NAME,"select")
                if sels: Select(sels[0]).select_by_value(tipo_doc)
            except: pass
        time.sleep(0.5)

        # Número documento
        try:
            inp_num=driver.find_element(By.XPATH,"//input[contains(@id,'numero') or contains(@id,'Numero') or contains(@id,'documento')]")
        except:
            inputs=[i for i in driver.find_elements(By.XPATH,"//input[@type='text']")]
            inp_num=inputs[0] if inputs else None
        if inp_num: inp_num.clear(); inp_num.send_keys(numero)
        time.sleep(0.5)

        # Fecha expedición
        try:
            inp_fecha=driver.find_element(By.XPATH,"//input[contains(@id,'fecha') or contains(@id,'Fecha') or contains(@id,'expedicion')]")
            inp_fecha.clear(); inp_fecha.send_keys(fecha_exp)
        except:
            inputs=[i for i in driver.find_elements(By.XPATH,"//input[@type='text']")]
            if len(inputs)>1: inputs[1].clear(); inputs[1].send_keys(fecha_exp)
        time.sleep(0.5)

        # Botón consultar
        try:
            btn=driver.find_element(By.XPATH,"//input[@value='Consultar'] | //button[contains(text(),'Consultar')]")
            driver.execute_script("arguments[0].click();",btn)
        except:
            btns=driver.find_elements(By.XPATH,"//input[@type='submit'] | //button[@type='submit']")
            if btns: driver.execute_script("arguments[0].click();",btns[-1])
        time.sleep(10)

        html=driver.page_source
        if "no se encontr" in html.lower() or "no existen" in html.lower(): return None

        r={}
        # Nombre
        try:
            nombre_el=driver.find_element(By.XPATH,"//td[contains(text(),'Nombre')]/following-sibling::td | //span[contains(@class,'nombre')]")
            r["nombre"]=nombre_el.text.strip()
        except: pass

        # Afiliaciones por sistema
        sistemas=["Salud","Pensión","Riesgos Laborales","Cesantías","Caja Compensación","Subsidio Familiar"]
        for sis in sistemas:
            try:
                fila=driver.find_element(By.XPATH,f"//tr[contains(.,'{sis}')]")
                celdas=fila.find_elements(By.TAG_NAME,"td")
                if len(celdas)>=3:
                    r[sis]={
                        "entidad": celdas[1].text.strip() if len(celdas)>1 else "",
                        "estado": celdas[2].text.strip() if len(celdas)>2 else "",
                        "regimen": celdas[3].text.strip() if len(celdas)>3 else "",
                    }
            except: pass

        # Si no se extrajo estructura, intentar texto plano
        if not r:
            try:
                tabla=driver.find_element(By.XPATH,"//table[contains(@class,'result') or contains(@id,'result') or contains(@class,'afil')]")
                r["raw"]=tabla.text[:1000]
            except:
                body=driver.find_element(By.TAG_NAME,"body").text
                if len(body)>200: r["raw"]=body[:1500]
        return r if r else None
    except TimeoutException: return {"error":"Tiempo de espera agotado"}
    except Exception as e: return {"error":str(e)}
    finally:
        if driver:
            try: driver.quit()
            except: pass

def fmt_ruaf(r, numero):
    if r is None: return "❌ *NO ENCONTRADO*\n\nDocumento no registrado en RUAF/SISPRO."
    if "error" in r: return f"⚠️ *Error:* `{r['error']}`"
    m ="╔════════════════════════════════╗\n"
    m+="║   MÓDULO RUAF / SISPRO         ║\n"
    m+="╚════════════════════════════════╝\n\n"
    m+=f"🔢 *Documento:* `{numero}`\n"
    if "nombre" in r: m+=f"👤 *Nombre:* {r['nombre']}\n"
    sistemas=["Salud","Pensión","Riesgos Laborales","Cesantías","Caja Compensación","Subsidio Familiar"]
    iconos={"Salud":"🏥","Pensión":"🏦","Riesgos Laborales":"🦺","Cesantías":"💰","Caja Compensación":"🏠","Subsidio Familiar":"👨‍👩‍👧"}
    found=False
    for sis in sistemas:
        if sis in r:
            found=True
            d=r[sis]
            m+=f"\n{iconos.get(sis,'📋')} *{sis}*\n"
            m+="──────────────────────\n"
            if d.get("entidad"): m+=f"  🏢 *Entidad:* {d['entidad']}\n"
            if d.get("estado"):
                emoji="🟢" if "activ" in d["estado"].lower() else "🔴"
                m+=f"  📌 *Estado:* {emoji} {d['estado']}\n"
            if d.get("regimen"): m+=f"  📋 *Régimen:* {d['regimen']}\n"
    if not found and "raw" in r:
        m+=f"\n📄 *Datos encontrados:*\n`{r['raw'][:800]}`\n"
    return m

# ══════════════════════════════════════════════════════════
#  MÓDULO 3 - RAMA JUDICIAL (procesos por cédula)
# ══════════════════════════════════════════════════════════
def consultar_rama_judicial(numero_doc):
    driver=None
    try:
        driver=get_driver(); driver.set_page_load_timeout(40)
        # CPNU - Consulta de Procesos Nacional Unificada
        driver.get("https://consultaprocesos.ramajudicial.gov.co/procesos/NombreRazonSocial")
        time.sleep(5)
        wait=WebDriverWait(driver,25)

        # Buscar por número de documento (sujeto procesal)
        try:
            # Intentar tab de cédula/documento
            tab=driver.find_element(By.XPATH,"//a[contains(text(),'Número Identificación') or contains(text(),'Cedula') or contains(text(),'Documento')]")
            tab.click(); time.sleep(1)
        except: pass

        try:
            inp=wait.until(EC.presence_of_element_located((By.XPATH,
                "//input[@type='text' and (@placeholder or @id or @name)]")))
            inp.clear(); inp.send_keys(numero_doc)
        except:
            inputs=driver.find_elements(By.XPATH,"//input[@type='text']")
            if inputs: inputs[0].clear(); inputs[0].send_keys(numero_doc)
        time.sleep(0.5)

        try:
            btn=driver.find_element(By.XPATH,"//button[contains(text(),'Buscar') or contains(text(),'Consultar')] | //input[@type='submit']")
            driver.execute_script("arguments[0].click();",btn)
        except:
            btns=driver.find_elements(By.TAG_NAME,"button")
            if btns: driver.execute_script("arguments[0].click();",btns[-1])
        time.sleep(8)

        html=driver.page_source
        if "no se encontr" in html.lower() or "sin result" in html.lower() or "0 resultados" in html.lower():
            return None

        procesos=[]
        try:
            filas=driver.find_elements(By.XPATH,"//tr[td]")
            for fila in filas[:10]:
                celdas=fila.find_elements(By.TAG_NAME,"td")
                if len(celdas)>=2:
                    texto=" | ".join([c.text.strip() for c in celdas if c.text.strip()])
                    if texto: procesos.append(texto)
        except: pass

        if not procesos:
            try:
                items=driver.find_elements(By.XPATH,"//div[contains(@class,'proceso') or contains(@class,'result')]")
                for item in items[:5]:
                    if item.text.strip(): procesos.append(item.text.strip()[:300])
            except: pass

        return {"procesos":procesos} if procesos else {"raw": driver.find_element(By.TAG_NAME,"body").text[:1500]}
    except TimeoutException: return {"error":"Tiempo de espera agotado"}
    except Exception as e: return {"error":str(e)}
    finally:
        if driver:
            try: driver.quit()
            except: pass

def fmt_rama(r, doc):
    if r is None: return f"✅ *SIN PROCESOS*\n\nNo se encontraron procesos judiciales para el documento `{doc}`."
    if "error" in r: return f"⚠️ *Error:* `{r['error']}`"
    m ="╔════════════════════════════════╗\n"
    m+="║     MÓDULO RAMA JUDICIAL       ║\n"
    m+="╚════════════════════════════════╝\n\n"
    m+=f"🔢 *Documento:* `{doc}`\n\n"
    if "procesos" in r and r["procesos"]:
        m+=f"⚖️ *Procesos encontrados:* {len(r['procesos'])}\n\n"
        for i,p in enumerate(r["procesos"][:8],1):
            m+=f"*{i}.* `{p[:250]}`\n\n"
    elif "raw" in r:
        m+=f"📄 *Datos:*\n`{r['raw'][:1000]}`\n"
    return m

# ══════════════════════════════════════════════════════════
#  MÓDULO 4 - SIMIT (multas y comparendos de tránsito)
# ══════════════════════════════════════════════════════════
def consultar_simit(numero_doc_o_placa):
    driver=None
    try:
        driver=get_driver(); driver.set_page_load_timeout(40)
        driver.get("https://fcm.org.co/simit/#/estado-cuenta")
        time.sleep(5)
        wait=WebDriverWait(driver,20)

        try:
            inp=wait.until(EC.presence_of_element_located((By.XPATH,
                "//input[@type='text' or @type='search' or contains(@placeholder,'documento') or contains(@placeholder,'placa')]")))
            inp.clear(); inp.send_keys(numero_doc_o_placa)
        except:
            inputs=driver.find_elements(By.XPATH,"//input[@type='text']")
            if inputs: inputs[0].clear(); inputs[0].send_keys(numero_doc_o_placa)
        time.sleep(0.5)

        try:
            btn=driver.find_element(By.XPATH,"//button[contains(text(),'Buscar') or contains(text(),'Consultar') or contains(text(),'Ver')] | //input[@type='submit']")
            driver.execute_script("arguments[0].click();",btn)
        except:
            btns=driver.find_elements(By.TAG_NAME,"button")
            for b in btns:
                if any(t in b.text.lower() for t in ["buscar","consultar","ver"]):
                    driver.execute_script("arguments[0].click();",b); break
        time.sleep(8)

        html=driver.page_source
        if "no se encontr" in html.lower() or "sin multas" in html.lower() or "no tiene comparendos" in html.lower():
            return {"sin_multas": True}

        r={}
        try:
            total_el=driver.find_element(By.XPATH,"//span[contains(text(),'$')] | //td[contains(text(),'Total')]")
            r["total"]=total_el.text.strip()
        except: pass

        multas=[]
        try:
            filas=driver.find_elements(By.XPATH,"//tr[td]")
            for fila in filas[:15]:
                celdas=fila.find_elements(By.TAG_NAME,"td")
                if len(celdas)>=2:
                    texto=" | ".join([c.text.strip() for c in celdas if c.text.strip()])
                    if texto: multas.append(texto)
        except: pass

        if multas: r["multas"]=multas
        if not r:
            body=driver.find_element(By.TAG_NAME,"body").text
            if len(body)>100: r["raw"]=body[:1500]
        return r
    except TimeoutException: return {"error":"Tiempo de espera agotado"}
    except Exception as e: return {"error":str(e)}
    finally:
        if driver:
            try: driver.quit()
            except: pass

def fmt_simit(r, consulta):
    if "error" in r: return f"⚠️ *Error:* `{r['error']}`"
    if r.get("sin_multas"): return f"✅ *SIN MULTAS*\n\n`{consulta}` no tiene comparendos ni multas activas en SIMIT."
    m ="╔════════════════════════════════╗\n"
    m+="║    MÓDULO SIMIT - MULTAS       ║\n"
    m+="╚════════════════════════════════╝\n\n"
    m+=f"🔢 *Consultado:* `{consulta}`\n"
    if "total" in r: m+=f"💰 *Total deuda:* {r['total']}\n"
    if "multas" in r:
        m+=f"\n🚦 *Comparendos/Multas:*\n──────────────────────\n"
        for i,mul in enumerate(r["multas"][:10],1):
            m+=f"*{i}.* `{mul[:200]}`\n\n"
    elif "raw" in r:
        m+=f"\n📄 *Datos:*\n`{r['raw'][:1000]}`\n"
    return m

# ══════════════════════════════════════════════════════════
#  MÓDULO 5 - DIAN RUT
# ══════════════════════════════════════════════════════════
def consultar_dian_rut(nit_o_cedula):
    driver=None
    try:
        driver=get_driver(); driver.set_page_load_timeout(40)
        driver.get("https://muisca.dian.gov.co/WebRutMuisca/DefConsultaEstadoRUT.faces")
        time.sleep(5)
        wait=WebDriverWait(driver,20)

        try:
            inp=wait.until(EC.presence_of_element_located((By.XPATH,
                "//input[@type='text' and (contains(@id,'nit') or contains(@id,'numero') or contains(@id,'identificacion'))]")))
        except:
            inputs=driver.find_elements(By.XPATH,"//input[@type='text']")
            inp=inputs[0] if inputs else None

        if inp: inp.clear(); inp.send_keys(nit_o_cedula)
        time.sleep(0.5)

        try:
            btn=driver.find_element(By.XPATH,"//input[@type='submit'] | //button[@type='submit'] | //button[contains(text(),'Buscar')]")
            driver.execute_script("arguments[0].click();",btn)
        except:
            btns=driver.find_elements(By.TAG_NAME,"button")
            if btns: driver.execute_script("arguments[0].click();",btns[-1])
        time.sleep(7)

        html=driver.page_source
        if "no se encontr" in html.lower() or "no existe" in html.lower(): return None

        r={}
        for label,key in [("Nombre","nombre"),("Razón Social","razon_social"),("Estado","estado"),
                          ("Tipo","tipo"),("Dirección","direccion"),("Ciudad","ciudad"),
                          ("Departamento","departamento"),("Actividad","actividad")]:
            try:
                el=driver.find_element(By.XPATH,
                    f"//td[contains(text(),'{label}')]/following-sibling::td[1] | "
                    f"//label[contains(text(),'{label}')]/following-sibling::span[1]")
                v=el.text.strip()
                if v: r[key]=v
            except: pass

        if not r:
            try:
                tabla=driver.find_element(By.XPATH,"//table")
                r["raw"]=tabla.text[:1200]
            except:
                body=driver.find_element(By.TAG_NAME,"body").text
                if len(body)>200: r["raw"]=body[:1500]
        return r if r else None
    except TimeoutException: return {"error":"Tiempo de espera agotado"}
    except Exception as e: return {"error":str(e)}
    finally:
        if driver:
            try: driver.quit()
            except: pass

def fmt_dian(r, nit):
    if r is None: return f"❌ *NO ENCONTRADO*\n\nNIT/Cédula `{nit}` no registra en DIAN RUT."
    if "error" in r: return f"⚠️ *Error:* `{r['error']}`"
    m ="╔════════════════════════════════╗\n"
    m+="║       MÓDULO DIAN - RUT        ║\n"
    m+="╚════════════════════════════════╝\n\n"
    m+=f"🔢 *NIT/Cédula:* `{nit}`\n\n"
    for k,l,emoji in [("nombre","Nombre","👤"),("razon_social","Razón Social","🏢"),
                      ("estado","Estado","📌"),("tipo","Tipo Persona","🪪"),
                      ("actividad","Actividad Económica","🔧"),
                      ("direccion","Dirección","📍"),("ciudad","Ciudad","🏙"),("departamento","Depto","🗺")]:
        if k in r:
            if k=="estado":
                em="🟢" if "activ" in r[k].lower() else "🔴"
                m+=f"{emoji} *{l}:* {em} {r[k]}\n"
            else:
                m+=f"{emoji} *{l}:* {r[k]}\n"
    if "raw" in r and len(r)==1:
        m+=f"\n📄 *Datos:*\n`{r['raw'][:800]}`\n"
    return m

# ══════════════════════════════════════════════════════════
#  MENÚS TELEGRAM
# ══════════════════════════════════════════════════════════
def menu_modulos():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔎 SISBEN IV",          callback_data="m_sisben")],
        [InlineKeyboardButton("🏥 RUAF / EPS + Pensión + ARL", callback_data="m_ruaf")],
        [InlineKeyboardButton("⚖️ Rama Judicial",      callback_data="m_rama")],
        [InlineKeyboardButton("🚦 SIMIT (Multas/Placa)",callback_data="m_simit")],
        [InlineKeyboardButton("📋 DIAN - RUT",          callback_data="m_dian")],
        [InlineKeyboardButton("❌ Cancelar",             callback_data="cancelar")],
    ])

def menu_tipo_sisben():
    b,f=[],[]
    for n,v in TIPOS_SISBEN:
        f.append(InlineKeyboardButton(n,callback_data=f"ts_{v}"))
        if len(f)==2: b.append(f); f=[]
    if f: b.append(f)
    b.append([InlineKeyboardButton("❌ Cancelar",callback_data="cancelar")])
    return InlineKeyboardMarkup(b)

def menu_tipo_ruaf():
    b=[[InlineKeyboardButton(n,callback_data=f"tr_{v}")] for n,v in TIPOS_RUAF]
    b.append([InlineKeyboardButton("❌ Cancelar",callback_data="cancelar")])
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
        [InlineKeyboardButton("🛡 Gestionar Admins",   callback_data="panel_admins")],
        [InlineKeyboardButton("👥 Gestionar Usuarios",  callback_data="panel_usuarios")],
        [InlineKeyboardButton("📊 Estadísticas",        callback_data="panel_stats")],
    ])

# ══════════════════════════════════════════════════════════
#  HANDLERS GENERALES
# ══════════════════════════════════════════════════════════
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u=update.effective_user
    if not es_activo(u.id):
        db=cargar_db(); info=db.get("usuarios",{}).get(str(u.id))
        msg="⛔ *Plan vencido.*\n\nContacta al administrador para renovar." if info else "⛔ *Sin acceso.*\n\nContacta al administrador."
        await update.message.reply_text(msg,parse_mode="Markdown"); return
    txt=(f"👋 Hola *{u.first_name}*\n\n"
         "🤖 *Bot de Consultas Colombia*\n\n"
         "📡 *Módulos disponibles:*\n"
         "  🔎 SISBEN IV\n"
         "  🏥 RUAF (EPS + Pensión + ARL + Cesantías)\n"
         "  ⚖️ Rama Judicial (procesos)\n"
         "  🚦 SIMIT (multas/comparendos)\n"
         "  📋 DIAN (estado RUT)\n\n"
         "/consultar — Iniciar consulta\n"
         "/ayuda — Ayuda\n")
    if es_admin(u.id):
        txt+="\n🔐 *Admin:*\n  /adminpanel\n  /stats\n"
    else:
        info=cargar_db().get("usuarios",{}).get(str(u.id))
        if info:
            exp=info.get("expira")
            exp_txt="Permanente ♾" if not exp else datetime.fromisoformat(exp).strftime("%d/%m/%Y %H:%M")
            txt+=f"\n📋 *Plan:* {info['nombre_plan']}  |  ⏰ *Expira:* {exp_txt}\n"
    await update.message.reply_text(txt,parse_mode="Markdown")

async def ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *Ayuda*\n\n"
        "/consultar — Iniciar consulta\n"
        "/cancelar — Cancelar operación\n"
        "/ayuda — Este mensaje\n\n"
        "🔎 *SISBEN IV* → solo cédula\n"
        "🏥 *RUAF* → cédula + fecha expedición\n"
        "⚖️ *Rama Judicial* → cédula\n"
        "🚦 *SIMIT* → cédula o placa\n"
        "📋 *DIAN RUT* → NIT o cédula\n",
        parse_mode="Markdown")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not es_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Sin permisos."); return
    db=cargar_db()
    usuarios=db.get("usuarios",{})
    activos=sum(1 for uid in usuarios if es_activo(int(uid)))
    await update.message.reply_text(
        f"📊 *Estadísticas*\n\n"
        f"👑 Owner: `{OWNER_ID}`\n"
        f"🛡 Admins: {len(db['admins'])}\n"
        f"👥 Usuarios: {len(usuarios)} ({activos} activos)\n"
        f"🔍 Consultas totales: {db.get('consultas',0)}\n",
        parse_mode="Markdown")

# ══════════════════════════════════════════════════════════
#  FLUJO DE CONSULTA
# ══════════════════════════════════════════════════════════
async def consultar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not es_activo(update.effective_user.id):
        await update.message.reply_text("⛔ Sin acceso activo."); return ConversationHandler.END
    await update.message.reply_text("📡 *Selecciona el módulo:*",
        reply_markup=menu_modulos(),parse_mode="Markdown")
    return SEL_MODULO

async def sel_modulo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    data=q.data
    if data=="cancelar":
        await q.edit_message_text("❌ Cancelado."); return ConversationHandler.END

    if data=="m_sisben":
        context.user_data["modulo"]="sisben"
        await q.edit_message_text("🔎 *SISBEN IV*\n\nSelecciona tipo de documento:",
            reply_markup=menu_tipo_sisben(),parse_mode="Markdown")
        return SEL_TIPO

    elif data=="m_ruaf":
        context.user_data["modulo"]="ruaf"
        await q.edit_message_text("🏥 *RUAF / SISPRO*\n\nSelecciona tipo de documento:",
            reply_markup=menu_tipo_ruaf(),parse_mode="Markdown")
        return SEL_TIPO

    elif data=="m_rama":
        context.user_data["modulo"]="rama"
        await q.edit_message_text("⚖️ *Rama Judicial*\n\nIngresa el número de cédula:",
            parse_mode="Markdown")
        return ING_NUMERO

    elif data=="m_simit":
        context.user_data["modulo"]="simit"
        await q.edit_message_text("🚦 *SIMIT*\n\nIngresa cédula o placa del vehículo:\n_(Ej: 1076350826 o ABC123)_",
            parse_mode="Markdown")
        return ING_PLACA

    elif data=="m_dian":
        context.user_data["modulo"]="dian"
        await q.edit_message_text("📋 *DIAN - RUT*\n\nIngresa NIT o cédula:",
            parse_mode="Markdown")
        return ING_NUMERO

    return SEL_MODULO

async def sel_tipo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    if q.data=="cancelar":
        await q.edit_message_text("❌ Cancelado."); return ConversationHandler.END

    modulo=context.user_data.get("modulo","")
    if q.data.startswith("ts_"):
        v=q.data.replace("ts_",""); n=next((x for x,y in TIPOS_SISBEN if y==v),v)
    elif q.data.startswith("tr_"):
        v=q.data.replace("tr_",""); n=next((x for x,y in TIPOS_RUAF if y==v),v)
    else:
        await q.edit_message_text("❌ Cancelado."); return ConversationHandler.END

    context.user_data["tipo_doc"]=v
    context.user_data["tipo_nombre"]=n

    if modulo=="ruaf":
        await q.edit_message_text(
            f"🏥 *RUAF* | Tipo: *{n}*\n\nIngresa el número de documento:",
            parse_mode="Markdown")
        return ING_NUMERO
    else:
        await q.edit_message_text(
            f"📄 Tipo: *{n}*\n\nIngresa el número de documento:",
            parse_mode="Markdown")
        return ING_NUMERO

async def ing_numero(update: Update, context: ContextTypes.DEFAULT_TYPE):
    numero=update.message.text.strip()
    if not numero or not numero.replace("-","").replace(" ","").isalnum():
        await update.message.reply_text("⚠️ Número inválido. Intenta de nuevo:"); return ING_NUMERO

    modulo=context.user_data.get("modulo","")
    context.user_data["numero"]=numero

    if modulo=="ruaf":
        await update.message.reply_text(
            "📅 Ingresa la *fecha de expedición* de la cédula:\n_(formato: DD/MM/YYYY  ej: 15/03/2010)_",
            parse_mode="Markdown")
        return ING_FECHA

    # Para SISBEN, RAMA, DIAN ejecutar directamente
    await _ejecutar_consulta(update, context, numero)
    return ConversationHandler.END

async def ing_fecha(update: Update, context: ContextTypes.DEFAULT_TYPE):
    fecha=update.message.text.strip()
    if not re.match(r'^\d{2}/\d{2}/\d{4}$', fecha):
        await update.message.reply_text("⚠️ Formato incorrecto. Usa DD/MM/YYYY\nEj: 15/03/2010")
        return ING_FECHA
    context.user_data["fecha_exp"]=fecha
    await _ejecutar_consulta(update, context, context.user_data["numero"])
    return ConversationHandler.END

async def ing_placa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    valor=update.message.text.strip()
    await _ejecutar_consulta(update, context, valor)
    return ConversationHandler.END

async def _ejecutar_consulta(update, context, valor):
    modulo=context.user_data.get("modulo","")
    tipo=context.user_data.get("tipo_doc","3")
    tipo_n=context.user_data.get("tipo_nombre","Cédula")
    fecha=context.user_data.get("fecha_exp","")

    nombres={"sisben":"SISBEN IV","ruaf":"RUAF/SISPRO","rama":"Rama Judicial","simit":"SIMIT","dian":"DIAN RUT"}
    msg=await update.message.reply_text(f"⏳ Consultando *{nombres.get(modulo,modulo)}*...\n_(puede tardar ~20 seg)_",parse_mode="Markdown")

    if   modulo=="sisben": resultado=await asyncio.to_thread(consultar_sisben, tipo, valor);      texto=fmt_sisben(resultado)
    elif modulo=="ruaf":   resultado=await asyncio.to_thread(consultar_ruaf, tipo, valor, fecha); texto=fmt_ruaf(resultado,valor)
    elif modulo=="rama":   resultado=await asyncio.to_thread(consultar_rama_judicial, valor);     texto=fmt_rama(resultado,valor)
    elif modulo=="simit":  resultado=await asyncio.to_thread(consultar_simit, valor);             texto=fmt_simit(resultado,valor)
    elif modulo=="dian":   resultado=await asyncio.to_thread(consultar_dian_rut, valor);          texto=fmt_dian(resultado,valor)
    else: texto="❌ Módulo desconocido."; resultado=None

    await msg.edit_text(texto,parse_mode="Markdown")
    await _notificar(update, context, nombres.get(modulo,modulo), tipo_n, valor, resultado)

async def _notificar(update, context, modulo, tipo, valor, resultado):
    db=cargar_db()
    db["consultas"]=db.get("consultas",0)+1
    guardar_db(db)
    u=update.effective_user
    encontrado=resultado is not None and isinstance(resultado,dict) and "error" not in resultado
    for aid in db["admins"]:
        try:
            await context.bot.send_message(chat_id=aid,
                text=(f"📌 *Nueva Consulta*\n\n"
                      f"👤 [{u.full_name}](tg://user?id={u.id})\n"
                      f"🆔 `{u.id}`\n"
                      f"📡 *Módulo:* {modulo}\n"
                      f"📄 *Tipo:* {tipo}\n"
                      f"🔢 *Valor:* `{valor}`\n"
                      f"{'✅ Encontrado' if encontrado else '❌ No encontrado'}"),
                parse_mode="Markdown")
        except: pass

# ══════════════════════════════════════════════════════════
#  PANEL ADMIN
# ══════════════════════════════════════════════════════════
async def adminpanel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not es_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Sin permisos."); return
    db=cargar_db()
    await update.message.reply_text(
        f"🔐 *Panel de Administración*\n\n"
        f"🛡 Admins: {len(db['admins'])}  |  👥 Usuarios: {len(db.get('usuarios',{}))}\n\nElige:",
        reply_markup=teclado_panel(),parse_mode="Markdown")

async def panel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    uid=q.from_user.id
    if not es_admin(uid): await q.edit_message_text("⛔ Sin permisos."); return
    db=cargar_db()
    data=q.data
    VOLVER=[[InlineKeyboardButton("🔙 Volver",callback_data="panel_volver")]]

    if data=="panel_volver":
        await q.edit_message_text(
            f"🔐 *Panel de Administración*\n\n"
            f"🛡 Admins: {len(db['admins'])}  |  👥 Usuarios: {len(db.get('usuarios',{}))}\n\nElige:",
            reply_markup=teclado_panel(),parse_mode="Markdown")

    elif data=="panel_stats":
        usuarios=db.get("usuarios",{})
        activos=sum(1 for u in usuarios if es_activo(int(u)))
        await q.edit_message_text(
            f"📊 *Estadísticas*\n\n👑 Owner: `{OWNER_ID}`\n🛡 Admins: {len(db['admins'])}\n"
            f"👥 Usuarios: {len(usuarios)} ({activos} activos)\n🔍 Consultas: {db.get('consultas',0)}\n",
            reply_markup=InlineKeyboardMarkup(VOLVER),parse_mode="Markdown")

    elif data=="panel_admins":
        lista="\n".join([f"  • `{a}`"+(" 👑" if a==OWNER_ID else "") for a in db["admins"]])
        btns=[[InlineKeyboardButton("➕ Agregar Admin",callback_data="add_admin")]]
        if es_owner(uid) and any(a!=OWNER_ID for a in db["admins"]):
            btns.append([InlineKeyboardButton("➖ Eliminar Admin",callback_data="del_list_admin")])
        btns+=VOLVER
        await q.edit_message_text(f"🛡 *Admins* ({len(db['admins'])}):\n{lista}",
            reply_markup=InlineKeyboardMarkup(btns),parse_mode="Markdown")

    elif data=="panel_usuarios":
        usuarios=db.get("usuarios",{})
        if usuarios:
            lines=[]
            for uid_str,info in usuarios.items():
                ok=es_activo(int(uid_str))
                exp="♾" if not info.get("expira") else datetime.fromisoformat(info["expira"]).strftime("%d/%m/%y")
                lines.append(f"  {'✅' if ok else '❌'} `{uid_str}` — {info['nombre_plan']} ({exp})")
            lista_txt="\n".join(lines)
        else:
            lista_txt="  _Sin usuarios_"
        btns=[[InlineKeyboardButton("➕ Agregar Usuario",callback_data="add_usuario")]]
        if usuarios: btns.append([InlineKeyboardButton("➖ Eliminar Usuario",callback_data="del_list_usuario")])
        btns+=VOLVER
        await q.edit_message_text(f"👥 *Usuarios* ({len(usuarios)}):\n{lista_txt}",
            reply_markup=InlineKeyboardMarkup(btns),parse_mode="Markdown")

    elif data=="add_admin":
        context.user_data["accion"]="agregar_admin"
        await q.edit_message_text("➕ Envía el *ID de Telegram* del nuevo admin:\n_(o /cancelar)_",parse_mode="Markdown")

    elif data=="add_usuario":
        context.user_data["accion"]="agregar_usuario_id"
        await q.edit_message_text("➕ Envía el *ID de Telegram* del nuevo usuario:\n_(o /cancelar)_",parse_mode="Markdown")

    elif data.startswith("plan_"):
        plan_key=data.replace("plan_","")
        target=context.user_data.get("usuario_target")
        if target and plan_key in PLANES:
            agregar_usuario_plan(target,plan_key)
            await q.edit_message_text(f"✅ Usuario `{target}` — plan *{PLANES[plan_key]['nombre']}* activado.",
                reply_markup=InlineKeyboardMarkup(VOLVER),parse_mode="Markdown")
            context.user_data.pop("usuario_target",None); context.user_data.pop("accion",None)

    elif data=="del_list_admin":
        if not es_owner(uid): await q.answer("⛔ Solo el owner.",show_alert=True); return
        elim=[a for a in db["admins"] if a!=OWNER_ID]
        if not elim: await q.answer("No hay admins para eliminar.",show_alert=True); return
        btns=[[InlineKeyboardButton(f"🗑 {a}",callback_data=f"del_admin_{a}")] for a in elim]+VOLVER
        await q.edit_message_text("Selecciona admin a *eliminar*:",
            reply_markup=InlineKeyboardMarkup(btns),parse_mode="Markdown")

    elif data=="del_list_usuario":
        usuarios=db.get("usuarios",{})
        if not usuarios: await q.answer("Sin usuarios.",show_alert=True); return
        btns=[[InlineKeyboardButton(f"🗑 {u}",callback_data=f"del_usuario_{u}")] for u in usuarios]+VOLVER
        await q.edit_message_text("Selecciona usuario a *eliminar*:",
            reply_markup=InlineKeyboardMarkup(btns),parse_mode="Markdown")

    elif data.startswith("del_admin_"):
        if not es_owner(uid): await q.answer("⛔ Solo el owner.",show_alert=True); return
        target=int(data.replace("del_admin_",""))
        db["admins"]=[a for a in db["admins"] if a!=target]; guardar_db(db)
        await q.edit_message_text(f"✅ Admin `{target}` eliminado.",
            reply_markup=InlineKeyboardMarkup(VOLVER),parse_mode="Markdown")

    elif data.startswith("del_usuario_"):
        target=data.replace("del_usuario_",""); eliminar_usuario(int(target))
        await q.edit_message_text(f"✅ Usuario `{target}` eliminado.",
            reply_markup=InlineKeyboardMarkup(VOLVER),parse_mode="Markdown")

async def recibir_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid=update.effective_user.id
    accion=context.user_data.get("accion")
    if not es_admin(uid) or not accion: return
    try: nuevo_id=int(update.message.text.strip())
    except: await update.message.reply_text("⚠️ ID inválido (número entero)."); return
    db=cargar_db()
    if accion=="agregar_admin":
        if nuevo_id in db["admins"]:
            await update.message.reply_text(f"ℹ️ `{nuevo_id}` ya es admin.",parse_mode="Markdown")
        else:
            db["admins"].append(nuevo_id); guardar_db(db)
            await update.message.reply_text(f"✅ Admin `{nuevo_id}` agregado 🛡",parse_mode="Markdown")
        context.user_data.pop("accion",None)
    elif accion=="agregar_usuario_id":
        context.user_data["usuario_target"]=nuevo_id
        context.user_data["accion"]="eligiendo_plan"
        await update.message.reply_text(f"👤 ID: `{nuevo_id}`\n\n📋 *Selecciona el plan:*",
            reply_markup=menu_planes(),parse_mode="Markdown")

async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Cancelado.")
    return ConversationHandler.END

# ══════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════
def main():
    app=Application.builder().token(TOKEN).build()
    conv=ConversationHandler(
        entry_points=[CommandHandler("consultar",consultar)],
        states={
            SEL_MODULO: [CallbackQueryHandler(sel_modulo)],
            SEL_TIPO:   [CallbackQueryHandler(sel_tipo)],
            ING_NUMERO: [MessageHandler(filters.TEXT&~filters.COMMAND,ing_numero)],
            ING_FECHA:  [MessageHandler(filters.TEXT&~filters.COMMAND,ing_fecha)],
            ING_PLACA:  [MessageHandler(filters.TEXT&~filters.COMMAND,ing_placa)],
        },
        fallbacks=[CommandHandler("cancelar",cancelar)],
        per_message=False,
    )
    app.add_handler(CommandHandler("start",     start))
    app.add_handler(CommandHandler("ayuda",     ayuda))
    app.add_handler(CommandHandler("stats",     stats))
    app.add_handler(CommandHandler("adminpanel",adminpanel))
    app.add_handler(conv)
    app.add_handler(CallbackQueryHandler(panel_callback,pattern="^(panel_|add_|del_|plan_)"))
    app.add_handler(MessageHandler(filters.TEXT&~filters.COMMAND,recibir_id))
    logger.info("✅ Bot Colombia iniciado | Owner: %s",OWNER_ID)
    app.run_polling(drop_pending_updates=True)

if __name__=="__main__":
    main()
