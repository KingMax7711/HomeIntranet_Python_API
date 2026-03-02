# type: ignore

from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, status, Request, Response, Header
from sqlalchemy import Date
from database import SessionLocal
from sqlalchemy.orm import Session
from models import Product, Mall, Category, ShoppingList, ShoppingListItem, Users, House
from typing import List, Annotated
from pydantic import BaseModel, ConfigDict
from auth import get_current_user


def connection_required(current_user: Annotated[Users, Depends(get_current_user)]):
    if not current_user:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")
    return current_user

def _normalize_etag(value: str) -> str:
    value = value.strip()
    if value.startswith("W/"):
        value = value[2:].lstrip()
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        value = value[1:-1]
    return value


def _if_none_match_matches(if_none_match: str, current_etag: str) -> bool:
    inm = if_none_match.strip()
    if inm == "*":
        return True

    current_norm = _normalize_etag(current_etag)
    candidates = [c.strip() for c in inm.split(",") if c.strip()]
    return any(_normalize_etag(c) == current_norm for c in candidates)

router = APIRouter(
    prefix="/shopping_list_view",
    tags=["shopping_list_view"],
    dependencies=[Depends(connection_required)]
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

db_dependency = Annotated[Session, Depends(get_db)]

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
    quantity: int
    price: float | None = None
    status: str # pending / found / not_found / given_up

    product: ProductBase | None = None
    affected_user: UserInList | None = None

class ShoppingListView(BaseModel):
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

@router.get("/shopping_list/current", response_model=ShoppingListView)
async def get_current_shopping_list_view(db: db_dependency, current_user: Users = Depends(get_current_user)):
    shopping_list = db.query(ShoppingList).filter(
        ShoppingList.house_id == current_user.house_id,
        ShoppingList.status.in_(["preparation", "in_progress"]),
    ).first()
    if shopping_list is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No current shopping list found for this house")
    
    mall = None
    if shopping_list.mall_id is not None:
        mall = db.query(Mall).filter(Mall.id == shopping_list.mall_id).first()

    house = None
    if shopping_list.house_id is not None:
        house = db.query(House).filter(House.id == shopping_list.house_id).first()

    items = db.query(ShoppingListItem).filter(ShoppingListItem.shopping_list_id == shopping_list.id).all()

    items_detailed = []
    for item in items:
        product = None
        if item.product_id is not None:
            product = db.query(Product).filter(Product.id == item.product_id).first()
        
        user = None
        if item.affected_user_id is not None:
            user = db.query(Users).filter(Users.id == item.affected_user_id).first()

        category = None
        if product and product.category_id is not None:
            category = db.query(Category).filter(Category.id == product.category_id).first()
            if category:
                product.category = category.name # type: ignore
        
        
        items_detailed.append(ShoppingListItemDetailed(
            id=item.id,
            quantity=item.quantity,
            price=item.price,
            status=item.status,
            product=ProductBase.from_orm(product) if product else None,
            affected_user=UserInList.from_orm(user) if user else None
        ))

    return ShoppingListView(
        id=shopping_list.id,
        house_name=house.name if house else None,
        mall_name=mall.name if mall else None,
        mall_location=mall.location if mall else None,
        items=items_detailed,
        created_at=shopping_list.created_at,
        closed_at=shopping_list.closed_at,
        status=shopping_list.status,
        total=shopping_list.total,
        version=shopping_list.version
    )


@router.get("/shopping_list/synchronize", response_model=ShoppingListView, responses={304: {"description": "Not Modified"}})
async def synchronize_current_shopping_list_view(db: db_dependency, response: Response, if_none_match: Annotated[str | None, Header(alias="If-None-Match")] = None, current_user: Users = Depends(get_current_user)):
    shopping_list = db.query(ShoppingList).filter(
        ShoppingList.house_id == current_user.house_id,
        ShoppingList.status.in_(["preparation", "in_progress"]),
    ).first()
    print(shopping_list)
    if shopping_list is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No current shopping list found for this house")
    
    current_etag = f'"{shopping_list.version}"'  # type: ignore

    # Standard HTTP: If-None-Match
    if if_none_match is not None and _if_none_match_matches(if_none_match, current_etag):
        raise HTTPException(status_code=status.HTTP_304_NOT_MODIFIED, detail="Shopping list has not been modified since the provided ETag", headers={"ETag": current_etag})

    response.headers["ETag"] = current_etag
    return await get_current_shopping_list_view(db, current_user)