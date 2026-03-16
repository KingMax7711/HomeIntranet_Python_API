from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from database import SessionLocal
from models import Users, ShoppingList, ShoppingListItem, Product, Category
from auth import get_current_user
from typing import Annotated, List
from pydantic import BaseModel, ConfigDict
from shopping.list_versioning import increment_current_list_version


def connection_required(current_user: Annotated[Users, Depends(get_current_user)]):
    if not current_user:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not enough permissions")
    return current_user

router = APIRouter(
    prefix="/shopping_list_globals",
    tags=["shopping_list_globals"],
    dependencies=[Depends(connection_required)]
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

db_dependency = Annotated[Session, Depends(get_db)]

class productLite(BaseModel):
    id: int
    name: str
    default_price: float | None = None
    comment: str | None = None
    category: str | None = None

    model_config = ConfigDict(from_attributes=True)

class category(BaseModel):
    id: int
    name: str

    model_config = ConfigDict(from_attributes=True)

class productBase(BaseModel):
    id: int 
    name: str
    default_price: float | None = None
    comment: str | None = None
    category_id: int | category | None = None

    model_config = ConfigDict(from_attributes=True)

class CategoryInline(BaseModel):
    id: int | None = None
    name: str | None = None

    model_config = ConfigDict(from_attributes=True)


class ProductInline(BaseModel):
    id: int | None = None
    name: str | None = None
    default_price: float | None = None
    comment: str | None = None
    category_id: int | CategoryInline | None = None

    model_config = ConfigDict(from_attributes=True)


class articleRegister(BaseModel):
    product: int | ProductInline
    shopping_list: int #? Envoyer par le front qui connait l'id de la shopping list active, mais on vérifira quand même
    #! On omet volontraiement le champs affected_user, il sera entrer par l'utilisateur plus tard
    in_promotion: bool 
    need_coupons: bool
    price: float
    quantity: int
    comment: str | None = None

    #! Tout les champs suivant sont volontairement omis, ils seront calculé ou entrer plus tard
    # status: str
    # created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class ShoppingListItemBase(BaseModel):
    id: int
    product_id: int
    shopping_list_id: int
    in_promotion: bool 
    need_coupons: bool
    price: float | None = None
    quantity: int
    comment: str | None = None
    status: str # pending / found / not_found / given_up

    model_config = ConfigDict(from_attributes=True)


def _normalize_name(value: str) -> str:
    return value.strip().lower()


def _resolve_or_create_category_id(db: Session, payload: int | CategoryInline | None) -> int | None:
    if payload is None:
        return None

    if isinstance(payload, int):
        category_db = db.query(Category).filter(Category.id == payload).first()
        if category_db is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
        return category_db.id  # type: ignore

    if payload.id is not None:
        category_db = db.query(Category).filter(Category.id == payload.id).first()
        if category_db is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
        return category_db.id  # type: ignore

    if not payload.name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Category must provide either 'id' or 'name'")

    normalized = _normalize_name(payload.name)
    if not normalized:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Category name cannot be empty")

    existing = db.query(Category).filter(Category.name == normalized).first()
    if existing is not None:
        return existing.id  # type: ignore

    new_category = Category(name=normalized)
    db.add(new_category)
    try:
        db.flush()
        return new_category.id  # type: ignore
    except IntegrityError:
        db.rollback()
        existing_after = db.query(Category).filter(Category.name == normalized).first()
        if existing_after is not None:
            return existing_after.id  # type: ignore
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Category already exists")


def _resolve_or_create_product_id(db: Session, payload: int | ProductInline) -> int:
    if isinstance(payload, int):
        product_db = db.query(Product).filter(Product.id == payload).first()
        if product_db is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
        return product_db.id  # type: ignore

    if payload.id is not None:
        product_db = db.query(Product).filter(Product.id == payload.id).first()
        if product_db is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
        return product_db.id  # type: ignore

    if not payload.name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Product must provide either 'id' or 'name'")

    normalized_name = _normalize_name(payload.name)
    if not normalized_name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Product name cannot be empty")

    category_id = _resolve_or_create_category_id(db, payload.category_id)

    existing = db.query(Product).filter(Product.name == normalized_name, Product.category_id == category_id).first()
    if existing is not None:
        return existing.id  # type: ignore

    new_product = Product(
        name=normalized_name,
        default_price=payload.default_price,
        comment=payload.comment,
        category_id=category_id,
    )
    db.add(new_product)
    try:
        db.flush()
        return new_product.id  # type: ignore
    except IntegrityError:
        db.rollback()
        existing_after = db.query(Product).filter(Product.name == normalized_name, Product.category_id == category_id).first()
        if existing_after is not None:
            return existing_after.id  # type: ignore
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Product already exists")

@router.get("/shopping_list_active")
async def get_shopping_list_active(db: db_dependency, current_user: Users = Depends(get_current_user)):
    shopping_list = db.query(ShoppingList).filter(ShoppingList.house_id == current_user.house_id, ShoppingList.status.in_(["preparation", "in_progress"])).first()
    if not shopping_list:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No active shopping list found for the user's house")
    return {"active_shopping_list_id": shopping_list.id}

@router.get("/all_products_lite", response_model=List[productLite])
async def get_all_products(db: db_dependency, current_user: Users = Depends(get_current_user)):
    products = db.query(Product).all()
    liste_result = []
    for p in products:
        category_name = None
        if p.category_id is not None: #type: ignore
            category = db.query(Category).filter(Category.id == p.category_id).first()
            category_name = category.name if category else None
        liste_result.append(productLite(id=p.id, name=p.name, default_price=p.default_price, comment=p.comment, category=category_name)) #type: ignore
    return liste_result
    
@router.get("/all_categories", response_model=List[category])
async def get_all_categories(db: db_dependency, current_user: Users = Depends(get_current_user)):
    categories = db.query(Category).all()
    return categories

@router.post("/register_article", response_model=ShoppingListItemBase)
async def register_article(article: articleRegister, db: db_dependency, current_user: Users = Depends(get_current_user)):
    if article.quantity <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Quantity must be > 0")
    if article.price < 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Price must be >= 0")

    shopping_list = db.query(ShoppingList).filter(ShoppingList.id == article.shopping_list, ShoppingList.house_id == current_user.house_id, ShoppingList.status.in_(["preparation", "in_progress"])).first()
    if not shopping_list:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Active shopping list not found for the user's house")

    try:
        product_id = _resolve_or_create_product_id(db, article.product)

        #? On vérifie que l'article qu'on ajoute soit pas déja dans la liste, si c'est le cas on incrémente uniquement la quantité au lieu de créer une nouvelle ligne
        existing_item = db.query(ShoppingListItem).filter(ShoppingListItem.shopping_list_id == shopping_list.id, ShoppingListItem.product_id == product_id).first()
        if existing_item:
            existing_item.quantity += article.quantity # type: ignore
            increment_current_list_version(db, shopping_list_id=shopping_list.id) # type: ignore

            db.commit()
            db.refresh(existing_item)
            return existing_item

        new_item = ShoppingListItem(
            product_id=product_id,
            shopping_list_id=shopping_list.id,
            in_promotion=article.in_promotion,
            need_coupons=article.need_coupons,
            price=article.price,
            quantity=article.quantity,
            status="pending",
            comment=article.comment
        )
        db.add(new_item)

        # Keep shopping list version consistent with the ETag sync endpoint
        increment_current_list_version(db, shopping_list_id=shopping_list.id) # type: ignore

        db.commit()
        db.refresh(new_item)
        return new_item
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise

@router.post("/create_product_custom", response_model=productBase)
async def create_products_custom(products: ProductInline, db: db_dependency, current_user: Users = Depends(get_current_user)):
    try:
        product_id = _resolve_or_create_product_id(db, products)
        product_db = db.query(Product).filter(Product.id == product_id).first()
        db.commit()
        db.refresh(product_db)
        return product_db
    except HTTPException:
        raise
    except Exception:
        raise

class ProductUpdateCustom(BaseModel):
    id: int
    name: str | None = None
    default_price: float | None = None
    comment: str | None = None
    category_id: int | CategoryInline | None = None

@router.post("/update_product_custom", response_model=productBase)
async def update_products_custom(products: ProductUpdateCustom, db: db_dependency, current_user: Users = Depends(get_current_user)):
    try:
        product_id = products.id
        product_db = db.query(Product).filter(Product.id == product_id).first()
        if not product_db:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

        if products.name is not None:
            product_db.name = products.name.lower() # type: ignore
        if products.default_price is not None:
            product_db.default_price = products.default_price # type: ignore
        if products.comment is not None:
            product_db.comment = products.comment # type: ignore
        if products.category_id is not None:
            category = _resolve_or_create_category_id(db, products.category_id)
            product_db.category_id = category # type: ignore
        affected_rows = db.query(ShoppingListItem.shopping_list_id).filter(ShoppingListItem.product_id == product_id).distinct().all()
        for shopping_list_id, in affected_rows:
            increment_current_list_version(db, shopping_list_id=shopping_list_id)

        product_db = db.query(Product).filter(Product.id == product_id).first()
        db.commit()
        db.refresh(product_db)
        return product_db
    except HTTPException:
        raise
    except Exception:
        raise