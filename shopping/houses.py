from datetime import date
from fastapi import APIRouter, HTTPException, Depends, status, Request
from sqlalchemy import Date
from database import SessionLocal
from sqlalchemy.orm import Session
from models import House, Users
from typing import List, Annotated
from pydantic import BaseModel, ConfigDict
from auth import get_current_user

def connection_required(current_user: Annotated[Users, Depends(get_current_user)]):
    if not current_user:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")
    return current_user

router = APIRouter(
    prefix="/houses",
    tags=["houses"], 
    dependencies=[Depends(connection_required)]
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

db_dependency = Annotated[Session, Depends(get_db)]

class HouseBase(BaseModel):
    id: int 
    name: str

class UserPublic(BaseModel):
    id: int
    first_name: str
    last_name: str
    email: str
    inscription_date: date | None = None
    privileges: str | None = None
    model_config = ConfigDict(from_attributes=True)

class houseDetailed(HouseBase):
    id: int
    name: str
    members: List[UserPublic] | None = None

class HouseCreate(BaseModel):
    name: str



@router.get("/all", response_model=List[HouseBase])
async def get_all_houses(db: db_dependency):
    houses = db.query(House).all()
    return houses

@router.get("/my_house", response_model=houseDetailed)
async def get_house(db: db_dependency, current_user: Users = Depends(get_current_user)):
    house = db.query(House).filter(House.id == current_user.house_id).first()
    if house is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="You don't seem to belong to a house")
    members = [user for user in db.query(Users).filter(Users.house_id == house.id).all()]
    return houseDetailed(id=house.id, name=house.name, members=members) #type: ignore

@router.post("/create", response_model=HouseBase)
async def create_house(house: HouseCreate, db: db_dependency, current_user: Users = Depends(get_current_user)):
    db_user = db.query(Users).filter(Users.id == current_user.id).first()
    if db_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if db_user.house_id is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User already belongs to a house")

    db_house = House(name=house.name.lower())
    db.add(db_house)
    db.commit()
    db.refresh(db_house)

    db_user.house_id = db_house.id # type: ignore
    db.commit()
    db.refresh(db_user)
    return db_house

@router.delete("/delete", status_code=status.HTTP_204_NO_CONTENT)
async def delete_house(db: db_dependency, current_user: Users = Depends(get_current_user)):
    house = db.query(House).filter(House.id == current_user.house_id).first()
    if house is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="You don't seem to belong to a house")
    
    users_in_house = db.query(Users).filter(Users.house_id == house.id).all()
    for user in users_in_house:
        user.house_id = None # type: ignore
    db.delete(house)
    db.commit()

@router.put("/update", response_model=HouseBase)
async def update_house(house: HouseCreate, db: db_dependency, current_user: Users = Depends(get_current_user)):
    db_house = db.query(House).filter(House.id == current_user.house_id).first()
    if db_house is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="You don't seem to belong to a house")
    db_house.name = house.name.lower() #type: ignore
    db.commit()
    db.refresh(db_house)
    return db_house

@router.post('/generate_invitation_code')
async def generate_invitation_code(db: db_dependency, current_user: Users = Depends(get_current_user)):
    house = db.query(House).filter(House.id == current_user.house_id).first()
    if house is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="You don't seem to belong to a house")
    
    # Generate a random 6-character alphanumeric code
    import random
    import string
    invitation_code = ''.join(random.choices(string.ascii_letters + string.digits, k=6))
    
    # Save the invitation code to the database ()
    house.invitation_code = invitation_code # type: ignore
    db.commit()
    db.refresh(house)
    
    return {"invitation_code": invitation_code}

@router.post('/join/{invitation_code}')
async def join_house(invitation_code: str, db: db_dependency, current_user: Users = Depends(get_current_user)):
    house = db.query(House).filter(House.invitation_code == invitation_code).first()
    if house is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Invalid invitation code")
    
    db_user = db.query(Users).filter(Users.id == current_user.id).first()
    if db_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    db_user.house_id = house.id # type: ignore
    db.commit()
    
    return {"message": f"Joined house {house.name} successfully"}

@router.post('/leave')
async def leave_house(db: db_dependency, current_user: Users = Depends(get_current_user)):
    db_user = db.query(Users).filter(Users.id == current_user.id).first()
    if db_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    db_user.house_id = None # type: ignore
    db.commit()
    
    return {"message": "Left house successfully"}

@router.get('/invitation_code')
async def get_invitation_code(db: db_dependency, current_user: Users = Depends(get_current_user)):
    house = db.query(House).filter(House.id == current_user.house_id).first()
    if house is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="You don't seem to belong to a house")
    
    return {"invitation_code": house.invitation_code}