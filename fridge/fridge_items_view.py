from datetime import date
from click import command
from fastapi import APIRouter, HTTPException, Depends, status, Request
from sqlalchemy import Date
from database import SessionLocal
from sqlalchemy.orm import Session
from models import House, Users, Fridge, FridgeItem, Product, Category
from typing import List, Annotated
from pydantic import BaseModel, ConfigDict
from auth import get_current_user

def connection_required(current_user: Annotated[Users, Depends(get_current_user)]):
    if not current_user:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")
    return current_user

router = APIRouter(
    prefix="/fridge_items_view",
    tags=["fridge_items_view"], 
    dependencies=[Depends(connection_required)]
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

db_dependency = Annotated[Session, Depends(get_db)]

class ProductDetailed(BaseModel):
    id: int
    name: str
    comment: str | None = None
    category_id: int | None = None
    category_name: str | None = None

class FridgeItemDetailed(BaseModel):
    id: int 
    product: ProductDetailed
    fridge_id: int
    quantity: int
    added_at: date | None = None
    expiration_date: date | None = None
    source: str | None = None
    comment: str | None = None

class FridgeItemLite(BaseModel):
    id: int
    product_name: str
    quantity: int
    expiration_date: date | None = None

class FridgeRecap(BaseModel):
    fridge_id: int
    fridge_name: str
    number_of_items: int

class FridgeDetailed(BaseModel):
    id: int
    house_id: int
    house_name: str
    name: str
    main: bool
    items: List[FridgeItemDetailed]

@router.get("/my_fridges_recap", response_model=List[FridgeRecap])
async def get_my_fridges_recap(
    current_user: Users = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    fridges = db.query(Fridge).filter(Fridge.house_id == current_user.house_id).all()
    fridge_recaps = []
    for fridge in fridges:
        number_of_items = db.query(FridgeItem).filter(FridgeItem.fridge_id == fridge.id).count()
        fridge_recap = FridgeRecap(
            fridge_id=fridge.id, #type: ignore
            fridge_name=fridge.name, #type: ignore
            number_of_items=number_of_items
        )
        fridge_recaps.append(fridge_recap)
    return fridge_recaps

@router.get("/fridge_detailed/{fridge_id}", response_model=FridgeDetailed)
async def get_fridge_detailed(
    fridge_id: int,
    current_user: Users = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    fridge = db.query(Fridge).filter(Fridge.id == fridge_id).first()
    if not fridge:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fridge not found")
    if fridge.house_id != current_user.house_id: #type: ignore
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")

    items = db.query(FridgeItem).filter(FridgeItem.fridge_id == fridge.id).all()
    house = db.query(House).filter(House.id == fridge.house_id).first() if fridge.house_id else None #type: ignore
    fridge_items = []
    for item in items:
        product = db.query(Product).filter(Product.id == item.product_id).first()
        category = db.query(Category).filter(Category.id == product.category_id).first() if product and product.category_id else None #type: ignore
        fridge_item = FridgeItemDetailed(
            id=item.id, #type: ignore
            product=ProductDetailed(
                id=product.id, #type: ignore
                name=product.name, #type: ignore
                comment=product.comment, #type: ignore
                category_id=product.category_id, #type: ignore
                category_name=category.name if category else None #type: ignore
            ),
            fridge_id=item.fridge_id, #type: ignore
            quantity=item.quantity, #type: ignore
            added_at=item.added_at, #type: ignore
            expiration_date=item.expiration_date, #type: ignore
            source=item.source, #type: ignore
            comment=item.comment #type: ignore
        )
        fridge_items.append(fridge_item)

    return FridgeDetailed(
        id=fridge.id, #type: ignore
        house_id=fridge.house_id, #type: ignore
        house_name=house.name if house else None, #type: ignore
        name=fridge.name, #type: ignore
        main=fridge.main, #type: ignore
        items=fridge_items
    )
