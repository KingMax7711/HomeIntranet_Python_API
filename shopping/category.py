from fastapi import APIRouter, HTTPException, Depends, status, Request
from database import SessionLocal
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from models import Category, Users
from typing import List, Annotated
from pydantic import BaseModel
from auth import get_current_user


def connection_required(current_user: Annotated[Users, Depends(get_current_user)]):
    if not current_user:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")
    return current_user

router = APIRouter(
    prefix="/categories",
    tags=["categories"],
    dependencies=[Depends(connection_required)]
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

db_dependency = Annotated[Session, Depends(get_db)]

class CategoryBase(BaseModel):
    id: int 
    name: str

class CategoryCreate(BaseModel):
    name: str

@router.get("/all", response_model=List[CategoryBase])
async def get_all_categories(db: db_dependency):
    categories = db.query(Category).all()
    return categories

@router.get("/search/{name}", response_model=List[CategoryBase])
async def search_categories(name: str, db: db_dependency):
    categories = db.query(Category).filter(Category.name.contains(name.lower())).all()
    return categories

@router.post("/create", response_model=CategoryBase)
async def create_category(category: CategoryCreate, db: db_dependency):
    db_category = Category(name=category.name.lower())
    db.add(db_category)
    try:
        db.commit()
        db.refresh(db_category)
        return db_category
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Category already exists")

