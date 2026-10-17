from fastapi import Depends, Header, HTTPException
from sqlalchemy import text

from app.db import get_db


def require_tenant(x_api_key: str = Header(None), db=Depends(get_db)) -> int:
    """Resolve the caller's tenant from their API key, or reject with 401."""
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing API key")
    tenant = db.execute(
        text("SELECT tenant_id FROM api_keys WHERE key = :key AND NOT revoked"),
        {"key": x_api_key},
    ).scalar()
    if tenant is None:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return tenant
