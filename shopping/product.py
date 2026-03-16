from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends, status, Request
from sqlalchemy import Date
from sqlalchemy.exc import IntegrityError
from database import SessionLocal
from sqlalchemy.orm import Session
from models import Category, Product, Users, ShoppingListItem, ShoppingList, ProductRecurrence
from typing import List, Annotated
from pydantic import BaseModel
from auth import get_current_user
from shopping.list_versioning import increment_current_list_version


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

@router.get("/get/{product_id}", response_model=ProductBase)
async def get_product(product_id: int, db: db_dependency):
    product = db.query(Product).filter(Product.id == product_id).first()
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return product

@router.get("/total", response_model=int)
async def get_total_products(db: db_dependency):
    total = db.query(Product).count()
    return total

@router.get("/search/{name}", response_model=List[ProductBase])
async def search_products(name: str, db: db_dependency):
    products = db.query(Product).filter(Product.name.contains(name.lower())).all()
    return products

@router.delete("/delete/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(product_id: int, db: db_dependency):
    product = db.query(Product).filter(Product.id == product_id).first()
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    affected_rows = db.query(ShoppingListItem.shopping_list_id).filter(ShoppingListItem.product_id == product_id).distinct().all()
    reference = db.query(ShoppingListItem).filter(ShoppingListItem.product_id == product_id).all()
    reference_bis = db.query(ProductRecurrence).filter(ProductRecurrence.product_id == product_id).all()
    for article in reference:
        db.delete(article)
    for recurrence in reference_bis:
        db.delete(recurrence)

    db.delete(product)
    for shopping_list_id, in affected_rows:
        increment_current_list_version(db, shopping_list_id=shopping_list_id)
    db.commit()


@router.put("/update/{product_id}", response_model=ProductBase)
async def update_product(product_id: int, product: ProductCreate, db: db_dependency):
    db_product = db.query(Product).filter(Product.id == product_id).first()
    if db_product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    if product.category_id is not None:
        category = db.query(Category).filter(Category.id == product.category_id).first()
        if category is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")

    db_product.name = product.name.lower() # type: ignore
    db_product.default_price = product.default_price # type: ignore
    db_product.comment = product.comment # type: ignore
    db_product.category_id = product.category_id # type: ignore
    try:
        affected_rows = db.query(ShoppingListItem.shopping_list_id).filter(ShoppingListItem.product_id == product_id).distinct().all()
        for shopping_list_id, in affected_rows:
            increment_current_list_version(db, shopping_list_id=shopping_list_id)
        db.commit()
        db.refresh(db_product)
        return db_product
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Product already exists")

@router.post("/create", response_model=ProductBase)
async def create_product(product: ProductCreate, db: db_dependency):
    if product.category_id is not None:
        category = db.query(Category).filter(Category.id == product.category_id).first()
        if category is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")

    db_product = Product(
        name=product.name.lower(),
        default_price=product.default_price,
        comment=product.comment,
        category_id=product.category_id
    )
    db.add(db_product)
    try:
        db.commit()
        db.refresh(db_product)
        return db_product
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Product already exists")
    
