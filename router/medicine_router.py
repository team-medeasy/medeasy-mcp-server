import json
import logging
import os

import httpx
from fastapi import APIRouter, FastAPI, Query, HTTPException, Path
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/medicine",
    tags=["Medicine Router"]
)

@router.get("/search", operation_id="search_medicine", description="의약품 검색 기능, 검색어와 연관이 있는 의약품 리스트를 리턴한다.")
async def search_medicine(
        jwt_token: str = Query(None, description="Users JWT Token"),
        medicine_name: str = Query(None, description="Medicine Name"),
        size: int= Query(1, description="result size")
):
    logger.info("search_medicine 도구 execute")
    api_url = f"{os.getenv("MEDEASY_API_URL")}/medicine/search"

    if not jwt_token:
        return {"error": "authorization token is required"}

    if not medicine_name:
        return {"error": "medicine name is required"}

    # JWT 토큰 설정 (실제 토큰으로 대체 필요)
    headers = {
        "Authorization": f"Bearer {jwt_token}"
    }

    # 쿼리 파라미터 설정
    params = {
        "name": medicine_name,
        "size": size
    }

    # 비동기 HTTP 클라이언트를 사용하여 API 요청 보내기
    async with httpx.AsyncClient() as client:
        try:
            logger.info(f"jwt_token: {headers}")
            response = await client.get(api_url, headers=headers, params=params)
            response.raise_for_status()  # 4XX, 5XX 에러 발생 시 예외 발생
            return response.json()  # API 응답을 JSON으로 변환하여 반환
        except httpx.HTTPStatusError as e:
            # HTTP 상태 코드 에러 처리
            return {"error": f"API 요청 실패: {e.response.status_code}", "detail": e.response.text}
        except httpx.RequestError as e:
            # 네트워크 관련 에러 처리 (타임아웃, 연결 오류 등)
            return {"error": f"API 요청 중 오류 발생: {str(e)}"}


@router.get("/{medicine_id}", operation_id="get_medicine_by_medicine_id", description="medicine_id를 통한 단일 의약품 조회")
async def search_medicine(
        jwt_token: str = Query(None, description="Users JWT Token"),
        medicine_id: str = Path(..., description="Medicine ID")
):
    logger.info("get_medicine_by_medicine_id 도구 execute")
    api_url = f"{os.getenv("MEDEASY_API_URL")}/medicine/medicine_id/{medicine_id}"

    if not jwt_token:
        return {"error": "authorization token is required"}

    # JWT 토큰 설정 (실제 토큰으로 대체 필요)
    headers = {
        "Authorization": f"Bearer {jwt_token}"
    }

    # 비동기 HTTP 클라이언트를 사용하여 API 요청 보내기
    async with httpx.AsyncClient() as client:
        try:
            logger.info(f"jwt_token: {headers}")
            response = await client.get(api_url, headers=headers)
            response.raise_for_status()  # 4XX, 5XX 에러 발생 시 예외 발생
            return response.json()  # API 응답을 JSON으로 변환하여 반환
        except httpx.HTTPStatusError as e:
            # HTTP 상태 코드 에러 처리
            return {"error": f"API 요청 실패: {e.response.status_code}", "detail": e.response.text}
        except httpx.RequestError as e:
            # 네트워크 관련 에러 처리 (타임아웃, 연결 오류 등)
            return {"error": f"API 요청 중 오류 발생: {str(e)}"}

@router.get("/current/medications", operation_id="get_current_medications_information", description="사용자가 현재 복용 중인 의약품 정보 조회")
async def get_current_medications(
        jwt_token: str = Query(None, description="Users JWT Token")
):
    api_url = f"{os.getenv("MEDEASY_API_URL")}/user/medicines/current"

    if not jwt_token:
        return {"error": "authorization token is required"}

    # JWT 토큰 설정 (실제 토큰으로 대체 필요)
    headers = {
        "Authorization": f"Bearer {jwt_token}"
    }

    # 비동기 HTTP 클라이언트를 사용하여 API 요청 보내기
    async with httpx.AsyncClient() as client:
        try:
            logger.info(f"jwt_token: {headers}")
            response = await client.get(api_url, headers=headers)
            response.raise_for_status()  # 4XX, 5XX 에러 발생 시 예외 발생
            return response.json()  # API 응답을 JSON으로 변환하여 반환
        except httpx.HTTPStatusError as e:
            # HTTP 상태 코드 에러 처리
            return {"error": f"API 요청 실패: {e.response.status_code}", "detail": e.response.text}
        except httpx.RequestError as e:
            # 네트워크 관련 에러 처리 (타임아웃, 연결 오류 등)
            return {"error": f"API 요청 중 오류 발생: {str(e)}"}