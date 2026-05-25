"""IP text → text/text text (ip-api.com text API + MongoDB text).

- text API: http://ip-api.com/json/{ip}  (text text, rate limit 45 req/min)
- text: ip_geo_cache text (30 text TTL)
- text/text IP text text text text text None
- text/text text text text None — text text text text

urllib text text text text text text. asyncio.to_thread text event loop text text.
"""

import asyncio
import json
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Optional

from bson import ObjectId

from app.database import get_db, is_db_connected


_INT_CACHE_TTL_DAYS = 30
_FLOAT_HTTP_TIMEOUT = 3.0
_STR_GEO_URL = "http://ip-api.com/json/{ip}"
_SET_PRIVATE_PREFIXES = (
    "127.",
    "10.",
    "192.168.",
    "169.254.",
    "::1",
    "fe80:",
    "fc00:",
    "fd00:",
)


def _is_private_ip(str_ip: str) -> bool:
    if not str_ip or str_ip == "unknown":
        return True
    if str_ip.startswith(_SET_PRIVATE_PREFIXES):
        return True
    # 172.16.0.0/12
    if str_ip.startswith("172."):
        try:
            int_second = int(str_ip.split(".")[1])
            if 16 <= int_second <= 31:
                return True
        except (ValueError, IndexError):
            pass
    return False


def _fetch_geo_sync(str_ip: str) -> Optional[dict]:
    """text HTTP GET — asyncio.to_thread text text."""
    try:
        str_url = _STR_GEO_URL.format(ip=urllib.parse.quote(str_ip, safe=""))
        str_url += "?fields=status,country,countryCode,regionName,city"
        req = urllib.request.Request(str_url, headers={"User-Agent": "MeDIAuto-SaaS/1.0"})
        with urllib.request.urlopen(req, timeout=_FLOAT_HTTP_TIMEOUT) as resp:
            bytes_body = resp.read()
        dict_data = json.loads(bytes_body.decode("utf-8"))
    except Exception:
        return None
    if dict_data.get("status") != "success":
        return None
    return {
        "country": dict_data.get("countryCode", "") or "",
        "country_name": dict_data.get("country", "") or "",
        "city": dict_data.get("city", "") or "",
        "region": dict_data.get("regionName", "") or "",
    }


async def lookup_geo(str_ip: str) -> Optional[dict]:
    """IP → {"country", "country_name", "city", "region"} or None."""
    if _is_private_ip(str_ip):
        return None
    if not is_db_connected():
        # DB text text text text text text
        return await asyncio.to_thread(_fetch_geo_sync, str_ip)

    db = get_db()
    dict_cached = await db.ip_geo_cache.find_one({"str_ip": str_ip})
    if dict_cached:
        dt_expires = dict_cached.get("dt_expires_at")
        if isinstance(dt_expires, datetime):
            if dt_expires.tzinfo is None:
                dt_expires = dt_expires.replace(tzinfo=timezone.utc)
            if dt_expires > datetime.now(timezone.utc):
                return {
                    "country": dict_cached.get("str_country", ""),
                    "country_name": dict_cached.get("str_country_name", ""),
                    "city": dict_cached.get("str_city", ""),
                    "region": dict_cached.get("str_region", ""),
                }

    dict_result = await asyncio.to_thread(_fetch_geo_sync, str_ip)
    if not dict_result:
        return None

    dt_now = datetime.now(timezone.utc)
    try:
        await db.ip_geo_cache.update_one(
            {"str_ip": str_ip},
            {
                "$set": {
                    "str_ip": str_ip,
                    "str_country": dict_result["country"],
                    "str_country_name": dict_result["country_name"],
                    "str_city": dict_result["city"],
                    "str_region": dict_result["region"],
                    "dt_expires_at": dt_now + timedelta(days=_INT_CACHE_TTL_DAYS),
                    "dt_updated_at": dt_now,
                }
            },
            upsert=True,
        )
    except Exception:
        pass
    return dict_result


async def enrich_audit_with_geo(str_audit_log_id: Optional[str], str_ip: str) -> None:
    """text text geo text text text — fire-and-forget text.

    log_audit_event text text _id text text text document text country/city text text.
    text text text.
    """
    if not str_audit_log_id or not str_ip:
        return
    dict_geo = await lookup_geo(str_ip)
    if not dict_geo:
        return
    if not is_db_connected():
        return
    db = get_db()
    try:
        await db.audit_logs.update_one(
            {"_id": ObjectId(str_audit_log_id)},
            {
                "$set": {
                    "str_country": dict_geo["country"],
                    "str_country_name": dict_geo["country_name"],
                    "str_city": dict_geo["city"],
                    "str_region": dict_geo["region"],
                }
            },
        )
    except Exception:
        pass
