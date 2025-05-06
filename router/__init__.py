from fastapi import APIRouter
from router.routine_router import router as router_router
from router.medicine_router import router as medicine_router
from router.test_router import router as test_router

api_router = APIRouter()

api_router.include_router(router_router)
api_router.include_router(medicine_router)
api_router.include_router(test_router)
