import asyncio
import logging
import os
from datetime import datetime

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

# RSS
RSS_POLICIALES = "https://www.infobae.com/policiales/rss/?output=RSS"
RSS_POLITICA = "https://www.infobae.com/politica/rss/?output=RSS"
RSS_LOCALES = "https://www.smnoticias.com/feed"
RSS_RIVER = "https://www.promiedos.com.ar/rss2.php?c=river"

# Estado
enviados_noticias: set[str] = set()
enviados_partidos: set[str] = set()
enviados_urgentes: set[str] = set()
enviadas_alertas: set[str] = set()

KEYWORDS_URGENTES = [
    "asalto",
    "tiroteo",
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
    "crisis",
    "atentado",
    "eeuu",
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
    return "ok"


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
        return "⚠️ *No se pudo obtener el clima.*"


def consultar_alertas() -> list[str]:
    """Obtiene lista de eventos de alertas meteorológicas."""
    try:
        url = (
            f"https://api.openweathermap.org/data/2.5/weather?q={CIUDAD}&appid={API_KEY}&units=metric&lang=es"
        )
        data = requests.get(url).json()
        lat = data["coord"]["lat"]
        lon = data["coord"]["lon"]
        url_alert = (
            f"https://api.openweathermap.org/data/3.0/onecall?lat={lat}&lon={lon}&appid={API_KEY}&lang=es"
        )
        datos = requests.get(url_alert).json()
        if "alerts" not in datos:
            return []
        return [a.get("event", "Alerta") for a in datos["alerts"]]
    except Exception as e:  # pragma: no cover - red de terceros
        logging.error(f"[ALERTAS] {e}")
        return []


def obtener_alertas() -> str | None:
    """Consulta alertas meteorológicas activas."""
    eventos = consultar_alertas()
    if not eventos:
        return None
    mensajes = [f"- *{ev}*" for ev in eventos]
    return "⚠️ *Alertas meteorológicas:*\n" + "\n".join(mensajes)


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
        return None


def obtener_partido_river() -> str | None:
    """Devuelve el partido de River si juega hoy."""
    try:
        feed = feedparser.parse(RSS_RIVER)
        tz = pytz.timezone("America/Argentina/Buenos_Aires")
        hoy = datetime.now(tz).strftime("%d/%m/%Y")
        for entry in feed.entries:
            texto = entry.get("title", "")
            if hoy in texto:
                enlace = entry.get("link", "")
                if enlace not in enviados_partidos:
                    enviados_partidos.add(enlace)
                    return f"⚽️ *{texto}*"
        return None
    except Exception as e:  # pragma: no cover - red de terceros
        logging.error(f"[RIVER] {e}")
        return None


async def revisar_alertas_urgentes(app):
    """Envía mensaje si aparece una alerta meteorológica nueva."""
    eventos = consultar_alertas()
    nuevos = [e for e in eventos if e not in enviadas_alertas]
    for e in nuevos:
        enviadas_alertas.add(e)
    if nuevos:
        msg = "⚠️ *Nueva alerta meteorológica:*\n" + "\n".join(f"- *{n}*" for n in nuevos)
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
    feeds = [RSS_POLICIALES, RSS_POLITICA, RSS_LOCALES]
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


def armar_resumen() -> str:
    """Construye el mensaje de resumen."""
    partes = [obtener_clima()]

    alertas = obtener_alertas()
    if alertas:
        partes.append(alertas)

    policiales = obtener_noticias(RSS_POLICIALES)
    if policiales:
        partes.append("🔎 *Noticias policiales:*\n" + policiales)

    politica = obtener_noticias(RSS_POLITICA)
    if politica:
        partes.append("📰 *Noticias políticas:*\n" + politica)

    locales = obtener_noticias(RSS_LOCALES)
    if locales:
        partes.append("🏠 *Noticias locales:*\n" + locales)

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
        mensaje = partido or "No hay partido de River programado para hoy."
        await update.message.reply_text(
            mensaje,
            parse_mode="Markdown",
            disable_web_page_preview=True,
        )
    except Exception as e:  # pragma: no cover - red de terceros
        logging.error(f"[COMANDO /river] {e}")


async def comando_ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Lista de comandos."""
    mensaje = "\n".join(
        [
            "🤖 *Comandos disponibles:*",
            "/clima - Clima actual",
            "/noticias - Últimas noticias",
            "/river - Partido de River de hoy",
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
    app.add_handler(CommandHandler("ayuda", comando_ayuda))

    tz = pytz.timezone("America/Argentina/Buenos_Aires")
    scheduler = AsyncIOScheduler(timezone=tz)
    scheduler.add_job(enviar_resumen, "cron", hour="0,7,12,18", minute=0, args=[app])
    scheduler.add_job(limpiar_enviados, "cron", hour=1, minute=0)
    scheduler.add_job(self_ping, "interval", minutes=14)
    scheduler.add_job(revisar_alertas_urgentes, "interval", minutes=15, args=[app])
    scheduler.add_job(revisar_noticias_urgentes, "interval", minutes=10, args=[app])
    scheduler.start()

    print("✅ BOT FUNCIONANDO CORRECTAMENTE")
    await app.run_polling()


if __name__ == "__main__":
    from threading import Thread

    Thread(target=iniciar_flask, daemon=True).start()
    asyncio.run(iniciar_bot())

