# 약 검색 API 호출
import httpx
import os
from fastapi import HTTPException
from dotenv import load_dotenv

load_dotenv()

async def search_medicine_by_name(medicine_name: str):
    api_url = "https://api.medeasy.dev/medicine/search"
    jwt_token = os.getenv("JWT_TOKEN")
    headers = {"Authorization": f"Bearer {jwt_token}"}
    params = {"name": medicine_name}

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(api_url, headers=headers, params=params)
            response.raise_for_status()
            medicines = response.json().get("body", [])

            if not medicines:
                return None

            # 첫 번째 검색 결과 사용 (가장 관련성 높은 결과로 가정)
            return medicines[0]["id"]
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"약 검색 중 오류: {str(e)}")
