#type: ignore

from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends, status, Request
from sqlalchemy import Date
from sqlalchemy.exc import IntegrityError
from database import SessionLocal
from sqlalchemy.orm import Session
from models import Users, ProductRecurrence, Product, House
from typing import List, Annotated
from pydantic import BaseModel
from auth import get_current_user


def connection_required(current_user: Annotated[Users, Depends(get_current_user)]):
    if not current_user:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")
    return current_user

router = APIRouter(
    prefix="/product_recurrences",
    tags=["products_recurrences"],
    dependencies=[Depends(connection_required)]
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

db_dependency = Annotated[Session, Depends(get_db)]

class ProductRecurrenceBase(BaseModel):
    id: int 
    product_id: int
    house_id: int

class ProductRecurrenceDetailled(ProductRecurrenceBase):
    id: int
    product_id: int
    product_name: str | None = None
    house_id: int
    house_name: str | None = None

class ProductRecurrenceCreate(BaseModel):
    product_id: int


@router.get("/all", response_model=List[ProductRecurrenceBase])
async def get_all_product_recurrences(db: db_dependency, current_user: Annotated[Users, Depends(get_current_user)]):
    product_recurrences = db.query(ProductRecurrence).filter(ProductRecurrence.house_id == current_user.house_id).all()
    if not product_recurrences:        
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No product recurrences found for this house")
    return product_recurrences

@router.get("/all_detailled", response_model=List[ProductRecurrenceDetailled])
async def get_all_product_recurrences_detailled(db: db_dependency, current_user: Annotated[Users, Depends(get_current_user)]):
    product_recurrences = db.query(ProductRecurrence).filter(ProductRecurrence.house_id == current_user.house_id).all()
    if not product_recurrences:        
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No product recurrences found for this house")
    
    list_product_recurrences_detailled = []
    for product_recurrence in product_recurrences:
        product = db.query(Product).filter(Product.id == product_recurrence.product_id).first()
        house = db.query(House).filter(House.id == product_recurrence.house_id).first()
        list_product_recurrences_detailled.append(ProductRecurrenceDetailled(
            id=product_recurrence.id,
            product_id=product_recurrence.product_id,
            product_name=product.name if product else None,
            house_id=product_recurrence.house_id,
            house_name=house.name if house else None
        ))

    return list_product_recurrences_detailled

@router.post("/create", response_model=ProductRecurrenceBase)
async def create_product_recurrence(product_recurrence: ProductRecurrenceCreate, db: db_dependency, current_user: Annotated[Users, Depends(get_current_user)]):
    db_product_recurrence = ProductRecurrence(**product_recurrence.dict(), house_id=current_user.house_id)
    db.add(db_product_recurrence)
    db.commit()
    db.refresh(db_product_recurrence)
    return db_product_recurrence

@router.delete("/delete/{product_recurrence_id}", response_model=ProductRecurrenceBase)
async def delete_product_recurrence(product_recurrence_id: int, db: db_dependency, current_user: Annotated[Users, Depends(get_current_user)]):
    product_recurrence = db.query(ProductRecurrence).filter(ProductRecurrence.id == product_recurrence_id).first()
    if product_recurrence is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product recurrence not found")
    if product_recurrence.house_id != current_user.house_id: #type: ignore
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions to delete this product recurrence")
    db.delete(product_recurrence)
    db.commit()
    return product_recurrence