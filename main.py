from datetime import date
from fastapi import FastAPI, Depends, Request
from pydantic import BaseModel, ConfigDict
from typing import  Annotated
from sqlalchemy.orm import Session
from sqlalchemy import text
from fastapi.middleware.cors import CORSMiddleware
from passlib.context import CryptContext
import time
import os
from dotenv import load_dotenv
# Local
from database import engine, SessionLocal
from models import Users
import models
import auth
from shopping.category import router as category_router
from shopping.product import router as product_router
from shopping.shopping_list import router as shopping_list_router
from shopping.shopping_list_items import router as shopping_list_items_router
from shopping.malls import router as malls_router
from shopping.houses import router as houses_router
from shopping.shopping_list_view import router as shopping_list_view_router
from shopping.shopping_list_globals import router as shopping_list_globals_router
from shopping.product_recurrences import router as product_recurrences_router
from shopping.shopping_list_history import router as shopping_list_history_router
from users import router as users_router

from log import api_log

load_dotenv()

app = FastAPI(
    # Permet d’être servi derrière un préfixe (ex: /api) via le reverse proxy
    root_path=os.getenv("API_ROOT_PATH", "/api"),
)
app.title = "NestBoard API"
app.version = str(os.getenv("APP_VERSION", "Unknown"))
START_TIME = time.time()
# Gestion des systèmes par les Admins


# Routes publiques
app.include_router(auth.router)
app.include_router(category_router)
app.include_router(product_router)
app.include_router(shopping_list_router)
app.include_router(shopping_list_items_router)
app.include_router(malls_router)
app.include_router(houses_router)
app.include_router(shopping_list_view_router)
app.include_router(shopping_list_globals_router)
app.include_router(product_recurrences_router)
app.include_router(shopping_list_history_router)
app.include_router(users_router)

# Détermine dynamiquement les origines CORS autorisées
_frontend_origins_env = os.getenv("FRONTEND_ORIGINS", "")
if _frontend_origins_env:
    _allowed_origins = [o.strip() for o in _frontend_origins_env.split(",") if o.strip()]
else:
    # Valeurs par défaut utiles en dev: Vite (5173) et dev server (3000)
    _allowed_origins = [
        "http://localhost:3000",
        "http://localhost:5173",
        "https://192.168.1.40:3000",
        "https://192.168.1.40:5173",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def _on_startup() -> None:
    # Force l'initialisation du logger et la création du répertoire logs
    api_log("app.startup", level="INFO", data={"version": app.version})
    # Créer un admin par défaut si la base est vide
    try:
        create_default_admin_user()
    except Exception as e:
        api_log("app.startup.default_admin.failed", level="ERROR", data={"error": str(e)})

# Exécuter create_all uniquement hors production, sauf si DB_BOOTSTRAP=true
IS_PROD = os.getenv("APP_RELEASE_STATUS", "").lower() == "prod"
DB_BOOTSTRAP = os.getenv("DB_BOOTSTRAP", "").lower() == "true"
if DB_BOOTSTRAP:
    models.Base.metadata.create_all(bind=engine)


bcrypt_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class UserBase(BaseModel):
    # Common fields
    id: int
    first_name: str
    last_name: str
    email: str
    password: str
    inscription_date: date | None = None

    # Admin
    privileges: str | None = None
    model_config = ConfigDict(from_attributes=True)

class UserPublic(BaseModel):
    id: int
    first_name: str
    last_name: str
    email: str
    inscription_date: date | None = None
    privileges: str | None = None
    house_id: int | None = None
    model_config = ConfigDict(from_attributes=True)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

db_dependency = Annotated[Session, Depends(get_db)]

# Création d'un utilisateur admin par défaut si aucun utilisateur n'existe
def create_default_admin_user():
    db = SessionLocal()
    try:
        user_count = db.query(Users).count()
        if user_count == 0:
            default_admin_password = os.getenv("DEFAULT_ADMIN_PASSWORD", "admin")
            default_admin = Users(
                first_name="admin",
                last_name="default",
                email="admin@admin.com",
                password=bcrypt_context.hash(default_admin_password),
                privileges="owner",
            )
            db.add(default_admin)
            db.commit()
            db.refresh(default_admin)
            api_log("users.create.default_admin", level="CRITICAL", user_id=default_admin.id) # type: ignore
    finally:
        db.close()

@app.get("/health")
async def health(db: db_dependency, request: Request):
    uptime_s = round(time.time() - START_TIME, 3)
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
        api_log("health.check.failed", level="ERROR", request=request, correlation_id=request.headers.get("x-correlation-id"))
    return {
        "status": "ok" if db_ok else "degraded",
        "db_health": "ok" if db_ok else "degraded",
        "api_version": app.version + str(' (' + os.getenv("APP_RELEASE_STATUS", "Unknown") + ')'),
        "uptime_seconds": uptime_s,
    }

@app.get("/ping")
async def ping():
    return {"message": "pong"}