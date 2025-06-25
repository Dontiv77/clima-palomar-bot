import os
import sys
from datetime import datetime
import types

import requests

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
import bot

class FixedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2025,6,25,12,0,0, tzinfo=tz)

def test_river_juega_hoy(monkeypatch):
    html = '<div>Liga Profesional - River Plate vs Boca - 25/06 22:00</div>'

    class Resp:
        text = html

    monkeypatch.setattr(requests, 'get', lambda *a, **k: Resp())
    monkeypatch.setattr(bot, 'datetime', FixedDateTime)

    assert bot.obtener_partido_river() == '🏟 River juega hoy a las 22:00 vs Boca (Liga Profesional)'
