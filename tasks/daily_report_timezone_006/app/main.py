from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import text

from app.db import get_db

app = FastAPI(title="Daily report")


def parse_zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        raise HTTPException(status_code=422, detail="Unknown time zone")


@app.get("/reports/daily")
def daily_report(day: date, tz: str = "UTC", db=Depends(get_db)):
    zone = parse_zone(tz)
    row = db.execute(
        text(
            "SELECT COUNT(*) AS count, COALESCE(SUM(amount_cents), 0) AS total_cents "
            "FROM invoices WHERE created_at::date = :day"
        ),
        {"day": day},
    ).mappings().one()
    return {"day": day.isoformat(), "tz": tz, **row}
