from fastapi import APIRouter

from app.api.v1.routers import auth, contact, market, models, strategies, system

api_router = APIRouter()
api_router.include_router(market.router)
api_router.include_router(models.router)
api_router.include_router(strategies.router)
api_router.include_router(system.router)
api_router.include_router(contact.router)
api_router.include_router(auth.router)
