from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy import null
from database import SessionLocal
from sqlalchemy.orm import Session
from models import ShoppingList, ShoppingListItem, Users, ProductRecurrence, Product
from typing import List, Annotated
from pydantic import BaseModel, ConfigDict
from auth import get_current_user
from shopping.list_versioning import increment_current_list_version


def connection_required(current_user: Annotated[Users, Depends(get_current_user)]):
    if not current_user:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")
    return current_user


router = APIRouter(
    prefix="/shopping_lists",
    tags=["shopping_lists"],
    dependencies=[Depends(connection_required)]
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

db_dependency = Annotated[Session, Depends(get_db)]

class ShoppingListBase(BaseModel):
    id: int 
    house_id: int 
    mall_id: int | None = None
    created_at: datetime | None = None
    closed_at: datetime | None = None
    status: str # preparation / in_progress / completed
    total: float | None = None
    version: int

    model_config = ConfigDict(from_attributes=True)

class ShoppingListCreate(BaseModel):
    mall_id: int | None = None

@router.get("/all", response_model=List[ShoppingListBase])
async def get_all_shopping_lists(db: db_dependency, current_user: Users = Depends(get_current_user)):
    shopping_lists = db.query(ShoppingList).filter(ShoppingList.house_id == current_user.house_id).all() #type: ignore
    if shopping_lists is None or len(shopping_lists) == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No shopping list found for this house")
    return shopping_lists

@router.get("/get/{shopping_list_id}", response_model=ShoppingListBase)
async def get_shopping_list(shopping_list_id: int, db: db_dependency, current_user: Users = Depends(get_current_user)):
    shopping_list = db.query(ShoppingList).filter(ShoppingList.id == shopping_list_id).first()
    if shopping_list is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shopping list not found")
    if shopping_list.house_id != current_user.house_id: #type: ignore
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You don't have access to this shopping list")
    return shopping_list

@router.post("/create_fresh", response_model=ShoppingListBase)
async def create_shopping_list(shopping_list: ShoppingListCreate, db: db_dependency, current_user: Users = Depends(get_current_user)):
    if current_user.house_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You don't belong to a house")
    old_shopping_list = db.query(ShoppingList).filter(
        ShoppingList.house_id == current_user.house_id,
        ShoppingList.status.in_(["preparation", "in_progress"]),
    ).first()  # type: ignore
    if old_shopping_list is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A shopping list is already in preparation or in progress for this house. Please close it before creating a new one.")
    
    db_shopping_list = ShoppingList(
        house_id=current_user.house_id,
        mall_id=shopping_list.mall_id,
        created_at=datetime.now(), # type: ignore
        status="preparation"
    )
    db.add(db_shopping_list)
    db.commit()
    db.refresh(db_shopping_list)

    product_recurrences = db.query(ProductRecurrence).filter(ProductRecurrence.house_id == current_user.house_id).all() #type: ignore
    for product_recurrence in product_recurrences:
        db_product = db.query(Product).filter(Product.id == product_recurrence.product_id).first()

        db_shopping_list_item = ShoppingListItem(
            shopping_list_id=db_shopping_list.id,
            product_id=product_recurrence.product_id,
            affected_user_id=None,
            in_promotion=False,
            quantity=1,
            price=db_product.default_price if db_product else None,
            comment=None,
            status="pending",
            created_at=datetime.now()
        )
        db.add(db_shopping_list_item)

    db.commit()
    db.refresh(db_shopping_list)
    return db_shopping_list

@router.post("/create_from_old/{old_shopping_list_id}", response_model=ShoppingListBase)
async def create_shopping_list_from_old(new_shopping_list: ShoppingListCreate, old_shopping_list_id: int, db: db_dependency, current_user: Users = Depends(get_current_user)):
    old_shopping_list = db.query(ShoppingList).filter(ShoppingList.id == old_shopping_list_id).first()
    if old_shopping_list is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Old shopping list not found")
    if old_shopping_list.house_id != current_user.house_id: #type: ignore
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You don't have access to this shopping list")
    if old_shopping_list.status == "preparation" or old_shopping_list.status == "in_progress": #type: ignore
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="The old shopping list is still in preparation or in progress. Please close it before creating a new one.")
    
    article_not_found_in_old_list = db.query(ShoppingListItem).filter(ShoppingListItem.shopping_list_id == old_shopping_list_id, ShoppingListItem.status == "not_found").all()
    
    
    db.commit()
    db.refresh(old_shopping_list)

    db_shopping_list = ShoppingList(
        house_id=current_user.house_id,
        mall_id=new_shopping_list.mall_id,
        created_at=datetime.now(),
        status="preparation"
    )
    db.add(db_shopping_list)
    db.commit()
    db.refresh(db_shopping_list)

    for item in article_not_found_in_old_list:
        db_shopping_list_item = ShoppingListItem(
            shopping_list_id=db_shopping_list.id,
            product_id=item.product_id,
            affected_user_id=None,
            in_promotion=item.in_promotion,
            quantity=item.quantity,
            price=item.price,
            comment=item.comment,
            status="pending",
            created_at=datetime.now()
        )
        db.add(db_shopping_list_item)
    db.commit()
    db.refresh(db_shopping_list)

    product_recurrences = db.query(ProductRecurrence).filter(ProductRecurrence.house_id == current_user.house_id).all() #type: ignore
    for product_recurrence in product_recurrences:
        already_in_list = db.query(ShoppingListItem).filter(ShoppingListItem.shopping_list_id == db_shopping_list.id, ShoppingListItem.product_id == product_recurrence.product_id).first()
        if already_in_list is None:
            db_product = db.query(Product).filter(Product.id == product_recurrence.product_id).first()

            db_shopping_list_item = ShoppingListItem(
                shopping_list_id=db_shopping_list.id,
                product_id=product_recurrence.product_id,
                affected_user_id=None,
                in_promotion=False,
                quantity=1,
                price=db_product.default_price if db_product else None,
                comment=None,
                status="pending",
                created_at=datetime.now()
            )
            db.add(db_shopping_list_item)
    db.commit()
    db.refresh(db_shopping_list)
    return db_shopping_list
    

@router.post("/update/{shopping_list_id}", response_model=ShoppingListBase)
async def update_shopping_list(shopping_list_id: int, shopping_list: ShoppingListCreate, db: db_dependency):
    db_shopping_list = db.query(ShoppingList).filter(ShoppingList.id == shopping_list_id).first()
    if db_shopping_list is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shopping list not found")
    
    db_shopping_list.house_id = shopping_list.house_id # type: ignore
    db_shopping_list.mall_id = shopping_list.mall_id # type: ignore
    increment_current_list_version(db, shopping_list_id=shopping_list_id)
    db.commit()
    db.refresh(db_shopping_list)
    return db_shopping_list

@router.post("/close/{shopping_list_id}", response_model=ShoppingListBase)
async def close_shopping_list(shopping_list_id: int, db: db_dependency, current_user: Users = Depends(get_current_user)):
    shopping_list = db.query(ShoppingList).filter(ShoppingList.id == shopping_list_id).first()
    if shopping_list is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shopping list not found")
    if shopping_list.house_id != current_user.house_id: #type: ignore
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You don't have access to this shopping list")
    
    total_list_items = db.query(ShoppingListItem).filter(ShoppingListItem.shopping_list_id == shopping_list_id).all()
    shopping_list.total = sum(item.price * item.quantity if item.price else 0 for item in total_list_items) # type: ignore #!!! Attention à calculer le total plus tard
    shopping_list.closed_at = datetime.now() # type: ignore
    shopping_list.status = "completed" # type: ignore
    db.commit()
    db.refresh(shopping_list)
    return shopping_list

@router.post("/set_in_progress/{shopping_list_id}", response_model=ShoppingListBase)
async def set_in_progress_shopping_list(shopping_list_id: int, db: db_dependency, current_user: Users = Depends(get_current_user)):
    shopping_list = db.query(ShoppingList).filter(ShoppingList.id == shopping_list_id).first()
    if shopping_list is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shopping list not found")
    if shopping_list.house_id != current_user.house_id: #type: ignore
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You don't have access to this shopping list")
    if shopping_list.status != "preparation": #type: ignore
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only shopping lists in preparation can be set to in progress")
    
    shopping_list.status = "in_progress" # type: ignore
    increment_current_list_version(db, shopping_list_id=shopping_list_id)
    db.commit()
    db.refresh(shopping_list)
    return shopping_list

@router.get("/current_shopping_list", response_model=ShoppingListBase)
async def get_current_shopping_list(db: db_dependency, current_user: Users = Depends(get_current_user)):
    shopping_list = db.query(ShoppingList).filter(
        ShoppingList.house_id == current_user.house_id,
        ShoppingList.status.in_(["preparation", "in_progress"]),
    ).first()
    if shopping_list is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No current shopping list found for this house")
    return shopping_list


@router.post("/close_all_current", response_model=List[ShoppingListBase])
async def close_all_current_shopping_lists(db: db_dependency, current_user: Users = Depends(get_current_user)):
    shopping_lists = db.query(ShoppingList).filter(
        ShoppingList.house_id == current_user.house_id,
        ShoppingList.status.in_(["preparation", "in_progress"]),
    ).all()  # type: ignore
    if shopping_lists is None or len(shopping_lists) == 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No current shopping list found for this house")
    
    for shopping_list in shopping_lists:
        total_list_items = db.query(ShoppingListItem).filter(ShoppingListItem.shopping_list_id == shopping_list.id).all()
        shopping_list.total = sum(item.price * item.quantity if item.price else 0 for item in total_list_items) # type: ignore #!!! Attention à calculer le total plus tard
        shopping_list.closed_at = datetime.now() # type: ignore
        shopping_list.status = "completed" # type: ignore
    db.commit()
    return shopping_lists

@router.get("/shopping_list/last_closed", response_model=ShoppingListBase)
async def get_last_closed_shopping_list(db: db_dependency, current_user: Users = Depends(get_current_user)):
    shopping_list = db.query(ShoppingList).filter(ShoppingList.house_id == current_user.house_id, ShoppingList.status == "completed").order_by(ShoppingList.closed_at.desc()).first()
    if shopping_list is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No closed shopping list found for this house")
    return shopping_list

@router.post("/sort_items/{shopping_list_id}", response_model=ShoppingListBase)
async def sort_items_in_shopping_list(shopping_list_id: int, sorted_item_ids: List[int], db: db_dependency, current_user: Users = Depends(get_current_user)):
    shopping_list = db.query(ShoppingList).filter(ShoppingList.id == shopping_list_id).first()
    if shopping_list is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shopping list not found")
    if shopping_list.house_id != current_user.house_id: #type: ignore
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You don't have access to this shopping list")
    
    items = db.query(ShoppingListItem).filter(ShoppingListItem.shopping_list_id == shopping_list_id).all()
    item_dict = {item.id: item for item in items}
    
    for index, item_id in enumerate(sorted_item_ids):
        if item_id in item_dict:
            item_dict[item_id].custom_sort_index = index # type: ignore
    
    increment_current_list_version(db, shopping_list_id=shopping_list_id)
    db.commit()
    db.refresh(shopping_list)
    return shopping_list