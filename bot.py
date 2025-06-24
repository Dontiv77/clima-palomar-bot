from datetime import datetime, timedelta
import nest_asyncio
nest_asyncio.apply()
import pytz
import requests
import logging
import asyncio
import feedparser
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# Logging
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    filename='bot_errores.log',
    filemode='a'
)

API_KEY = 'd2018c5d7f0737051c1d3bb6fb6e041f'
CIUDAD = 'El Palomar,AR'
CHAT_ID = '8162211117'
BOT_TOKEN = '8054719934:AAGkqZLv4N605PzRtAXtH28QGTqW7TjiGpY'

enviados_clima = set()
enviados_noticias = set()
enviados_alertas = set()
enviados_partidos = set()

def obtener_clima():
    try:
        url = f'https://api.openweathermap.org/data/2.5/weather?q={CIUDAD}&appid={API_KEY}&units=metric&lang=es'
        r = requests.get(url)
        data = r.json()
        desc = data["weather"][0]["description"]
        temp = data["main"]["temp"]
        st = data["main"]["feels_like"]
        viento = data["wind"]["speed"]
        humedad = data["main"]["humidity"]
        return (
            f"☁️ *Clima en El Palomar* ☁️\n"
            f"🌡 Estado: *{desc.capitalize()}*\n"
            f"🌞 Temperatura: *{temp}°C* (ST: {st}°C)\n"
            f"🌬 Viento: *{viento} m/s*\n"
            f"💧 Humedad: *{humedad}%*"
        )
    except Exception as e:
        logging.error(f"[CLIMA] {e}")
        return "⚠️ *No se pudo obtener el clima.*"

async def comando(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        texto = update.message.text
        if texto == "/clima":
            await update.message.reply_text(obtener_clima(), parse_mode="Markdown")
        elif texto == "/ayuda":
            await update.message.reply_text(
                "🤖 *Comandos disponibles:*\n"
                "/clima - Muestra el clima actual\n"
                "/ayuda - Lista de comandos", parse_mode="Markdown"
            )
    except Exception as e:
        logging.error(f"[COMANDO] {e}")

async def resumen_periodico(app):
    try:
        ahora = datetime.now(pytz.timezone("America/Argentina/Buenos_Aires"))
        hora = ahora.strftime("%H:%M")
        if hora in ['00:00', '07:00', '12:00'] and hora not in enviados_clima:
            await app.bot.send_message(chat_id=CHAT_ID, text=obtener_clima(), parse_mode="Markdown")
            enviados_clima.add(hora)
        if ahora.hour == 1:
            enviados_clima.clear()
    except Exception as e:
        logging.error(f"[RESUMEN AUTOMÁTICO] {e}")

async def iniciar_bot():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler(["clima", "ayuda"], comando))

    tz = pytz.timezone("America/Argentina/Buenos_Aires")
    scheduler = AsyncIOScheduler(timezone=tz)
    scheduler.add_job(lambda: asyncio.create_task(resumen_periodico(app)), 'interval', minutes=1)
    scheduler.start()

    print("✅ BOT FUNCIONANDO CORRECTAMENTE")
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(iniciar_bot())
