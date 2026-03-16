from datetime import date, datetime

from fastapi import APIRouter, HTTPException, Depends, responses, status, Request, Header, Response
from sqlalchemy import Date
from database import SessionLocal
from sqlalchemy.orm import Session
from models import ShoppingListItem, ShoppingList, Users, Product
from typing import List, Annotated, cast
from pydantic import BaseModel, ConfigDict
from auth import get_current_user
from shopping.list_versioning import increment_current_list_version


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
    prefix="/shopping_list_items",
    tags=["shopping_list_items"],
    dependencies=[Depends(connection_required)]
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

db_dependency = Annotated[Session, Depends(get_db)]


class ShoppingListItemBase(BaseModel):
    id: int 
    shopping_list_id: int 
    product_id: int 
    affected_user_id: int | None = None
    custom_sort_index: int | None = None
    in_promotion: bool
    need_coupons: bool
    quantity: int
    price: float | None = None
    comment: str | None = None
    status: str # pending / found / not_found / given_up
    created_at : datetime
    model_config = ConfigDict(from_attributes=True)

class ShoppingListItemCreate(BaseModel):
    shopping_list_id: int 
    product_id: int 
    affected_user_id: int | None = None
    in_promotion: bool
    need_coupons: bool
    quantity: int
    price: float | None = None
    comment: str | None = None


@router.get("/shopping_list/{shopping_list_id}", response_model=List[ShoppingListItemBase])
async def get_shopping_list_items_by_shopping_list(shopping_list_id: int, db: db_dependency, current_user: Users = Depends(get_current_user)):
    shopping_list = db.query(ShoppingList).filter(ShoppingList.id == shopping_list_id).first()
    if shopping_list is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shopping list not found")
    if shopping_list.house_id != current_user.house_id: #type: ignore
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You don't have access to this shopping list")
    shopping_list_items = db.query(ShoppingListItem).filter(ShoppingListItem.shopping_list_id == shopping_list_id).all()
    return shopping_list_items

@router.get(
    "/shopping_list_synch/{shopping_list_id}",
    response_model=List[ShoppingListItemBase],
    responses={304: {"description": "Not Modified"}},
)
async def get_shopping_list_items_synch(
    shopping_list_id: int,
    db: db_dependency,
    response: Response,
    if_none_match: Annotated[str | None, Header(alias="If-None-Match")] = None,
    current_user: Users = Depends(get_current_user)
):
    shopping_list = db.query(ShoppingList).filter(ShoppingList.id == shopping_list_id).first()
    if shopping_list is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shopping list not found")
    if shopping_list.house_id != current_user.house_id: #type: ignore
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You don't have access to this shopping list")

    current_etag = f'"{shopping_list.version}"'  # type: ignore
    
    # Standard HTTP: If-None-Match
    if if_none_match is not None and _if_none_match_matches(if_none_match, current_etag):
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers={"ETag": current_etag})
    
    shopping_list_items = db.query(ShoppingListItem).filter(ShoppingListItem.shopping_list_id == shopping_list_id).all()
    response.headers["ETag"] = current_etag
    return shopping_list_items

@router.post("/create", response_model=ShoppingListItemBase)
async def create_shopping_list_item(shopping_list_item: ShoppingListItemCreate, db: db_dependency, current_user: Users = Depends(get_current_user)):
    shopping_list = db.query(ShoppingList).filter(ShoppingList.id == shopping_list_item.shopping_list_id).first()
    if shopping_list is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shopping list not found")
    if shopping_list.house_id != current_user.house_id: #type: ignore
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You don't have access to this shopping list")

    db_shopping_list_item = ShoppingListItem(
        shopping_list_id=shopping_list_item.shopping_list_id,
        product_id=shopping_list_item.product_id,
        affected_user_id=shopping_list_item.affected_user_id,
        in_promotion=shopping_list_item.in_promotion,
        need_coupons=shopping_list_item.need_coupons,
        quantity=shopping_list_item.quantity,
        price=shopping_list_item.price,
        comment="", #! On omet volontairement le commentaire, remplacer par le commentaire du produit
        status="pending",
        created_at=datetime.utcnow()
    )
    db.add(db_shopping_list_item)
    increment_current_list_version(db, shopping_list_id=db_shopping_list_item.shopping_list_id) #type: ignore
    db.commit()
    db.refresh(db_shopping_list_item)
    return db_shopping_list_item

@router.delete("/delete/{shopping_list_item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_shopping_list_item(shopping_list_item_id: int, db: db_dependency, current_user: Users = Depends(get_current_user)):
    shopping_list_item = db.query(ShoppingListItem).filter(ShoppingListItem.id == shopping_list_item_id).first()
    shopping_list = db.query(ShoppingList).filter(ShoppingList.id == shopping_list_item.shopping_list_id).first() if shopping_list_item else None
    if shopping_list is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shopping list not found")
    if shopping_list_item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shopping list item not found")
    if shopping_list.house_id != current_user.house_id: #type: ignore
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You don't have access to this shopping list")
    
    db.delete(shopping_list_item)
    increment_current_list_version(db, shopping_list_id=shopping_list_item.shopping_list_id) #type: ignore
    db.commit()

@router.put("/update/{shopping_list_item_id}", response_model=ShoppingListItemBase)
async def update_shopping_list_item(shopping_list_item_id: int, shopping_list_item: ShoppingListItemCreate, db: db_dependency, current_user: Users = Depends(get_current_user)):
    db_shopping_list_item = db.query(ShoppingListItem).filter(ShoppingListItem.id == shopping_list_item_id).first()
    if db_shopping_list_item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shopping list item not found")
    shopping_list = db.query(ShoppingList).filter(ShoppingList.id == db_shopping_list_item.shopping_list_id).first()
    if shopping_list is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shopping list not found")
    if shopping_list.house_id != current_user.house_id: #type: ignore
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You don't have access to this shopping list")
    db_shopping_list_item.shopping_list_id = shopping_list_item.shopping_list_id # type: ignore
    db_shopping_list_item.product_id = shopping_list_item.product_id # type: ignore
    db_shopping_list_item.affected_user_id = shopping_list_item.affected_user_id # type: ignore
    db_shopping_list_item.in_promotion = shopping_list_item.in_promotion # type: ignore
    db_shopping_list_item.quantity = shopping_list_item.quantity # type: ignore
    db_shopping_list_item.price = shopping_list_item.price # type: ignore
    db_shopping_list_item.comment = shopping_list_item.comment # type: ignore
    increment_current_list_version(db, shopping_list_id=db_shopping_list_item.shopping_list_id) #type: ignore
    db.commit()
    db.refresh(db_shopping_list_item)
    return db_shopping_list_item

@router.post("/update_status/{shopping_list_item_id}", response_model=ShoppingListItemBase)
async def update_shopping_list_item_status(shopping_list_item_id: int, new_status: str, db: db_dependency, current_user: Users = Depends(get_current_user)):
    db_shopping_list_item = db.query(ShoppingListItem).filter(ShoppingListItem.id == shopping_list_item_id).first()
    if db_shopping_list_item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shopping list item not found") 
    shopping_list = db.query(ShoppingList).filter(ShoppingList.id == db_shopping_list_item.shopping_list_id).first()
    if shopping_list is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shopping list not found") 
    if shopping_list.house_id != current_user.house_id: #type: ignore
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You don't have access to this shopping list") 
    autorized_statuses = ["pending", "found", "not_found", "given_up"]
    if new_status not in autorized_statuses:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Status must be one of {autorized_statuses}")
    db_shopping_list_item.status = new_status # type: ignore
    increment_current_list_version(db, shopping_list_id=db_shopping_list_item.shopping_list_id) #type: ignore
    db.commit()
    db.refresh(db_shopping_list_item)
    return db_shopping_list_item

@router.post("/update_price/{shopping_list_item_id}", response_model=ShoppingListItemBase)
async def update_shopping_list_item_price(shopping_list_item_id: int, new_price: float, db: db_dependency, current_user: Users = Depends(get_current_user)):
    db_shopping_list_item = db.query(ShoppingListItem).filter(ShoppingListItem.id == shopping_list_item_id).first()
    if db_shopping_list_item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shopping list item not found") 
    shopping_list = db.query(ShoppingList).filter(ShoppingList.id == db_shopping_list_item.shopping_list_id).first()
    if shopping_list is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shopping list not found") 
    if shopping_list.house_id != current_user.house_id: #type: ignore
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You don't have access to this shopping list") 
    db_shopping_list_item.price = new_price # type: ignore
    increment_current_list_version(db, shopping_list_id=db_shopping_list_item.shopping_list_id) #type: ignore
    db.commit()
    db.refresh(db_shopping_list_item)
    return db_shopping_list_item

@router.post("/update_quantity/{shopping_list_item_id}", response_model=ShoppingListItemBase)
async def update_shopping_list_item_quantity(shopping_list_item_id: int, new_quantity: int, db: db_dependency, current_user: Users = Depends(get_current_user)):
    db_shopping_list_item = db.query(ShoppingListItem).filter(ShoppingListItem.id == shopping_list_item_id).first()
    if db_shopping_list_item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shopping list item not found") 
    shopping_list = db.query(ShoppingList).filter(ShoppingList.id == db_shopping_list_item.shopping_list_id).first()
    if shopping_list is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shopping list not found") 
    if shopping_list.house_id != current_user.house_id: #type: ignore
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You don't have access to this shopping list") 
    db_shopping_list_item.quantity = new_quantity # type: ignore
    increment_current_list_version(db, shopping_list_id=db_shopping_list_item.shopping_list_id) #type: ignore
    db.commit()
    db.refresh(db_shopping_list_item)
    return db_shopping_list_item

@router.post("/affect_to_user/{shopping_list_item_id}/{user_id}", response_model=ShoppingListItemBase)
async def affect_shopping_list_item_to_user(shopping_list_item_id: int, user_id: int, db: db_dependency, current_user: Users = Depends(get_current_user)):
    db_shopping_list_item = db.query(ShoppingListItem).filter(ShoppingListItem.id == shopping_list_item_id).first()
    if db_shopping_list_item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shopping list item not found") 
    shopping_list = db.query(ShoppingList).filter(ShoppingList.id == db_shopping_list_item.shopping_list_id).first()
    if shopping_list is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shopping list not found") 
    if shopping_list.house_id != current_user.house_id: #type: ignore
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You don't have access to this shopping list") 
    user = db.query(Users).filter(Users.id == user_id).first()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.house_id != shopping_list.house_id: #type: ignore
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="User doesn't belong to the house of the shopping list")
    db_shopping_list_item.affected_user_id = user_id # type: ignore
    increment_current_list_version(db, shopping_list_id=db_shopping_list_item.shopping_list_id) #type: ignore
    db.commit()
    db.refresh(db_shopping_list_item)
    return db_shopping_list_item

class CustomUpdateShoppingListItem(BaseModel):
    quantity: int | None = None
    price: float | None = None
    in_promotion: bool | None = None
    need_coupons: bool | None = None
    comment: str | None = None

@router.post("/custom_update/{shopping_list_item_id}", response_model=ShoppingListItemBase)
async def custom_update_shopping_list_item(shopping_list_item_id: int, update_data: CustomUpdateShoppingListItem, db: db_dependency, current_user: Users = Depends(get_current_user)):
    db_shopping_list_item = db.query(ShoppingListItem).filter(ShoppingListItem.id == shopping_list_item_id).first()
    if db_shopping_list_item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shopping list item not found") 
    shopping_list = db.query(ShoppingList).filter(ShoppingList.id == db_shopping_list_item.shopping_list_id).first()
    if shopping_list is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shopping list not found") 
    if shopping_list.house_id != current_user.house_id: #type: ignore
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You don't have access to this shopping list") 
    if update_data.quantity is not None:
        db_shopping_list_item.quantity = update_data.quantity # type: ignore
    if update_data.price is not None:
        db_shopping_list_item.price = update_data.price # type: ignore
    if update_data.in_promotion is not None:
        db_shopping_list_item.in_promotion = update_data.in_promotion # type: ignore
    if update_data.need_coupons is not None:
        db_shopping_list_item.need_coupons = update_data.need_coupons # type: ignore
        
    #! Le commentaire est traité à part, on le met à jour même s'il est à None, pour permettre de supprimer un commentaire existant
    db_linked_product = db.query(Product).filter(Product.id == db_shopping_list_item.product_id).first()
    linked_product_comment = cast(str | None, db_linked_product.comment) if db_linked_product is not None else None
    if linked_product_comment == update_data.comment:
        db_shopping_list_item.comment = None # type: ignore
    else:
        db_shopping_list_item.comment = update_data.comment # type: ignore
    increment_current_list_version(db, shopping_list_id=db_shopping_list_item.shopping_list_id) #type: ignore
    db.commit()
    db.refresh(db_shopping_list_item)
    return db_shopping_list_item