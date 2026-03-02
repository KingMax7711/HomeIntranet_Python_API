from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends, status, Request
from sqlalchemy import Date
from database import SessionLocal
from sqlalchemy.orm import Session
from models import Mall, Users
from typing import List, Annotated
from pydantic import BaseModel
from auth import get_current_user

def connection_required(current_user: Annotated[Users, Depends(get_current_user)]):
    if not current_user:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")
    return current_user

router = APIRouter(
    prefix="/malls",
    tags=["malls"],
    dependencies=[Depends(connection_required)]
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

db_dependency = Annotated[Session, Depends(get_db)]

class MallBase(BaseModel):
    id: int 
    name: str
    location: str | None = None

class MallCreate(BaseModel):
    name: str
    location: str | None = None

@router.get("/all", response_model=List[MallBase])
async def get_all_malls(db: db_dependency):
    malls = db.query(Mall).all()
    return malls

@router.get("/{mall_id}", response_model=MallBase)
async def get_mall(mall_id: int, db: db_dependency):
    mall = db.query(Mall).filter(Mall.id == mall_id).first()
    if mall is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mall not found")
    return mall

@router.post("/create", response_model=MallBase)
async def create_mall(mall: MallCreate, db: db_dependency):
    db_mall = Mall(
        name=mall.name.lower(),
        location=mall.location
    )
    db.add(db_mall)
    db.commit()
    db.refresh(db_mall)
    return db_mall

@router.delete("/delete/{mall_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_mall(mall_id: int, db: db_dependency):
    mall = db.query(Mall).filter(Mall.id == mall_id).first()
    if mall is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mall not found")
    db.delete(mall)
    db.commit()