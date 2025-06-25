import types
from datetime import datetime
import os
import sys
import pytz
import feedparser
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
import bot

class FixedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2025,6,25,12,0,0, tzinfo=tz)

def test_river_juega_hoy(monkeypatch):
    entry = feedparser.FeedParserDict({
        'title': 'River vs Boca',
        'published_parsed': pytz.utc.localize(datetime(2025,6,26,1,0,0)).timetuple(),
    })

    def fake_parse(url):
        return types.SimpleNamespace(entries=[entry])

    monkeypatch.setattr(feedparser, 'parse', fake_parse)
    monkeypatch.setattr(bot, 'datetime', FixedDateTime)

    assert bot.obtener_partido_river() == '🏟 River juega hoy vs Boca a las 22:00'
