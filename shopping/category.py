from fastapi import APIRouter, HTTPException, Depends, status, Request
from database import SessionLocal
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from models import Category, Users, Product, ShoppingListItem, ShoppingList
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

def increment_current_list_version(db: db_dependency):
    current_list = db.query(ShoppingList).filter(ShoppingList.status.in_(['preparation', 'in_progress'])).first()
    if current_list:
        current_list.version += 1 # type: ignore
        db.commit()

@router.get("/all", response_model=List[CategoryBase])
async def get_all_categories(db: db_dependency):
    categories = db.query(Category).all()
    return categories

@router.get("/search/{name}", response_model=List[CategoryBase])
async def search_categories(name: str, db: db_dependency):
    categories = db.query(Category).filter(Category.name.contains(name.lower())).all()
    return categories

@router.get('/total', response_model=int)
async def get_total_categories(db: db_dependency):
    return db.query(Category).count()


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
    
@router.put("/update/{category_id}", response_model=CategoryBase)
async def update_category(category_id: int, category: CategoryCreate, db: db_dependency):
    db_category = db.query(Category).filter(Category.id == category_id).first()
    if not db_category:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    if len(category.name) == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Category name cannot be empty")
    
    db_category.name = category.name.lower() #type: ignore
    try:
        db.commit()
        db.refresh(db_category)
        increment_current_list_version(db)
        return db_category
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Category with this name already exists")

@router.delete("/delete/{category_id}")
async def delete_category(category_id: int, db: db_dependency):
    force_delete = False
    category = db.query(Category).filter(Category.id == category_id).first()
    if not category:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    
    db_products_linked = db.query(Product).filter(Product.category_id == category_id).all()
    for product in db_products_linked:
        force_delete = True
        product.category_id = None #type: ignore

    db.delete(category)
    db.commit()
    increment_current_list_version(db)
    return {"detail": "Category deleted successfully, take care, some products were linked to this category and have now no category" if force_delete else "Category deleted successfully"}

