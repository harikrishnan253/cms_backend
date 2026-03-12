from datetime import datetime
import pytz

IST = pytz.timezone("Asia/Kolkata")

def now_ist():
    """Return current datetime in IST."""
    return datetime.now(IST)

def now_ist_naive():
    """Return current IST datetime without tzinfo (for DB columns without timezone)."""
    return datetime.now(IST).replace(tzinfo=None)
