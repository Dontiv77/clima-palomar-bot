import asyncio
import logging
import os
from datetime import datetime, timezone
import re

import feedparser
from bs4 import BeautifulSoup
import nest_asyncio
import pytz
import requests
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes



# Configuración
API_KEY = "d2018c5d7f0737051c1d3bb6fb6e041f"
CHAT_ID = "8162211117"
BOT_TOKEN = "8054719934:AAGkqZLv4N605PzRtAXtH28QGTqW7TjiGpY"

# Ciudades para alertas meteorológicas
CIUDADES_ALERTA = {
    "El Palomar": (-34.6103, -58.5973),
    "Ezeiza": (-34.8216, -58.535),
    "Monte Grande": (-34.8166, -58.465),
    "CABA": (-34.608, -58.372),
}

# Coordenadas para rutas
ORIGEN_COORDS = (-34.6103, -58.5973)
DESTINO_COORDS = (-34.8216, -58.535)

ORIGEN_RUTA = "R\u00edo Negro 1000, El Palomar"
DESTINO_RUTA = "Aeropuerto Ezeiza"

# RSS
RSS_POLICIALES = "https://www.infobae.com/policiales/rss/?output=RSS"
RSS_POLITICA = "https://www.infobae.com/politica/rss/?output=RSS"
RSS_LOCALES = "https://www.smnoticias.com/feed"
RSS_RIVER = "https://www.promiedos.com.ar/rss2.php?c=river"
RIVER_URL = "https://www.promiedos.com.ar/river"
TRAFFIC_URL = "https://trafico.buenosaires.gob.ar/estado"
ACCESOS_VIALES = [
    "Panamericana",
    "General Paz",
    "Riccheri",
    "Acceso Oeste",
    "Autopista 25 de Mayo",
]
RSS_INTERNACIONAL = "https://www.infobae.com/america/rss/?output=RSS"

# Estado
enviados_noticias: set[str] = set()
enviados_partidos: set[str] = set()
enviados_urgentes: set[str] = set()
enviadas_alertas: set[str] = set()
enviados_tweets: set[str] = set()

TWITTER_CUENTAS = [
    "SMN_Argentina",
    "defensacivilBA",
    "solotransito",
    "EmergenciasBA",
    "CronicaPolicial",
    "alertastransito",
    "AutopistasBA",
    "InfoTransitoBA",
    "AUSAOk",
    "traficoSatelital",
    "RiverPlate",
    "RiverInfoPlate",
    "PolloVignolo",
]

# Palabras clave que disparan el aviso inmediato y sirven para filtrar
KEYWORDS_URGENTES = [
    "tiroteo",
    "asesinato",
    "robo comando",
    "narcotrafico",
    "allanamiento",
    "crimen",
    "atentado",
    "guerra",
    "congreso",
    "inflacion",
    "economia",
    "dolar",
    "despidos",
    "israel",
    "iran",
    "putin",
    "ucrania",
    "estados unidos",
    "presidente",
    "militares",
    "granizo",
    "tormenta",
    "alerta roja",
    "corte",
    "protesta",
    "accidente",
    "panamericana",
    "general paz",
    "riccheri",
    "acceso oeste",
    "25 de mayo",
    "river vs",
]

# Localidades a destacar en noticias
LOCALIDADES_FILTRO = ["caseros", "palomar", "ciudad jardín", "ciudad jardin"]

# Palabras que indican que una noticia es banal y debe descartarse
IGNORE_KEYWORDS = [
    "pareja",
    "cine",
    "boda",
    "evento",
    "camila",
    "kevin",
    "inaugur\u00f3",
    "plaza",
    "gatito",
    "perrito",
    "instagram",
    "tiktok",
    "famosos",
]


# Logging
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    filename="bot_errores.log",
    filemode="a",
)


flask_app = Flask(__name__)


@flask_app.route("/")
def raiz():
    return "Bot funcionando"


@flask_app.route("/ping")
def keep_alive() -> str:
    """Endpoint para que Render no apague el bot."""
    return "pong"


def iniciar_flask():
    flask_app.run(host="0.0.0.0", port=8080)


CIUDADES_CLIMA = {
    "El Palomar": "El Palomar,AR",
    "Monte Grande": "Monte Grande,AR",
    "Ezeiza": "Ezeiza,AR",
}


def _clima_ciudad(nombre: str, query: str) -> str | None:
    """Devuelve mensaje de clima para una ciudad."""
    try:
        url = (
            f"https://api.openweathermap.org/data/2.5/weather?q={query}&appid={API_KEY}&units=metric&lang=es"
        )
        r = requests.get(url)
        data = r.json()
        desc = data["weather"][0]["description"]
        temp = data["main"]["temp"]
        st = data["main"]["feels_like"]
        viento = data["wind"]["speed"]
        humedad = data["main"]["humidity"]
        return (
            f"☁️ *Clima en {nombre}* ☁️\n"
            f"🌡 Estado: *{desc.capitalize()}*\n"
            f"🌞 Temperatura: *{temp}°C* (ST: {st}°C)\n"
            f"🌬 Viento: *{viento} m/s*\n"
            f"💧 Humedad: *{humedad}%*"
        )
    except Exception as e:  # pragma: no cover - red de terceros
        logging.error(f"[CLIMA {nombre}] {e}")
        return None


def obtener_clima() -> str:
    """Devuelve el clima de las ciudades configuradas."""
    partes: list[str] = []
    for nombre, query in CIUDADES_CLIMA.items():
        msg = _clima_ciudad(nombre, query)
        if msg:
            partes.append(msg)
    if partes:
        return "\n\n".join(partes)
    return "⚠️ No pude obtener el clima. Intentá más tarde."


def consultar_alertas() -> dict[str, list[str]]:
    """Obtiene eventos de alertas meteorol\u00f3gicas por ciudad."""
    resultados: dict[str, list[str]] = {}
    for nombre, (lat, lon) in CIUDADES_ALERTA.items():
        try:
            url = (
                f"https://api.openweathermap.org/data/3.0/onecall?lat={lat}&lon={lon}&appid={API_KEY}&lang=es"
            )
            datos = requests.get(url).json()
            eventos = [a.get("event", "Alerta") for a in datos.get("alerts", [])]
            if eventos:
                resultados[nombre] = eventos
        except Exception as e:  # pragma: no cover - red de terceros
            logging.error(f"[ALERTAS {nombre}] {e}")
            continue
    return resultados


def obtener_alertas() -> str | None:
    """Consulta alertas meteorol\u00f3gicas activas."""
    datos = consultar_alertas()
    if not datos:
        return "⚠️ No pude obtener alertas. Intentá más tarde."
    lineas = []
    for ciudad, eventos in datos.items():
        for ev in eventos:
            lineas.append(f"- *{ciudad}: {ev}*")
    if lineas:
        return "⚠️ *Alertas meteorol\u00f3gicas:*\n" + "\n".join(lineas)
    return None


def _resumen(texto: str) -> str:
    """Devuelve un resumen breve y sin HTML."""
    limpio = re.sub("<[^>]+>", "", texto or "").strip()
    if len(limpio) > 120:
        limpio = limpio[:117] + "..."
    return limpio


def obtener_noticias(url: str, cantidad: int = 5, solo_local: bool = False) -> str | None:
    """Extrae noticias nuevas desde un feed RSS aplicando filtros."""
    try:
        feed = feedparser.parse(url)
        mensajes = []
        for entry in feed.entries:
            enlace = entry.get("link")
            if not enlace or enlace in enviados_noticias:
                continue

            titulo = entry.get("title", "(sin titulo)")
            texto = f"{titulo} {entry.get('summary', '')}".lower()
            if any(b in texto for b in IGNORE_KEYWORDS):
                continue
            if solo_local and not any(l in texto for l in LOCALIDADES_FILTRO):
                continue
            if not any(k in texto for k in KEYWORDS_URGENTES):
                continue

            resumen = _resumen(entry.get("summary", ""))
            linea = f"- [{titulo}]({enlace})"
            if resumen:
                linea += f"\n_{resumen}_"
            mensajes.append(linea)
            enviados_noticias.add(enlace)
            if len(mensajes) >= cantidad:
                break
        if mensajes:
            return "\n".join(mensajes)
        return None
    except Exception as e:  # pragma: no cover - red de terceros
        logging.error(f"[NOTICIAS] {e}")
        return "⚠️ No pude obtener noticias. Intentá más tarde."


def _parse_river_html(html: str, now: datetime) -> tuple[str | None, datetime | None, str | None, str | None]:
    """Extrae rival, fecha, torneo y texto crudo desde HTML."""
    soup = BeautifulSoup(html, "html.parser")
    texto = soup.get_text(" ", strip=True)
    raw_date = None
    rival = None
    fecha = None
    torneo = None

    m_fecha = re.search(r"(\d{1,2}/\d{1,2}(?:/\d{2,4})?)\s*(\d{1,2}:\d{2})", texto)
    if m_fecha:
        raw_date = m_fecha.group(0)
        dia = m_fecha.group(1)
        hora = m_fecha.group(2)
        if len(dia.split("/")) == 2:
            dia = f"{dia}/{now.year}"
        try:
            fecha = pytz.timezone("America/Argentina/Buenos_Aires").localize(
                datetime.strptime(f"{dia} {hora}", "%d/%m/%Y %H:%M")
            )
        except Exception:
            fecha = None

    m_rival = re.search(r"river(?:\s*plate)?(?:\s*\(arg\))?\s*vs\.?\s*([^\d\-\n]+)", texto, re.I)
    if m_rival:
        rival = m_rival.group(1).strip()

    torneos = [
        "liga profesional",
        "copa de la liga",
        "copa argentina",
        "copa libertadores",
        "copa sudamericana",
        "supercopa",
    ]
    for t in torneos:
        if re.search(t, texto, re.I):
            torneo = t.title()
            break

    return rival, fecha, raw_date, torneo


def obtener_partido_river(debug: bool = False) -> str | None:
    """Devuelve información del partido de River si se juega hoy."""
    try:
        html = requests.get(RIVER_URL, timeout=10).text
        tz = pytz.timezone("America/Argentina/Buenos_Aires")
        ahora = datetime.now(tz)
        rival, fecha, raw, torneo = _parse_river_html(html, ahora)
        if debug:
            return f"Fuente: {RIVER_URL}\nRaw: {raw}\nFecha local: {fecha}"
        if fecha and fecha.date() == ahora.date():
            hora = fecha.strftime("%H:%M")
            partes = [f"🏟 River juega hoy a las {hora}"]
            if rival:
                partes.append(f"vs {rival}")
            if torneo:
                partes.append(f"({torneo})")
            return " ".join(partes)
        return None
    except Exception as e:  # pragma: no cover - red de terceros
        logging.error(f"[RIVER] {e}")
        return "⚠️ No pude verificar partido de River. Intentá más tarde."



def _ruta_osrm(lon1: float, lat1: float, lon2: float, lat2: float) -> tuple[int, list[str]]:
    """Consulta OSRM y devuelve duración en minutos y pasos simplificados."""
    url = (
        f"https://router.project-osrm.org/route/v1/driving/{lon1},{lat1};{lon2},{lat2}?overview=false&steps=true"
    )
    data = requests.get(url).json()
    dur = int(data["routes"][0]["duration"] / 60)
    pasos: list[str] = []
    for s in data["routes"][0]["legs"][0].get("steps", []):
        name = s.get("name")
        if name and name not in pasos:
            pasos.append(name)
    return dur, pasos


def obtener_trafico() -> tuple[int, int, list[str], list[str]] | None:
    """Duración ida/vuelta y rutas sugeridas."""
    try:
        lon_o, lat_o = ORIGEN_COORDS[1], ORIGEN_COORDS[0]
        lon_d, lat_d = DESTINO_COORDS[1], DESTINO_COORDS[0]

        ida_dur, ida_steps = _ruta_osrm(lon_o, lat_o, lon_d, lat_d)
        vuelta_dur, vuelta_steps = _ruta_osrm(lon_d, lat_d, lon_o, lat_o)
        return ida_dur, vuelta_dur, ida_steps, vuelta_steps
    except Exception as e:  # pragma: no cover - red de terceros
        logging.error(f"[RUTA] {e}")
        return None


def obtener_estado_accesos() -> dict[str, str] | None:
    """Consulta el estado de los accesos viales."""
    try:
        data = requests.get(TRAFFIC_URL, timeout=10).json()
        resultados: dict[str, str] = {}
        for item in data.get("accesos", []):
            nombre = item.get("nombre", "")
            estado = item.get("estado", "")
            for acceso in ACCESOS_VIALES:
                if acceso.lower() in nombre.lower():
                    resultados[acceso] = estado
        return resultados
    except Exception as e:  # pragma: no cover - red de terceros
        logging.error(f"[ACCESOS] {e}")
        return None


def obtener_accesos_piquetes() -> tuple[dict[str, str] | None, list[str] | None]:
    """Estados de accesos y lista de piquetes/bloqueos."""
    try:
        data = requests.get(TRAFFIC_URL, timeout=10).json()
        accesos: dict[str, str] = {}
        for item in data.get("accesos", []):
            nombre = item.get("nombre", "")
            estado = item.get("estado", "")
            for acceso in ACCESOS_VIALES:
                if acceso.lower() in nombre.lower():
                    accesos[acceso] = estado
        piquetes: list[str] = []
        for bloqueos in [data.get("piquetes"), data.get("cortes"), data.get("incidentes")]:
            if isinstance(bloqueos, list):
                for b in bloqueos:
                    desc = b.get("descripcion") or b.get("lugar") or b.get("ubicacion")
                    if desc:
                        piquetes.append(desc)
        return accesos, piquetes
    except Exception as e:  # pragma: no cover - red de terceros
        logging.error(f"[PIQUETES] {e}")
        return None, None


def obtener_ruta() -> tuple[str, tuple[int, int] | None]:
    """Devuelve texto de tránsito ida y vuelta con rutas y estados."""
    datos = obtener_trafico()
    estados = obtener_estado_accesos()
    lineas: list[str] = []
    if not datos:
        lineas.append("⚠️ No pude obtener la ruta. Intentá más tarde.")
    else:
        ida, vuelta, pasos_ida, pasos_vuelta = datos
        linea_ida = f"Ida: {ida} min"
        if pasos_ida:
            linea_ida += " por " + " + ".join(pasos_ida[:4])
        linea_vuelta = f"Vuelta: {vuelta} min"
        if pasos_vuelta:
            linea_vuelta += " por " + " + ".join(pasos_vuelta[:4])
        lineas.append(linea_ida)
        lineas.append(linea_vuelta)
    if not estados:
        lineas.append("⚠️ No pude obtener estado del tránsito. Intentá más tarde.")
    else:
        lineas.append("🚧 Estado accesos:")
        alertas: list[str] = []
        for acceso in ACCESOS_VIALES:
            if acceso in estados:
                est = estados[acceso]
                lineas.append(f"• {acceso}: {est}")
                if any(p in est.lower() for p in ["corte", "congestion"]):
                    alertas.append(f"⚠️ Corte en {acceso} — buscar desvío")
        if alertas:
            lineas.extend(alertas)
    tiempos = None if not datos else (ida, vuelta)
    return "\n".join(lineas), tiempos


async def revisar_alertas_urgentes(app):
    """Env\u00eda mensaje si aparece una alerta meteorol\u00f3gica nueva."""
    datos = consultar_alertas()
    if not datos:
        return
    nuevos: list[str] = []
    for ciudad, eventos in datos.items():
        for ev in eventos:
            clave = f"{ciudad}:{ev}"
            if clave not in enviadas_alertas:
                enviadas_alertas.add(clave)
                nuevos.append(f"{ciudad}: {ev}")
    if nuevos:
        msg = "⚠️ *Nueva alerta meteorol\u00f3gica:*\n" + "\n".join(f"- *{n}*" for n in nuevos)
        try:
            await app.bot.send_message(
                chat_id=CHAT_ID,
                text=msg,
                parse_mode="Markdown",
                disable_web_page_preview=True,
            )
        except Exception as e:  # pragma: no cover - red de terceros
            logging.error(f"[ALERTA URGENTE] {e}")


async def revisar_noticias_urgentes(app):
    """Detecta noticias con palabras clave y las envia inmediatamente."""
    feeds = [RSS_POLICIALES, RSS_POLITICA, RSS_LOCALES, RSS_INTERNACIONAL]
    for url in feeds:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                enlace = entry.get("link")
                if not enlace or enlace in enviados_urgentes:
                    continue

                titulo = entry.get("title", "")
                texto = f"{titulo} {entry.get('summary', '')}".lower()
                if any(b in texto for b in IGNORE_KEYWORDS):
                    continue
                if any(k in texto for k in KEYWORDS_URGENTES):
                    enviados_urgentes.add(enlace)
                    resumen = _resumen(entry.get("summary", ""))
                    msg = f"⚠️ *Noticia urgente:* [{titulo}]({enlace})"
                    if resumen:
                        msg += f"\n_{resumen}_"
                    await app.bot.send_message(
                        chat_id=CHAT_ID,
                        text=msg,
                        parse_mode="Markdown",
                        disable_web_page_preview=True,
                    )
        except Exception as e:  # pragma: no cover - red de terceros
            logging.error(f"[NOTICIA URGENTE] {e}")


async def revisar_tweets_urgentes(app):
    """Chequea cuentas de Twitter por palabras clave de alerta."""
    for cuenta in TWITTER_CUENTAS:
        try:
            feed = feedparser.parse(f"https://nitter.net/{cuenta}/rss")
            for entry in feed.entries:
                enlace = entry.get("link")
                if not enlace or enlace in enviados_tweets:
                    continue

                titulo = entry.get("title", "")
                texto = titulo.lower()
                if any(b in texto for b in IGNORE_KEYWORDS):
                    continue
                if any(k in texto for k in KEYWORDS_URGENTES):
                    enviados_tweets.add(enlace)
                    msg = f"⚠️ *Tweet urgente:* [{titulo}]({enlace})"
                    await app.bot.send_message(
                        chat_id=CHAT_ID,
                        text=msg,
                        parse_mode="Markdown",
                        disable_web_page_preview=True,
                    )
        except Exception as e:  # pragma: no cover - red de terceros
            logging.error(f"[TWITTER {cuenta}] {e}")


def armar_resumen() -> str:
    """Construye el mensaje de resumen."""
    partes = [obtener_clima()]

    alertas = obtener_alertas()
    if alertas:
        partes.append(alertas)

    policiales = obtener_noticias(RSS_POLICIALES, 3, solo_local=True)
    if policiales:
        partes.append("🔎 *Noticias policiales:*\n" + policiales)

    politica = obtener_noticias(RSS_POLITICA, 3, solo_local=True)
    if politica:
        partes.append("📰 *Noticias políticas:*\n" + politica)

    locales = obtener_noticias(RSS_LOCALES, 3, solo_local=True)
    if locales:
        partes.append("🏠 *Noticias locales:*\n" + locales)

    internacional = obtener_noticias(RSS_INTERNACIONAL, 1, solo_local=True)
    if internacional:
        partes.append("🌎 *Internacional:*\n" + internacional)

    partido = obtener_partido_river()
    if partido:
        partes.append(partido)

    return "\n\n".join(partes)


async def comando_resumen(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Envía el resumen al solicitar /resumen."""
    try:
        await update.message.reply_text(
            armar_resumen(), parse_mode="Markdown", disable_web_page_preview=True
        )
    except Exception as e:  # pragma: no cover - red de terceros
        logging.error(f"[COMANDO /resumen] {e}")


async def comando_clima(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Envía solo el clima actual y alertas."""
    try:
        partes = [obtener_clima()]
        alertas = obtener_alertas()
        if alertas:
            partes.append(alertas)
        await update.message.reply_text(
            "\n\n".join(partes),
            parse_mode="Markdown",
            disable_web_page_preview=True,
        )
    except Exception as e:  # pragma: no cover - red de terceros
        logging.error(f"[COMANDO /clima] {e}")


async def comando_noticias(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Envía las últimas noticias."""
    try:
        partes = []

        policiales = obtener_noticias(RSS_POLICIALES, solo_local=True)
        if policiales:
            partes.append("🔎 *Noticias policiales:*\n" + policiales)

        politica = obtener_noticias(RSS_POLITICA, solo_local=True)
        if politica:
            partes.append("📰 *Noticias políticas:*\n" + politica)

        locales = obtener_noticias(RSS_LOCALES, solo_local=True)
        if locales:
            partes.append("🏠 *Noticias locales:*\n" + locales)

        if not partes:
            partes.append("⚠️ *No se pudieron obtener noticias.*")

        await update.message.reply_text(
            "\n\n".join(partes),
            parse_mode="Markdown",
            disable_web_page_preview=True,
        )
    except Exception as e:  # pragma: no cover - red de terceros
        logging.error(f"[COMANDO /noticias] {e}")


async def comando_river(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Informa si River juega hoy y resultado si está disponible."""
    try:
        partido = obtener_partido_river()
        mensaje = partido or "ℹ️ River no tiene partido programado para hoy."
        await update.message.reply_text(
            mensaje,
            parse_mode="Markdown",
            disable_web_page_preview=True,
        )
    except Exception as e:  # pragma: no cover - red de terceros
        logging.error(f"[COMANDO /river] {e}")


async def comando_debug_river(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Muestra información de depuración del partido de River."""
    try:
        mensaje = obtener_partido_river(debug=True)
        await update.message.reply_text(
            mensaje,
            parse_mode="Markdown",
            disable_web_page_preview=True,
        )
    except Exception as e:  # pragma: no cover - red de terceros
        logging.error(f"[COMANDO /debug_river] {e}")


async def comando_ruta(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Muestra el tránsito a Ezeiza ida y vuelta."""
    try:
        mensaje, tiempos = obtener_ruta()
        await update.message.reply_text(
            mensaje,
            parse_mode="Markdown",
            disable_web_page_preview=True,
        )
        if tiempos and max(tiempos) > 60:
            await update.message.reply_text(
                f"⚠️ Demora crítica en el tránsito a Ezeiza: {max(tiempos)} minutos\nRevisá rutas alternativas.",
                parse_mode="Markdown",
                disable_web_page_preview=True,
            )
    except Exception as e:  # pragma: no cover - red de terceros
        logging.error(f"[COMANDO /ruta] {e}")


async def comando_trafico(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Informa estado de accesos y piquetes."""
    try:
        accesos, piquetes = obtener_accesos_piquetes()
        lineas: list[str] = []
        if not accesos:
            lineas.append("⚠️ No pude obtener estado del tránsito. Intentá más tarde.")
        else:
            lineas.append("🚦 Estado accesos:")
            for acceso in ACCESOS_VIALES:
                if acceso in accesos:
                    lineas.append(f"• {acceso}: {accesos[acceso]}")
        if piquetes is None:
            lineas.append("⚠️ No pude verificar piquetes o bloqueos.")
        elif piquetes:
            lineas.append("🚧 Piquetes/bloqueos activos:")
            lineas.extend(f"• {p}" for p in piquetes)
        else:
            lineas.append("Sin piquetes ni bloqueos reportados.")
        await update.message.reply_text(
            "\n".join(lineas),
            parse_mode="Markdown",
            disable_web_page_preview=True,
        )
    except Exception as e:  # pragma: no cover - red de terceros
        logging.error(f"[COMANDO /trafico] {e}")


async def comando_alertas(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Muestra las alertas clim\u00e1ticas activas."""
    try:
        alerta = obtener_alertas()
        await update.message.reply_text(
            alerta or "No hay alertas vigentes.",
            parse_mode="Markdown",
            disable_web_page_preview=True,
        )
    except Exception as e:  # pragma: no cover - red de terceros
        logging.error(f"[COMANDO /alertas] {e}")


async def comando_ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Lista de comandos."""
    mensaje = "\n".join(
        [
            "🤖 *Comandos disponibles:*",
            "/clima - Clima actual",
            "/noticias - Últimas noticias",
            "/river - Partido de River de hoy",
            "/debug_river - Info depuración River",
            "/alertas - Ver alertas climáticas",
            "/trafico - Estado de accesos AMBA",
            "/ruta - Ruta al trabajo y a casa",
            "/resumen - Resumen manual",
            "/ayuda - Lista de comandos",
        ]
    )
    await update.message.reply_text(mensaje, parse_mode="Markdown")


async def enviar_resumen(app):
    """Envía el resumen automático."""
    try:
        await app.bot.send_message(
            chat_id=CHAT_ID,
            text=armar_resumen(),
            parse_mode="Markdown",
            disable_web_page_preview=True,
        )
    except Exception as e:  # pragma: no cover - red de terceros
        logging.error(f"[ENVÍO RESUMEN] {e}")


async def enviar_ruta(app):
    """Envía la información de tránsito y alerta por demoras."""
    try:
        mensaje, tiempos = obtener_ruta()
        await app.bot.send_message(
            chat_id=CHAT_ID,
            text=mensaje,
            parse_mode="Markdown",
            disable_web_page_preview=True,
        )
        if tiempos and max(tiempos) > 60:
            await app.bot.send_message(
                chat_id=CHAT_ID,
                text=(
                    f"⚠️ Demora crítica en el tránsito a Ezeiza: {max(tiempos)} minutos\n"
                    "Revisá rutas alternativas."
                ),
                parse_mode="Markdown",
                disable_web_page_preview=True,
            )
    except Exception as e:  # pragma: no cover - red de terceros
        logging.error(f"[ENVÍO RUTA] {e}")


def limpiar_enviados():
    """Reinicia sets de noticias y alertas."""
    enviados_noticias.clear()
    enviados_partidos.clear()
    enviados_urgentes.clear()
    enviadas_alertas.clear()


def self_ping() -> None:
    """Envía un ping a la propia aplicación cada 14 minutos."""
    url = os.environ.get("RENDER_EXTERNAL_URL")
    if not url:
        return
    try:
        requests.get(f"{url}/ping", timeout=10)
    except Exception as e:  # pragma: no cover - red de terceros
        logging.error(f"[SELF PING] {e}")


async def iniciar_bot():
    nest_asyncio.apply()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("resumen", comando_resumen))
    app.add_handler(CommandHandler("clima", comando_clima))
    app.add_handler(CommandHandler("noticias", comando_noticias))
    app.add_handler(CommandHandler("river", comando_river))
    app.add_handler(CommandHandler("debug_river", comando_debug_river))
    app.add_handler(CommandHandler("ruta", comando_ruta))
    app.add_handler(CommandHandler("transito", comando_trafico))
    app.add_handler(CommandHandler("trafico", comando_trafico))
    app.add_handler(CommandHandler("alertas", comando_alertas))
    app.add_handler(CommandHandler("ayuda", comando_ayuda))

    tz = pytz.timezone("America/Argentina/Buenos_Aires")
    scheduler = AsyncIOScheduler(timezone=tz)
    scheduler.add_job(enviar_resumen, "cron", hour="0,7,18", minute=0, args=[app])
    scheduler.add_job(limpiar_enviados, "cron", hour=1, minute=0)
    scheduler.add_job(self_ping, "interval", minutes=14)
    scheduler.add_job(revisar_alertas_urgentes, "interval", minutes=5, args=[app])
    scheduler.add_job(revisar_noticias_urgentes, "interval", minutes=8, args=[app])
    scheduler.add_job(revisar_tweets_urgentes, "interval", minutes=4, args=[app])
    scheduler.add_job(enviar_ruta, "cron", hour="7,16", minute=30, args=[app])
    scheduler.start()

    print("✅ BOT FUNCIONANDO CORRECTAMENTE")
    await app.run_polling()


if __name__ == "__main__":
    from threading import Thread

    Thread(target=iniciar_flask, daemon=True).start()
    asyncio.run(iniciar_bot())

