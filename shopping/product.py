from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends, status, Request
from sqlalchemy import Date
from database import SessionLocal
from sqlalchemy.orm import Session
from models import Product, Users
from typing import List, Annotated
from pydantic import BaseModel
from auth import get_current_user


def connection_required(current_user: Annotated[Users, Depends(get_current_user)]):
    if not current_user:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")
    return current_user

router = APIRouter(
    prefix="/products",
    tags=["products"],
    dependencies=[Depends(connection_required)]
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

db_dependency = Annotated[Session, Depends(get_db)]

class ProductBase(BaseModel):
    id: int 
    name: str
    default_price: float | None = None
    comment: str | None = None
    category_id: int | None = None

class ProductCreate(BaseModel):
    name: str
    default_price: float | None = None
    comment: str | None = None
    category_id: int | None = None

@router.get("/all", response_model=List[ProductBase])
async def get_all_products(db: db_dependency):
    products = db.query(Product).all()
    return products

@router.get("/{product_id}", response_model=ProductBase)
async def get_product(product_id: int, db: db_dependency):
    product = db.query(Product).filter(Product.id == product_id).first()
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return product

@router.get("/search/{name}", response_model=List[ProductBase])
async def search_products(name: str, db: db_dependency):
    products = db.query(Product).filter(Product.name.contains(name.lower())).all()
    return products

@router.delete("/delete/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(product_id: int, db: db_dependency):
    product = db.query(Product).filter(Product.id == product_id).first()
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    db.delete(product)
    db.commit()

@router.put("/update/{product_id}", response_model=ProductBase)
async def update_product(product_id: int, product: ProductCreate, db: db_dependency):
    db_product = db.query(Product).filter(Product.id == product_id).first()
    if db_product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    db_product.name = product.name.lower() # type: ignore
    db_product.default_price = product.default_price # type: ignore
    db_product.comment = product.comment # type: ignore
    db_product.category_id = product.category_id # type: ignore
    db.commit()
    db.refresh(db_product)
    return db_product

@router.post("/create", response_model=ProductBase)
async def create_product(product: ProductCreate, db: db_dependency):
    db_product = Product(
        name=product.name.lower(),
        default_price=product.default_price,
        comment=product.comment,
        category_id=product.category_id
    )
    db.add(db_product)
    db.commit()
    db.refresh(db_product)
    return db_product