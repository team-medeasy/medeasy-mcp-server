import logging
from fastapi import APIRouter
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/test",
    tags=["Test Router"]
)

@router.get("/weather/{city}", operation_id="get_weather")
async def getWeather(city: str):
    return {"result": f"{city} weather is very nice"}
