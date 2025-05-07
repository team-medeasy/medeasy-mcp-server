# 사용자 스케줄 조회 API 호출
import httpx
import os
from fastapi import HTTPException

from main import app
from routine.model import RoutineCreationRequest
from dotenv import load_dotenv

from service.medicine_service import search_medicine_id_by_name

load_dotenv()

# 응답 예시:
# {
#   "아침": "37",
#   "저녁": "38",
#   "자기전": "39"
# }
async def get_user_schedules()->dict[str, str]:
    api_url = "https://api.medeasy.dev/user/schedule"
    jwt_token = os.getenv("JWT_TOKEN")
    headers = {"Authorization": f"Bearer {jwt_token}"}

    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(api_url, headers=headers)
            response.raise_for_status()
            schedules = response.json().get("body", [])

            return {schedule["name"]: schedule["id"] for schedule in schedules}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"스케줄 조회 중 오류: {str(e)}")


# 약 복용 루틴 등록 엔드포인트
@app.post("/medication/register-routine", operation_id="register_medicine_routine")
async def register_medicine_routine(request: RoutineCreationRequest):
    # 1. 약 검색으로 medicine_id 획득
    medicine_id = await search_medicine_id_by_name(request.medicine_name)
    if not medicine_id:
        return {"error": "일치하는 약을 찾을 수 없습니다"}

    # 2. 사용자 스케줄 ID 획득 - 사용자 ID 파라미터 제거
    schedules = await get_user_schedules()

    # 사용자가 선택한 시간대에 맞는 schedule_id 찾기
    user_schedule_ids = []
    for time in request.schedule_times: # 아침 점심 저녁
        if time in schedules:
            user_schedule_ids.append(schedules[time])

    if not user_schedule_ids:
        return {"error": "선택한 시간대에 맞는 스케줄을 찾을 수 없습니다"}

    # 3. 루틴 등록 API 호출
    api_url = "https://api.medeasy.dev/routine"
    jwt_token = "eyJhbGciOiJIUzI1NiJ9.eyJ1c2VySWQiOjcsImV4cCI6MTc0NjI2NzE2MH0.rZJKEOJ_yTLH-mXxJmSjNFUnZBrJywmhLDSW4P3Na0A"
    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Content-Type": "application/json"
    }

    request_body = {
        "medicine_id": medicine_id,
        "nickname": request.nickname,
        "dose": request.dose,
        "total_quantity": request.total_quantity,
        "interval_days": request.interval_days,
        "user_schedule_ids": user_schedule_ids
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(api_url, headers=headers, json=request_body)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            return {"error": f"API 요청 실패: {e.response.status_code}", "detail": e.response.text}
        except httpx.RequestError as e:
            return {"error": f"API 요청 중 오류 발생: {str(e)}"}