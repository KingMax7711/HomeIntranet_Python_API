from datetime import date
from fastapi import APIRouter, HTTPException, Depends, status, Request
from sqlalchemy import Date
from database import SessionLocal
from sqlalchemy.orm import Session
from models import House, Users, Fridge
from typing import List, Annotated
from pydantic import BaseModel, ConfigDict
from auth import get_current_user

def connection_required(current_user: Annotated[Users, Depends(get_current_user)]):
    if not current_user:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")
    return current_user

router = APIRouter(
    prefix="/fridges",
    tags=["fridges"], 
    dependencies=[Depends(connection_required)]
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

db_dependency = Annotated[Session, Depends(get_db)]

class FridgeBase(BaseModel):
    id: int 
    house_id: int
    name: str
    main: bool

class FridgeDetailed(FridgeBase):
    id: int
    house_id: int
    house_name: str
    name: str
    main: bool

class FridgeCreate(BaseModel):
    name: str
    main: bool = False

# ??? Déplacé dans fridge_items_view.py pour éviter les duplications
# @router.get("/my_fridges", response_model=list[FridgeDetailed])
# async def get_fridges(db: db_dependency, current_user: Users = Depends(get_current_user)):
#     result = []
#     fridges = db.query(Fridge).filter(Fridge.house_id == current_user.house_id).all()
#     for fridge in fridges:
#         house = db.query(House).filter(House.id == fridge.house_id).first()
#         result.append(FridgeDetailed(
#             id=fridge.id, #type: ignore
#             house_id=fridge.house_id, #type: ignore
#             house_name=house.name if house else None, #type: ignore
#             name=fridge.name, #type: ignore
#             main=fridge.main #type: ignore
#         ))
#     return result

@router.post("/create", response_model=FridgeBase)
async def create_fridge(fridge: FridgeCreate, db: db_dependency, current_user: Users = Depends(get_current_user)):
    if not current_user.house_id: #type: ignore
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User is not in a house")
    if fridge.main:
        existing_main_fridge = db.query(Fridge).filter(Fridge.house_id == current_user.house_id, Fridge.main == True).first()
        if existing_main_fridge:
            existing_main_fridge.main = False # type: ignore

    new_fridge = Fridge(
        house_id=current_user.house_id,
        name=fridge.name,
        main=fridge.main
    )
    db.add(new_fridge)
    db.commit()
    db.refresh(new_fridge)
    return new_fridge

@router.post("/update/{fridge_id}", response_model=FridgeBase)
async def update_fridge(fridge_id: int, fridge_update: FridgeCreate, db: db_dependency, current_user: Users = Depends(get_current_user)):
    fridge = db.query(Fridge).filter(Fridge.id == fridge_id, Fridge.house_id == current_user.house_id).first()
    if not fridge:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fridge not found")

    if fridge_update.main:
        existing_main_fridge = db.query(Fridge).filter(Fridge.house_id == current_user.house_id, Fridge.main == True).first()
        if existing_main_fridge and existing_main_fridge.id != fridge_id: # type: ignore
            existing_main_fridge.main = False # type: ignore

    fridge.name = fridge_update.name # type: ignore
    fridge.main = fridge_update.main # type: ignore
    db.commit()
    db.refresh(fridge)
    return fridge

@router.delete("/delete/{fridge_id}")
async def delete_fridge(fridge_id: int, db: db_dependency, current_user: Users = Depends(get_current_user)):
    fridge = db.query(Fridge).filter(Fridge.id == fridge_id, Fridge.house_id == current_user.house_id).first()
    #! In the future, we need to delete all products linked to this fridge !
    if not fridge:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fridge not found")
    db.delete(fridge)
    db.commit()
    return {"detail": "Fridge deleted successfully"}