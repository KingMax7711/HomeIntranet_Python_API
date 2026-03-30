from datetime import date, datetime

from fastapi import APIRouter, HTTPException, Depends, status, Request
from sqlalchemy import Date
from database import SessionLocal
from sqlalchemy.orm import Session
from passlib.context import CryptContext
from models import Users, House
from typing import List, Annotated
from pydantic import BaseModel, ConfigDict
from auth import get_current_user

def connection_required(current_user: Annotated[Users, Depends(get_current_user)]):
    if not current_user:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")
    if not current_user.id == 1:  #type: ignore # Assuming user with ID 1 is the admin
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")
    return current_user

router = APIRouter(
    prefix="/admin",
    tags=["admin"],
    dependencies=[Depends(connection_required)]
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

db_dependency = Annotated[Session, Depends(get_db)]
bcrypt_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class UserAdminView(BaseModel):
    id: int
    first_name: str
    last_name: str
    email: str
    inscription_date: date | None = None
    privileges: str | None = None
    house_id: int | None = None

    model_config = ConfigDict(from_attributes=True)

class HouseAdminView(BaseModel):
    id: int
    name: str
    invitation_code: str | None = None
    members: List[UserAdminView] = []

class ResetPasswordResponse(BaseModel):
    id: int
    new_password: str


def generate_random_password(length: int = 12) -> str:
    import string
    import random

    characters = string.ascii_letters + string.digits + string.punctuation
    password = ''.join(random.choice(characters) for i in range(length))
    return password

@router.get("/users", response_model=List[UserAdminView])
async def get_all_users(db: db_dependency):
    users = db.query(Users).all()
    return users

@router.get("/users/{user_id}", response_model=UserAdminView)
async def get_user(user_id: int, db: db_dependency):
    user = db.query(Users).filter(Users.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user

@router.get("/houses", response_model=List[HouseAdminView])
async def get_all_houses(db: db_dependency):
    houses = db.query(House).all()
    house_views = []
    for house in houses:
        members = db.query(Users).filter(Users.house_id == house.id).all()
        member_views = [UserAdminView.model_validate(member) for member in members]
        house_view = HouseAdminView(
            id=house.id, #type: ignore
            name=house.name, #type: ignore
            invitation_code=house.invitation_code,  #type: ignore
            members=member_views
        )
        house_views.append(house_view)
    return house_views

@router.get("/houses/{house_id}", response_model=HouseAdminView)
async def get_house(house_id: int, db: db_dependency):
    house = db.query(House).filter(House.id == house_id).first()
    if house is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="House not found")
    members = db.query(Users).filter(Users.house_id == house.id).all()
    member_views = [UserAdminView.model_validate(member) for member in members]
    return HouseAdminView(
        id=house.id, #type: ignore
        name=house.name, #type: ignore
        invitation_code=house.invitation_code,  #type: ignore
        members=member_views
    )

@router.post("/reset_password/{user_id}", response_model=ResetPasswordResponse)
async def reset_password(user_id: int, db: db_dependency):
    user = db.query(Users).filter(Users.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    new_password = generate_random_password()
    user.password = bcrypt_context.hash(new_password) #type: ignore
    user.token_version += 1 #type: ignore
    db.commit()
    db.refresh(user)
    return ResetPasswordResponse(id=user.id, new_password=new_password) #type: ignore

@router.post("/kick_user_from_house/{user_id}", response_model=str)
async def kick_user_from_house(user_id: int, db: db_dependency):
    user = db.query(Users).filter(Users.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    house = db.query(House).filter(House.id == user.house_id).first()
    if house is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="This user is not in a house")
    user.house_id = None #type: ignore
    db.commit()
    db.refresh(user)
    return f"User {user.first_name + ' ' + user.last_name[:1]}. has been kicked from the house {house.name}."

@router.post("/reset_invitations/{house_id}", response_model=str)
async def reset_invitations(house_id: int, db: db_dependency):
    house = db.query(House).filter(House.id == house_id).first()
    if house is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="House not found")
    house.invitation_code = None #type: ignore
    db.commit()
    db.refresh(house)
    return f"Invitations for house {house.name} have been reset."