from datetime import datetime
from zoneinfo import ZoneInfo
from app.config import settings

TZ = ZoneInfo(settings.tz)

def to_local(dt_utc: datetime) -> datetime:
    # expects aware UTC datetime
    return dt_utc.astimezone(TZ)

def fmt_local(dt_utc: datetime, with_seconds: bool = False) -> str:
    dt = to_local(dt_utc)
    return dt.strftime("%d.%m.%Y %H:%M:%S" if with_seconds else "%d.%m.%Y %H:%M")
