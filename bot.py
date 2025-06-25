import asyncio
import logging
import os
from datetime import datetime
import re

import feedparser
import nest_asyncio
import pytz
import requests
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from flask import Flask
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes



# Configuración
API_KEY = "d2018c5d7f0737051c1d3bb6fb6e041f"
CIUDAD = "El Palomar,AR"
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

KEYWORDS_URGENTES = [
    "asalto",
    "tiroteo",
    "accidente",
    "incendio",
    "protesta",
    "nieve",
    "temporal",
    "evacuación",
    "homicidio",
    "caseros",
    "palomar",
    "morón",
    "ciudad jardín",
    "guerra",
    "putin",
    "rusia",
    "ucrania",
    "israel",
    "ir\u00e1n",
    "otan",
    "nuclear",
    "crisis",
    "atentado",
    "eeuu",
    "granizo",
    "alerta roja",
    "riccheri",
    "panamericana",
    "general paz",
    "25 de mayo",
    "corte",
    "congestion",
    "river vs",
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


def obtener_clima() -> str:
    """Devuelve el clima actual en El Palomar."""
    try:
        url = (
            f"https://api.openweathermap.org/data/2.5/weather?q={CIUDAD}&appid={API_KEY}&units=metric&lang=es"
        )
        r = requests.get(url)
        data = r.json()
        desc = data["weather"][0]["description"]
        temp = data["main"]["temp"]
        st = data["main"]["feels_like"]
        viento = data["wind"]["speed"]
        humedad = data["main"]["humidity"]
        return (
            "☁️ *Clima en El Palomar* ☁️\n"
            f"🌡 Estado: *{desc.capitalize()}*\n"
            f"🌞 Temperatura: *{temp}°C* (ST: {st}°C)\n"
            f"🌬 Viento: *{viento} m/s*\n"
            f"💧 Humedad: *{humedad}%*"
        )
    except Exception as e:  # pragma: no cover - red de terceros
        logging.error(f"[CLIMA] {e}")
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


def obtener_noticias(url: str, cantidad: int = 5) -> str | None:
    """Extrae noticias nuevas desde un feed RSS."""
    try:
        feed = feedparser.parse(url)
        mensajes = []
        for entry in feed.entries:
            enlace = entry.get("link")
            if enlace and enlace not in enviados_noticias:
                titulo = entry.get("title", "(sin titulo)")
                mensajes.append(f"- [{titulo}]({enlace})")
                enviados_noticias.add(enlace)
            if len(mensajes) >= cantidad:
                break
        if mensajes:
            return "\n".join(mensajes)
        return None
    except Exception as e:  # pragma: no cover - red de terceros
        logging.error(f"[NOTICIAS] {e}")
        return "⚠️ No pude obtener noticias. Intentá más tarde."


def obtener_partido_river() -> str | None:
    """Devuelve información del partido de River si se juega hoy."""
    try:
        feed = feedparser.parse(RSS_RIVER)
        tz = pytz.timezone("America/Argentina/Buenos_Aires")
        hoy = datetime.now(tz).date()
        for entry in feed.entries:
            fecha: datetime | None = None
            if entry.get("published_parsed"):
                fecha = (
                    datetime(*entry.published_parsed[:6], tzinfo=pytz.utc)
                    .astimezone(tz)
                )
            elif entry.get("published"):
                try:
                    fecha = (
                        datetime.strptime(
                            entry.published, "%a, %d %b %Y %H:%M:%S %z"
                        ).astimezone(tz)
                    )
                except Exception:
                    fecha = None
            if not fecha:
                texto = f"{entry.get('title', '')} {entry.get('summary', '')}".lower()
                m = re.search(r"(\d{1,2}/\d{1,2})\s+(\d{1,2}:\d{2})", texto)
                if m:
                    try:
                        dia, hora = m.groups()
                        fecha = tz.localize(
                            datetime.strptime(
                                f"{dia}/{datetime.now(tz).year} {hora}",
                                "%d/%m/%Y %H:%M",
                            )
                        )
                    except Exception:
                        fecha = None
            if fecha and fecha.date() == hoy:
                hora = fecha.strftime("%H:%M")
                titulo = entry.get("title", "")
                m = re.search(r"vs\.?\s*([^\-|]+)", titulo, re.IGNORECASE)
                rival = m.group(1).strip() if m else titulo
                return f"🏟 River juega hoy vs {rival} a las {hora}"
        return None
    except Exception as e:  # pragma: no cover - red de terceros
        logging.error(f"[RIVER] {e}")
        return "⚠️ No pude obtener información de River. Intentá más tarde."



def obtener_trafico() -> tuple[int, int] | None:
    """Calcula duración de ida y vuelta a Ezeiza en minutos."""
    try:
        lon_o, lat_o = ORIGEN_COORDS[1], ORIGEN_COORDS[0]
        lon_d, lat_d = DESTINO_COORDS[1], DESTINO_COORDS[0]

        def _dur(lon1: float, lat1: float, lon2: float, lat2: float) -> int:
            url = (
                f"https://router.project-osrm.org/route/v1/driving/{lon1},{lat1};{lon2},{lat2}?overview=false"
            )
            data = requests.get(url).json()
            return int(data["routes"][0]["duration"] / 60)

        ida = _dur(lon_o, lat_o, lon_d, lat_d)
        vuelta = _dur(lon_d, lat_d, lon_o, lat_o)
        return ida, vuelta
    except Exception as e:  # pragma: no cover - red de terceros
        logging.error(f"[RUTA] {e}")
        return None


def obtener_ruta() -> str:
    """Devuelve texto de tránsito ida y vuelta."""
    tiempos = obtener_trafico()
    if not tiempos:
        return "⚠️ No pude obtener la ruta. Intentá más tarde."
    ida, vuelta = tiempos
    return (
        f"🚗 Ida (Palomar → Ezeiza): {ida} minutos\n"
        f"🔁 Vuelta (Ezeiza → Palomar): {vuelta} minutos"
    )


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
                titulo = entry.get("title", "").lower()
                if not enlace or enlace in enviados_urgentes:
                    continue
                if any(kw in titulo for kw in KEYWORDS_URGENTES):
                    enviados_urgentes.add(enlace)
                    texto = entry.get("title", "(sin titulo)")
                    msg = f"🚨 *Noticia urgente:* [{texto}]({enlace})"
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
                titulo = entry.get("title", "").lower()
                if not enlace or enlace in enviados_tweets:
                    continue
                if any(kw in titulo for kw in KEYWORDS_URGENTES):
                    enviados_tweets.add(enlace)
                    texto = entry.get("title", "(sin titulo)")
                    msg = f"🚨 *Tweet urgente:* [{texto}]({enlace})"
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

    policiales = obtener_noticias(RSS_POLICIALES, 3)
    if policiales:
        partes.append("🔎 *Noticias policiales:*\n" + policiales)

    politica = obtener_noticias(RSS_POLITICA, 3)
    if politica:
        partes.append("📰 *Noticias políticas:*\n" + politica)

    locales = obtener_noticias(RSS_LOCALES, 3)
    if locales:
        partes.append("🏠 *Noticias locales:*\n" + locales)

    internacional = obtener_noticias(RSS_INTERNACIONAL, 1)
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

        policiales = obtener_noticias(RSS_POLICIALES)
        if policiales:
            partes.append("🔎 *Noticias policiales:*\n" + policiales)

        politica = obtener_noticias(RSS_POLITICA)
        if politica:
            partes.append("📰 *Noticias políticas:*\n" + politica)

        locales = obtener_noticias(RSS_LOCALES)
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


async def comando_ruta(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Muestra el tránsito a Ezeiza ida y vuelta."""
    try:
        tiempos = obtener_trafico()
        if not tiempos:
            mensaje = "⚠️ No pude obtener la ruta. Intentá más tarde."
        else:
            ida, vuelta = tiempos
            mensaje = (
                f"🚗 Ida (Palomar → Ezeiza): {ida} minutos\n"
                f"🔁 Vuelta (Ezeiza → Palomar): {vuelta} minutos"
            )
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
    """Alias de /ruta para compatibilidad."""
    await comando_ruta(update, context)


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
            "/alertas - Ver alertas climáticas",
            "/trafico - Tránsito a Ezeiza",
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
        tiempos = obtener_trafico()
        if not tiempos:
            mensaje = "⚠️ No pude obtener la ruta. Intentá más tarde."
        else:
            ida, vuelta = tiempos
            mensaje = (
                f"🚗 Ida (Palomar → Ezeiza): {ida} minutos\n"
                f"🔁 Vuelta (Ezeiza → Palomar): {vuelta} minutos"
            )
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
    app.add_handler(CommandHandler("ruta", comando_ruta))
    app.add_handler(CommandHandler("transito", comando_trafico))
    app.add_handler(CommandHandler("trafico", comando_trafico))
    app.add_handler(CommandHandler("alertas", comando_alertas))
    app.add_handler(CommandHandler("ayuda", comando_ayuda))

    tz = pytz.timezone("America/Argentina/Buenos_Aires")
    scheduler = AsyncIOScheduler(timezone=tz)
    scheduler.add_job(enviar_resumen, "cron", hour="0,7,12,18", minute=0, args=[app])
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

