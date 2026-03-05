from sqlalchemy import Boolean, Column, Float, ForeignKey, Integer, BigInteger, Index, Null, String, Date, DateTime, func, null, text
from database import Base

class Users(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    # Real Information
    first_name = Column(String, index=True)
    last_name = Column(String, index=True)
    email = Column(String, index=True, unique=True)
    password = Column(String)
    inscription_date = Column(Date, index=True, nullable=True)

    # Utility Information
    house_id = Column(Integer, ForeignKey("houses.id"), nullable=True)

    # Admin
    privileges = Column(String, index=True, nullable=False, server_default="user") # Owner / user
    # Version des refresh tokens : incrémentée pour invalider tous les anciens
    token_version = Column(Integer, default=0, nullable=False, server_default="0")
    # CGU & Privacy Policy acceptance
    accepted_cgu = Column(Boolean, default=False, nullable=False, server_default="false")
    accepted_privacy = Column(Boolean, default=False, nullable=False, server_default="false")

class House(Base):
    __tablename__ = "houses"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    invitation_code = Column(String, index=True, unique=True, nullable=True)

class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, unique=True)

class Mall(Base):
    __tablename__ = "malls"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    location = Column(String, nullable=True)

class Product(Base):
    __tablename__ = "products"

    __table_args__ = (
        Index(
            "uq_products_name_category_notnull",
            "name",
            "category_id",
            unique=True,
            postgresql_where=text("category_id IS NOT NULL"),
        ),
        Index(
            "uq_products_name_category_null",
            "name",
            unique=True,
            postgresql_where=text("category_id IS NULL"),
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    default_price = Column(Float, nullable=True)
    comment = Column(String, nullable=True)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=True)

class ShoppingList(Base):
    __tablename__ = "shopping_lists"

    id = Column(Integer, primary_key=True, index=True)
    house_id = Column(Integer, ForeignKey("houses.id"), nullable=False)
    mall_id = Column(Integer, ForeignKey("malls.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    closed_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String, index=True, nullable=False, server_default="preparation") # preparation / in_progress / completed
    total = Column(Float, nullable=True)
    version = Column(Integer, default=1, nullable=False, server_default="1") # Incrémentée à chaque modification 

class ShoppingListItem(Base):
    __tablename__ = "shopping_list_items"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    shopping_list_id = Column(Integer, ForeignKey("shopping_lists.id"), nullable=False)
    affected_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    in_promotion = Column(Boolean, default=False, nullable=False, server_default="false")
    price = Column(Float, nullable=True)
    quantity = Column(Integer, default=1, nullable=False, server_default="1")
    status = Column(String, index=True, nullable=False, server_default="pending") # pending / found / not_found / given_up
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    comment = Column(String, nullable=True)