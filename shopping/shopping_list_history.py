from datetime import date, datetime

from fastapi import APIRouter, HTTPException, Depends, responses, status, Request, Header, Response
from sqlalchemy import Date
from database import SessionLocal
from sqlalchemy.orm import Session
from models import ShoppingListItem, ShoppingList, Users, Product, Category, Mall, House
from typing import List, Annotated, cast
from pydantic import BaseModel, ConfigDict
from auth import get_current_user
from shopping.list_versioning import increment_current_list_version

def connection_required(current_user: Annotated[Users, Depends(get_current_user)]):
    if not current_user:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")
    return current_user

router = APIRouter(
    prefix="/shopping_list_history",
    tags=["shopping_list_history"],
    dependencies=[Depends(connection_required)]
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

db_dependency = Annotated[Session, Depends(get_db)]

class ShoppingListRecap(BaseModel):
    id: int 
    house_name: str
    mall_name: str | None
    mall_location: str | None
    number_of_items: int
    total: float | None
    closed_at: datetime | None

    model_config = ConfigDict(from_attributes=True)

class UserInList(BaseModel):
    id: int
    first_name: str
    last_name: str

    model_config = ConfigDict(from_attributes=True)

class ProductBase(BaseModel):
    id: int 
    name: str
    comment: str | None = None
    category: str | None = None

    model_config = ConfigDict(from_attributes=True)

class ShoppingListItemDetailed(BaseModel):
    id: int
    custom_sort_index: int | None = None
    quantity: int
    price: float | None = None
    in_promotion: bool
    need_coupons: bool
    status: str # pending / found / not_found / given_up

    product: ProductBase | None = None
    affected_user: UserInList | None = None

class ShoppingListRecapDetailed(BaseModel):
    id: int 
    # Maisons
    house_name: str | None = None

    # Centres commerciaux
    mall_name: str | None = None
    mall_location: str | None = None

    # Articles
    items: List[ShoppingListItemDetailed] | None = None


    created_at: datetime | None = None
    closed_at: datetime | None = None
    status: str # preparation / in_progress / completed
    total: float | None = None
    version: int

    model_config = ConfigDict(from_attributes=True)

@router.get("/recap_list", response_model=List[ShoppingListRecap])
async def get_shopping_lists_recap(db: db_dependency, current_user: Users = Depends(get_current_user)):
    shopping_lists = db.query(ShoppingList).filter(ShoppingList.house_id == current_user.house_id, ShoppingList.status == "completed").order_by(ShoppingList.created_at.desc()).limit(10).all()
    recaps = []
    for shopping_list in shopping_lists:
        number_of_items = db.query(ShoppingListItem).filter(ShoppingListItem.shopping_list_id == shopping_list.id).count()
        mall = db.query(Mall).filter(Mall.id == shopping_list.mall_id).first() if shopping_list.mall_id else None #type: ignore
        house = db.query(House).filter(House.id == shopping_list.house_id).first()
        recaps.append(ShoppingListRecap(
            id=shopping_list.id, #type: ignore
            house_name=house.name if house else None, #type: ignore
            mall_name=mall.name if mall else None, #type: ignore
            mall_location=mall.location if mall else None, #type: ignore
            number_of_items=number_of_items,
            total=shopping_list.total, #type: ignore
            closed_at=shopping_list.closed_at #type: ignore
        ))
    return recaps

@router.get("/recap/{list_id}", response_model=ShoppingListRecapDetailed)
async def get_shopping_list_recap_detailed(list_id: int, db: db_dependency, current_user: Users = Depends(get_current_user)):
    shopping_list = db.query(ShoppingList).filter(ShoppingList.id == list_id, ShoppingList.house_id == current_user.house_id).first()
    if not shopping_list:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shopping list not found")
    if shopping_list.house_id != current_user.house_id: #type: ignore
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions to access this shopping list")
    if shopping_list.status != "completed": #type: ignore
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Shopping list is not completed yet")
    
    mall = db.query(Mall).filter(Mall.id == shopping_list.mall_id).first() if shopping_list.mall_id else None #type: ignore
    house = db.query(House).filter(House.id == shopping_list.house_id).first()

    items = []
    for item in db.query(ShoppingListItem).filter(ShoppingListItem.shopping_list_id == shopping_list.id).order_by(ShoppingListItem.custom_sort_index.asc().nulls_last(), ShoppingListItem.id.asc()).all(): #type: ignore
        product = db.query(Product).filter(Product.id == item.product_id).first()
        affected_user = db.query(Users).filter(Users.id == item.affected_user_id).first() if item.affected_user_id else None #type: ignore
        category = db.query(Category).filter(Category.id == product.category_id).first() if product and product.category_id else None #type: ignore
        comment = item.comment if item.comment else (product.comment if product and product.comment else None) #type: ignore
        items.append(ShoppingListItemDetailed(
            id=item.id, #type: ignore
            custom_sort_index=item.custom_sort_index, #type: ignore
            quantity=item.quantity, #type: ignore
            price=product.default_price if product else None, #type: ignore
            in_promotion=item.in_promotion, #type: ignore
            need_coupons=item.need_coupons, #type: ignore
            status=item.status, #type: ignore
            product=ProductBase(
                id=product.id, #type: ignore
                name=product.name, #type: ignore
                comment=comment, #type: ignore
                category=category.name if category else None #type: ignore
            ) if product else None,
            affected_user=UserInList(
                id=affected_user.id, #type: ignore
                first_name=affected_user.first_name, #type: ignore
                last_name=affected_user.last_name #type: ignore
            ) if affected_user else None
        ))

    return ShoppingListRecapDetailed(
        id=shopping_list.id, #type: ignore
        house_name=house.name if house else None, #type: ignore
        mall_name=mall.name if mall else None, #type: ignore
        mall_location=mall.location if mall else None, #type: ignore
        items=items,
        created_at=shopping_list.created_at, #type: ignore
        closed_at=shopping_list.closed_at, #type: ignore
        total=shopping_list.total, #type: ignore
        status=shopping_list.status, #type: ignore
        version=shopping_list.version #type: ignore
    )


