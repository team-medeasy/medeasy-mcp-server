import logging
import os
from datetime import date, datetime

import httpx
import pytz
from fastapi import APIRouter, FastAPI, Query, HTTPException
from dotenv import load_dotenv
from service.medicine_service import search_medicine_id_by_name
from service.user_schedule_service import get_user_schedule, mapping_user_schedule_ids

load_dotenv()
logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/routine",
    tags=["Routine Router"]
)

medeasy_api_url = os.getenv("MEDEASY_API_URL")

# 한국 시간대 객체 생성 - 전역 범위에 정의
kst = pytz.timezone('Asia/Seoul')

@router.post(
    path="/register",
    operation_id="create_new_medicine_routine",
    description="새로운 복약 일정을 등록할 때 사용하는 도구"
)
async def create_medicine_routine(
        medicine_name: str = Query(description="medicine name", required=True),
        nickname: str = Query(default=None, description="medicine nickname", required=False),
        dose: int = Query(default=1, description="dose", ge=1, le=10, required=False),
        total_quantity: int = Query(description="medicine's total quantity", ge=1, le=200, required=True),
        interval_days: int = Query(default=1, description="medicine's interval days", ge=1, le=30, required=False),
        user_schedule_names: list[str] = Query(description="Schedule names for when the user takes medicine", required=True),
        jwt_token: str = Query(description="Users JWT Token", required=True),
):
    medicine_id=await search_medicine_id_by_name(jwt_token, medicine_name)

    # medicine_id 검색
    if medicine_id is None:
        raise HTTPException(status_code=400, detail=f"존재하지 않는 약입니다.")

    # user_schedules 조회
    schedules = await get_user_schedule(jwt_token)

    # OpenAI로 입력받은 user_schedule_names와 어울리는 user_schedule_id 추출
    matched_ids=await mapping_user_schedule_ids(schedules, user_schedule_names)

    if not matched_ids:
        return {"복약 일정을 등록하실 시간대가 없습니다. 먼저 시간대를 설정해주세요."}

    # 루틴 생성 API 호출
    routine_url = f"{medeasy_api_url}/routine"
    body = {
        "medicine_id": medicine_id,
        "nickname": nickname,
        "dose": dose,
        "total_quantity": total_quantity,
        "interval_days": interval_days,
        "user_schedule_ids": matched_ids,
    }

    headers = {"Authorization": f"Bearer {jwt_token}", "Content-Type": "application/json"}

    async with httpx.AsyncClient() as client:
        resp = await client.post(routine_url, headers=headers, json=body)
        if resp.status_code >= 400:
            raise HTTPException(status_code=502, detail=f"루틴 생성 실패: {resp.text}")
        return resp.json()

@router.get("", operation_id="get_medicine_routine_list_by_date")
async def get_medicine_routine_list_by_date(
        jwt_token: str = Query(description="Users JWT Token", required=True),
        start_date: date = Query(default= datetime.now(kst).date(),description="Query start date (default: today)"),
        end_date: date = Query(default=datetime.now(kst).date(),description="Query start date (default: today)")
):
    url = f"{medeasy_api_url}/routine"
    # Query String 파라미터로 start_date, end_date 전달
    params = {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat()
    }

    headers = {"Authorization": f"Bearer {jwt_token}", "Content-Type": "application/json"}

    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=headers, params=params)
        if resp.status_code >= 400:
            raise HTTPException(status_code=resp.status_code, detail=f"조회 실패: {resp.text}")
        return resp.json()


@router.get(
    "/prescription",
    operation_id="register_routine_by_prescription",
    description="사용자가 처방전 촬영으로 루틴 등록을 원할 때 사용하는 도구"
)
async def register_routine_by_prescription(
        jwt_token: str = Query(description="Users JWT Token", required=True),
):
    return "처방전 촬영해주세요."


@router.get(
    "/pills-photo",
    operation_id="register_routine_by_pills_photo",
    description="사용자가 알약 촬영으로 복약 일정을 등록하고 싶을 때 사용하는 도구"
)
async def register_routine_by_pills_photo(
        jwt_token: str = Query(description="Users JWT Token", required=True),
):
    return "알약 사진을 업로드하거나 촬영해주세요."