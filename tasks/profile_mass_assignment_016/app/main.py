from fastapi import Body, Depends, FastAPI, Header, HTTPException
from sqlalchemy import Column, Integer, MetaData, Table, Text, select, update

from app.db import get_db

app = FastAPI(title="Profiles")

metadata = MetaData()
users = Table(
    "users",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("tenant_id", Integer),
    Column("email", Text),
    Column("display_name", Text),
    Column("timezone", Text),
    Column("role", Text),
    Column("credit_cents", Integer),
)


def load(db, user_id: int) -> dict:
    row = db.execute(select(users).where(users.c.id == user_id)).mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail="User not found")
    return dict(row)


@app.get("/users/me")
def me(x_user_id: int = Header(...), db=Depends(get_db)):
    return load(db, x_user_id)


@app.patch("/users/me")
def update_me(changes: dict = Body(...), x_user_id: int = Header(...), db=Depends(get_db)):
    load(db, x_user_id)
    values = {k: v for k, v in changes.items() if k in users.c}
    if values:
        db.execute(update(users).where(users.c.id == x_user_id).values(**values))
        db.commit()
    return load(db, x_user_id)
