# Clima Palomar Bot

Bot automático para Telegram. Informa clima, noticias destacadas (policiales, políticas y locales de Palomar, Caseros y Ciudad Jardín), alertas y próximos partidos de River.

## Comandos

```
/clima     - Clima y alertas actuales
/noticias  - Últimas noticias
/river     - Partido de River del día
/alertas   - Ver alertas activas
/trafico   - Tr\u00e1nsito a Ezeiza
/resumen   - Resumen completo
/ayuda     - Esta ayuda
```

## Instalación

1. Clonar el repositorio:

Este proyecto está diseñado para ejecutarse en **Python 3.10**. Render usa el
archivo `runtime.txt` para fijar la versión `python-3.10.13`.

El bot utiliza **APScheduler** para ejecutar tareas automáticas y se auto-
envía un `ping` cada 14 minutos a la ruta `/ping` para evitar que Render
detenga el contenedor en el plan gratuito.

También consulta alertas climáticas y monitorea cuentas de Twitter para
detectar mensajes urgentes sobre clima, tránsito o seguridad.

Además revisa alertas meteorológicas y noticias urgentes (accidentes,
guerra, cortes de tránsito) para enviarlas al instante.

Además detecta alertas meteorológicas nuevas y noticias urgentes con palabras
clave (asalto, tiroteo, guerra, etc.) para enviarlas inmediatamente al chat.
