from datetime import date
from fastapi import APIRouter, HTTPException, Depends, status, Request
from database import SessionLocal
from sqlalchemy.orm import Session
from models import  Users
from typing import  Annotated, Optional, cast
from pydantic import BaseModel, ConfigDict
from auth import get_current_user, bcrypt_context
from log import api_log

def connection_required(current_user: Annotated[Users, Depends(get_current_user)]):
    if not current_user:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")
    return current_user

router = APIRouter(
    prefix="/users",
    tags=["users"], 
    dependencies=[Depends(connection_required)]
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

db_dependency = Annotated[Session, Depends(get_db)]

class UserPublic(BaseModel):
    id: int
    first_name: str
    last_name: str
    email: str
    inscription_date: date | None = None
    privileges: str | None = None
    house_id: int | None = None
    model_config = ConfigDict(from_attributes=True)

class UserUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None

class UserUpdatePassword(BaseModel):
    current_password: str
    new_password: str


@router.get("/me", response_model=UserPublic)
async def read_user_me(current_user: Annotated[Users, Depends(get_current_user)], request: Request):
    user_id: Optional[int] = cast(Optional[int], getattr(current_user, "id", None))
    email: Optional[str] = cast(Optional[str], getattr(current_user, "email", None))
    api_log(
        "users.me.success",
        level="INFO",
        request=request,
        user_id=user_id,
        email=email,
        tags=["users", "me"],
        correlation_id=request.headers.get("x-correlation-id"),
    )
    return current_user

@router.post("/update", response_model=UserPublic)
async def update_user_me(user_update: UserUpdate, db: db_dependency, current_user: Annotated[Users, Depends(get_current_user)], request: Request):
    db_user = db.query(Users).filter(Users.id == current_user.id).first()

    if user_update.first_name is not None and len(user_update.first_name) < 2:
        api_log("users.update.invalid_first_name", level="WARNING", request=request, tags=["users", "update"], user_id=db_user.id,email=db_user.email, correlation_id=request.headers.get("x-correlation-id")) # type: ignore
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="First name must be at least 2 characters long")
    if user_update.last_name is not None and len(user_update.last_name) < 2:
        api_log("users.update.invalid_last_name", level="WARNING", request=request, tags=["users", "update"], user_id=db_user.id,email=db_user.email, correlation_id=request.headers.get("x-correlation-id")) # type: ignore
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Last name must be at least 2 characters long")

    if user_update.first_name is not None:
        db_user.first_name = user_update.first_name.lower() # type: ignore
    if user_update.last_name is not None:
        db_user.last_name = user_update.last_name.lower() # type: ignore
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    user_id: Optional[int] = cast(Optional[int], getattr(db_user, "id", None))
    email: Optional[str] = cast(Optional[str], getattr(db_user, "email", None))
    api_log(
        "users.update.success",
        level="INFO",
        request=request,
        user_id=user_id,
        email=email,
        tags=["users", "update"],
        correlation_id=request.headers.get("x-correlation-id"),
    )
    return db_user

@router.post("/update_password")
async def update_user_password(user_update: UserUpdatePassword, db: db_dependency, current_user: Annotated[Users, Depends(get_current_user)], request: Request):
    db_user = db.query(Users).filter(Users.id == current_user.id).first()

    if not bcrypt_context.verify(user_update.current_password, db_user.password): # type: ignore
        api_log("users.update_password.invalid_current_password", level="WARNING", request=request, tags=["users", "update_password"], user_id=db_user.id,email=db_user.email, correlation_id=request.headers.get("x-correlation-id")) # type: ignore
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")
    
    if len(user_update.new_password) < 6:
        api_log("users.update_password.weak_new_password", level="WARNING", request=request, tags=["users", "update_password"], user_id=db_user.id,email=db_user.email, correlation_id=request.headers.get("x-correlation-id")) # type: ignore
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="New password must be at least 6 characters long")
    
    if user_update.new_password == user_update.current_password:
        api_log("users.update_password.same_new_password", level="WARNING", request=request, tags=["users", "update_password"], user_id=db_user.id,email=db_user.email, correlation_id=request.headers.get("x-correlation-id")) # type: ignore
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="New password must be different from current password")

    db_user.password = bcrypt_context.hash(user_update.new_password) # type: ignore
    db_user.token_version += 1 # type: ignore
    db.add(db_user)
    db.commit()
    db.refresh(db_user)

    user_id: Optional[int] = cast(Optional[int], getattr(db_user, "id", None))
    email: Optional[str] = cast(Optional[str], getattr(db_user, "email", None))
    api_log(
        "users.update_password.success",
        level="INFO",
        request=request,
        user_id=user_id,
        email=email,
        tags=["users", "update_password"],
        correlation_id=request.headers.get("x-correlation-id"),
    )
    return {"message": "Password updated successfully"}

@router.post("/end_all_sessions")
async def end_all_sessions(db: db_dependency, current_user: Annotated[Users, Depends(get_current_user)], request: Request):
    db_user = db.query(Users).filter(Users.id == current_user.id).first()
    if db_user is None:
        api_log("users.end_all_sessions.user_not_found", level="ERROR", request=request, tags=["users", "end_all_sessions"], user_id=current_user.id,email=current_user.email, correlation_id=request.headers.get("x-correlation-id")) # type: ignore
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    db_user.token_version += 1 # type: ignore
    db.add(db_user)
    db.commit()
    db.refresh(db_user)

    user_id: Optional[int] = cast(Optional[int], getattr(db_user, "id", None))
    email: Optional[str] = cast(Optional[str], getattr(db_user, "email", None))
    api_log(
        "users.end_all_sessions.success",
        level="INFO",
        request=request,
        user_id=user_id,
        email=email,
        tags=["users", "end_all_sessions"],
        correlation_id=request.headers.get("x-correlation-id"),
    )
    return {"message": "All sessions ended successfully"}