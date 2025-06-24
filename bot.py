import asyncio
import logging
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


def obtener_alertas() -> str | None:
    """Consulta alertas meteorológicas activas."""
    try:
        # Primero obtenemos lat/lon de la ciudad
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
            return None
        mensajes = []
        for alert in datos["alerts"]:
            evento = alert.get("event", "Alerta")
            mensajes.append(f"- *{evento}*")
        if mensajes:
            return "⚠️ *Alertas meteorológicas:*\n" + "\n".join(mensajes)
        return None
    except Exception as e:  # pragma: no cover - red de terceros
        logging.error(f"[ALERTAS] {e}")
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


async def comando_ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Lista de comandos."""
    mensaje = "\n".join(
        [
            "🤖 *Comandos disponibles:*",
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
    """Reinicia sets de noticias y partidos."""
    enviados_noticias.clear()
    enviados_partidos.clear()


async def iniciar_bot():
    nest_asyncio.apply()
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("resumen", comando_resumen))
    app.add_handler(CommandHandler("ayuda", comando_ayuda))

    tz = pytz.timezone("America/Argentina/Buenos_Aires")
    scheduler = AsyncIOScheduler(timezone=tz)
    scheduler.add_job(enviar_resumen, "cron", hour="0,7,12,18", minute=0, args=[app])
    scheduler.add_job(limpiar_enviados, "cron", hour=1, minute=0)
    scheduler.start()

    print("✅ BOT FUNCIONANDO CORRECTAMENTE")
    await app.run_polling()


if __name__ == "__main__":
    from threading import Thread

    Thread(target=iniciar_flask, daemon=True).start()
    asyncio.run(iniciar_bot())

