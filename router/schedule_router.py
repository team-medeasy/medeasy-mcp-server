import logging
import os
from datetime import date, datetime, time

import httpx
import pytz
from fastapi import APIRouter, FastAPI, Query, HTTPException
from dotenv import load_dotenv
from service.user_schedule_service import get_user_schedule, mapping_user_schedule_ids

load_dotenv()
logger = logging.getLogger(__name__)

# 한국 시간대 객체 생성 - 전역 범위에 정의
kst = pytz.timezone('Asia/Seoul')
medeasy_api_url = os.getenv("MEDEASY_API_URL")

router = APIRouter(
    prefix="/user",
    tags=["User Router"]
)

@router.patch(
    path="/schedule",
    operation_id="modify_medicine_routine_schedule_time",
    description="사용자의 복용 일정 시간 변경"
)
async def modify_schedule_time(
        jwt_token: str = Query(description="Users JWT Token", required=True),
        user_schedule_name: str = Query(description="Schedule name for when the user takes medicine", required=True),
        take_time: time = Query(default=datetime.now(kst).time(), required=True, description="Time to take"),
):
    # user_schedules 조회
    schedules = await get_user_schedule(jwt_token)

    # OpenAI로 입력받은 user_schedule_names와 어울리는 user_schedule_id 추출
    matched_ids=await mapping_user_schedule_ids(schedules, [user_schedule_name])

    if not matched_ids:
        return {"message": f"'{user_schedule_name}'에 해당하는 스케줄이 없습니다."}

    # 요청 전송
    user_schedule_url = f"{medeasy_api_url}/user/schedule/update"

    headers = {"Authorization": f"Bearer {jwt_token}", "Content-Type": "application/json"}
    body = {
        "user_schedule_id": matched_ids[0],
        "take_time": take_time.strftime("%H:%M:%S")
    }

    async with httpx.AsyncClient() as client:
        resp = await client.patch(user_schedule_url, headers=headers, json=body)
        if resp.status_code >= 400:
            raise HTTPException(status_code=resp.status_code, detail=f"복약 시간 변경 실패: {resp.text}")
        return resp.json()