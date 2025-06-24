from datetime import datetime, timedelta
import nest_asyncio
nest_asyncio.apply()
import pytz
import requests
import logging
import asyncio
import feedparser
import imghdr as imghdr_custom  # Compatibilidad para Python 3.13+
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

# Configuración
API_KEY = 'd2018c5d7f0737051c1d3bb6fb6e041f'
CIUDAD = 'El Palomar,AR'
CHAT_ID = '8162211117'
BOT_TOKEN = '8054719934:AAGkqZLv4N605PzRtAXtH28QGTqW7TjiGpY'

# Control
enviados_clima = set()
enviados_noticias = set()
enviados_alertas = set()
enviados_partidos = set()
noticias_locales_enviadas = set()

# Funciones
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

def obtener_alerta():
    try:
        url = f'https://api.openweathermap.org/data/2.5/weather?q={CIUDAD}&appid={API_KEY}&units=metric&lang=es'
        r = requests.get(url)
        data = r.json()
        estado = data['weather'][0]['main'].lower()
        temp = data['main']['temp']
        if any(w in estado for w in ['snow', 'storm', 'rain', 'wind']) or temp <= 1:
            return f"⚠️ *Alerta en El Palomar:* {data['weather'][0]['description'].capitalize()}, {temp}°C"
    except Exception as e:
        logging.error(f"[ALERTA] {e}")
    return None

def obtener_noticias():
    try:
        rss_feeds = [
            "https://www.clarin.com/rss/policiales/",
            "https://www.infobae.com/feeds/rss/policiales.xml",
            "https://www.pagina12.com.ar/rss/policia.xml",
            "https://www.lanacion.com.ar/rss/policiales.xml",
            "https://www.tn.com.ar/rss/policiales.xml",
            "https://www.minutouno.com/rss/policiales.xml",
            "https://www.infobae.com/feeds/rss/politica.xml",
            "https://www.pagina12.com.ar/rss/politica.xml",
            "https://www.ambito.com/rss/politica.xml",
            "https://www.baenegocios.com/rss/politica.xml",
            "https://www.eldiarioar.com/rss/politica.xml",
        ]
        zonas = ["palomar", "caseros", "ciudad jardín", "ciudad jardin", "el palomar"]
        noticias_locales = []
        noticias_policiales = []
        noticias_politica = []

        for url in rss_feeds:
            feed = feedparser.parse(url)
            for entry in feed.entries[:8]:
                titulo = entry.title
                resumen = entry.get("summary", "")
                link = entry.link
                if any(z in titulo.lower() or z in resumen.lower() for z in zonas):
                    noticias_locales.append(f"📍 {titulo}\n{link}")
                elif "polici" in url:
                    noticias_policiales.append(f"🚔 {titulo}\n{link}")
                elif "politi" in url:
                    noticias_politica.append(f"🏛️ {titulo}\n{link}")

        mensaje = "📰 *Noticias destacadas:*\n"
        if noticias_locales:
            mensaje += "\n*Locales (Palomar, Caseros, Ciudad Jardín):*\n" + "\n".join(noticias_locales[:3])
        if noticias_policiales:
            mensaje += "\n\n*Policiales:*\n" + "\n".join(noticias_policiales[:3])
        if noticias_politica:
            mensaje += "\n\n*Política:*\n" + "\n".join(noticias_politica[:3])

        if not (noticias_locales or noticias_policiales or noticias_politica):
            mensaje += "⚠️ No se encontraron noticias en los portales configurados."

        return mensaje

    except Exception as e:
        logging.error(f"[NOTICIAS] {e}")
        return "⚠️ *No se pudo obtener noticias.*"

async def alerta_noticias_locales(app):
    try:
        zonas = ["palomar", "caseros", "ciudad jardín", "ciudad jardin", "el palomar"]
        rss_feeds = [
            "https://www.clarin.com/rss/policiales/",
            "https://www.infobae.com/feeds/rss/policiales.xml",
            "https://www.pagina12.com.ar/rss/policia.xml",
            "https://www.lanacion.com.ar/rss/policiales.xml",
            "https://www.tn.com.ar/rss/policiales.xml",
            "https://www.minutouno.com/rss/policiales.xml",
            "https://www.infobae.com/feeds/rss/politica.xml",
            "https://www.pagina12.com.ar/rss/politica.xml",
            "https://www.ambito.com/rss/politica.xml",
            "https://www.baenegocios.com/rss/politica.xml",
            "https://www.eldiarioar.com/rss/politica.xml",
        ]
        nuevas = []
        for url in rss_feeds:
            feed = feedparser.parse(url)
            for entry in feed.entries[:8]:
                titulo = entry.title
                resumen = entry.get("summary", "")
                link = entry.link
                identificador = f"{titulo}_{link}"
                if any(z in titulo.lower() or z in resumen.lower() for z in zonas) and identificador not in noticias_locales_enviadas:
                    nuevas.append(f"🚨 *Noticia local urgente:*\n📍 {titulo}\n{link}")
                    noticias_locales_enviadas.add(identificador)

        for n in nuevas:
            await app.bot.send_message(chat_id=CHAT_ID, text=n, parse_mode="Markdown")
    except Exception as e:
        logging.error(f"[ALERTA LOCAL INMEDIATA] {e}")

def obtener_partido_river():
    try:
        partidos = {
            "21/06/2025": "⚽ 21:00 - River vs Monterrey (Mundial de Clubes)",
            "25/06/2025": "⚽ 18:00 - Manchester City vs Fluminense"
        }
        hoy = datetime.now().strftime("%d/%m/%Y")
        manana = (datetime.now() + timedelta(days=1)).strftime("%d/%m/%Y")
        if hoy in partidos:
            return f"🗓 *Hoy juega:*\n{partidos[hoy]}"
        elif manana in partidos:
            return f"🗓 *Mañana juega:*\n{partidos[manana]}"
    except Exception as e:
        logging.error(f"[RIVER] {e}")
    return None

# Comandos del bot
async def comando(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        texto = update.message.text
        if texto == "/clima":
            await update.message.reply_text(obtener_clima(), parse_mode="Markdown")
        elif texto == "/noticias":
            await update.message.reply_text(obtener_noticias(), parse_mode="Markdown")
        elif texto == "/alerta":
            alerta = obtener_alerta()
            await update.message.reply_text(alerta if alerta else "✅ *Sin alertas por ahora.*", parse_mode="Markdown")
        elif texto == "/river":
            partido = obtener_partido_river()
            await update.message.reply_text(partido if partido else "📭 *River no juega hoy ni mañana.*", parse_mode="Markdown")
        elif texto == "/resumen":
            await update.message.reply_text(obtener_clima(), parse_mode="Markdown")
            await update.message.reply_text(obtener_noticias(), parse_mode="Markdown")
            alerta = obtener_alerta()
            if alerta:
                await update.message.reply_text(alerta, parse_mode="Markdown")
            partido = obtener_partido_river()
            if partido:
                await update.message.reply_text(partido, parse_mode="Markdown")
        elif texto == "/ayuda":
            await update.message.reply_text(
                "🤖 *Comandos disponibles:*\n"
                "/clima - Muestra el clima actual\n"
                "/noticias - Noticias destacadas\n"
                "/alerta - Alerta meteorológica\n"
                "/river - Próximo partido de River\n"
                "/resumen - Clima + noticias + alerta + River\n"
                "/ayuda - Lista de comandos", parse_mode="Markdown"
            )
    except Exception as e:
        logging.error(f"[COMANDO] {e}")

# Resumen cada 1 minuto y alertas locales
async def resumen_periodico(app):
    try:
        ahora = datetime.now(pytz.timezone("America/Argentina/Buenos_Aires"))
        hora = ahora.strftime("%H:%M")

        if hora in ['00:00', '07:00', '12:00'] and hora not in enviados_clima:
            await app.bot.send_message(chat_id=CHAT_ID, text=obtener_clima(), parse_mode="Markdown")
            enviados_clima.add(hora)

        if hora in ['07:00', '12:00', '18:00'] and hora not in enviados_noticias:
            await app.bot.send_message(chat_id=CHAT_ID, text=obtener_noticias(), parse_mode="Markdown")
            enviados_noticias.add(hora)

        if 7 <= ahora.hour <= 23:
            alerta = obtener_alerta()
            if alerta and alerta not in enviados_alertas:
                await app.bot.send_message(chat_id=CHAT_ID, text=alerta, parse_mode="Markdown")
                enviados_alertas.add(alerta)

        partido = obtener_partido_river()
        if partido and partido not in enviados_partidos:
            await app.bot.send_message(chat_id=CHAT_ID, text=partido, parse_mode="Markdown")
            enviados_partidos.add(partido)

        if ahora.hour == 1:
            enviados_clima.clear()
            enviados_noticias.clear()
            enviados_alertas.clear()
            enviados_partidos.clear()
    except Exception as e:
        logging.error(f"[RESUMEN AUTOMÁTICO] {e}")

# Inicio del bot
async def iniciar_bot():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler(["clima", "noticias", "alerta", "river", "resumen", "ayuda"], comando))

    tz = pytz.timezone("America/Argentina/Buenos_Aires")
    scheduler = AsyncIOScheduler(timezone=tz)
    scheduler.add_job(lambda: asyncio.create_task(resumen_periodico(app)), 'interval', minutes=1)
    scheduler.add_job(lambda: asyncio.create_task(alerta_noticias_locales(app)), 'interval', minutes=5)
    scheduler.start()

    print("✅ BOT FUNCIONANDO CORRECTAMENTE")
    await app.run_polling()

if __name__ == "__main__":
    asyncio.run(iniciar_bot())
