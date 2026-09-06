from fastapi import APIRouter

from app.api.v1.routers import (
    admin,
    auth,
    contact,
    market,
    models,
    portfolio,
    strategies,
    system,
)

api_router = APIRouter()
api_router.include_router(market.router)
api_router.include_router(models.router)
api_router.include_router(strategies.router)
api_router.include_router(system.router)
api_router.include_router(contact.router)
api_router.include_router(auth.router)
api_router.include_router(portfolio.router)
api_router.include_router(admin.router)
