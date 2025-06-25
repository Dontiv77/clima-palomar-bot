import os
import sys
from datetime import datetime
import types

import feedparser

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
import bot

class FixedDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2025,6,25,12,0,0, tzinfo=tz)

def test_river_juega_hoy(monkeypatch):
    class Entry:
        title = 'River Plate vs Boca - 25/06 22:00'
        published_parsed = datetime(2025,6,25).timetuple()

    class Feed:
        entries = [Entry()]

    monkeypatch.setattr(feedparser, 'parse', lambda *a, **k: Feed())
    monkeypatch.setattr(bot, 'datetime', FixedDateTime)

    assert bot.river_juega_hoy() == '🎯 Hoy juega River: River Plate vs Boca - 25/06 22:00'
