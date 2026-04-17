from datetime import date
from click import command
from fastapi import APIRouter, HTTPException, Depends, status, Request
from sqlalchemy import Date
from database import SessionLocal
from sqlalchemy.orm import Session
from models import House, Users, Fridge, FridgeItem
from typing import List, Annotated
from pydantic import BaseModel, ConfigDict
from auth import get_current_user
from shopping.shopping_list_globals import ProductInline, _resolve_or_create_product_id

def connection_required(current_user: Annotated[Users, Depends(get_current_user)]):
    if not current_user:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")
    return current_user

router = APIRouter(
    prefix="/fridge_items",
    tags=["fridge_items"], 
    dependencies=[Depends(connection_required)]
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

db_dependency = Annotated[Session, Depends(get_db)]

class FridgeItemBase(BaseModel):
    id: int 
    product_id: int
    fridge_id: int
    quantity: int
    added_at: date | None = None
    expiration_date: date | None = None
    source: str | None = None
    comment: str | None = None

class FridgeItemCreate(BaseModel):
    product: int | ProductInline
    fridge_id: int
    quantity: int = 1
    expiration_date: date | None = None
    source: str | None = None
    comment: str | None = None

class FridgeItemUpdate(BaseModel):
    fridge_id: int | None = None
    quantity: int | None = None
    expiration_date: date | None = None
    source: str | None = None
    comment: str | None = None

@router.post("/create", response_model=FridgeItemBase)
async def create_fridge_item(fridge_item: FridgeItemCreate, db: db_dependency, current_user: Users = Depends(get_current_user)):
    fridge = db.query(Fridge).filter(Fridge.id == fridge_item.fridge_id).first()
    if not fridge:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fridge not found")
    if fridge.house_id != current_user.house_id: #type: ignore
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You don't have access to this fridge")
    
    product_id = _resolve_or_create_product_id(db, fridge_item.product)
    
    new_fridge_item = FridgeItem(
        product_id=product_id,
        fridge_id=fridge_item.fridge_id,
        quantity=fridge_item.quantity,
        added_at=date.today(),
        expiration_date=fridge_item.expiration_date,
        source=fridge_item.source,
        comment=fridge_item.comment
    )
    db.add(new_fridge_item)
    db.commit()
    db.refresh(new_fridge_item)
    return new_fridge_item

@router.post("/update/{fridge_item_id}", response_model=FridgeItemBase)
async def update_fridge_item(fridge_item_id: int, fridge_item_update: FridgeItemUpdate, db: db_dependency, current_user: Users = Depends(get_current_user)):
    fridge_item = db.query(FridgeItem).filter(FridgeItem.id == fridge_item_id).first()
    if not fridge_item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fridge item not found")
    
    fridge = db.query(Fridge).filter(Fridge.id == fridge_item.fridge_id).first()
    if not fridge:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fridge not found")
    if fridge.house_id != current_user.house_id: #type: ignore
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You don't have access to this fridge item")
    
    if fridge_item_update.fridge_id is not None:
        new_fridge = db.query(Fridge).filter(Fridge.id == fridge_item_update.fridge_id).first()
        if not new_fridge:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="New fridge not found")
        if new_fridge.house_id != current_user.house_id: #type: ignore
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You don't have access to the new fridge")
        fridge_item.fridge_id = fridge_item_update.fridge_id # type: ignore
    
    if fridge_item_update.quantity is not None:
        fridge_item.quantity = fridge_item_update.quantity # type: ignore
    if fridge_item_update.expiration_date is not None:
        fridge_item.expiration_date = fridge_item_update.expiration_date # type: ignore
    if fridge_item_update.source is not None:
        fridge_item.source = fridge_item_update.source # type: ignore
    #! On traite le commentaire différement, un commentaire null signifie une suppression du commentaire et PAS une absence de mise à jour du commentaire
    fridge_item.comment = fridge_item_update.comment # type: ignore
    
    db.commit()
    db.refresh(fridge_item)
    return fridge_item

@router.delete("/{fridge_item_id}")
async def delete_fridge_item(fridge_item_id: int, db: db_dependency, current_user: Users = Depends(get_current_user)):
    fridge_item = db.query(FridgeItem).filter(FridgeItem.id == fridge_item_id).first()
    if not fridge_item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fridge item not found")
    
    fridge = db.query(Fridge).filter(Fridge.id == fridge_item.fridge_id).first()
    if not fridge:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fridge not found")
    if fridge.house_id != current_user.house_id: #type: ignore
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You don't have access to this fridge item")
    
    db.delete(fridge_item)
    db.commit()
    return {"detail": "Fridge item deleted successfully"}
