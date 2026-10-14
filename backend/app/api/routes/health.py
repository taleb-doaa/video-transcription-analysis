from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db


router = APIRouter(
    prefix="/health",
    tags=["Health"],
)


@router.get("")
def health_check():
    return {"status": "ok"}


@router.get("/db")
def database_health(db: Session = Depends(get_db)):
    result = db.execute(text("SELECT 1"))
    value = result.scalar_one()

    return {
        "status": "ok",
        "database": "postgresql",
        "result": value,
    }