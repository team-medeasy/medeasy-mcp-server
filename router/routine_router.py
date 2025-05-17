import logging
import os
from datetime import date, datetime, timedelta

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
    params = {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat()
    }
    headers = {"Authorization": f"Bearer {jwt_token}", "Content-Type": "application/json"}

    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=headers, params=params)
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=f"조회 실패: {resp.text}")


    now = datetime.now(kst).time()
    lines = []
    lines.append("오늘 복약 일정에 대해 알려드릴게요!")

    data = resp.json()["body"]
    soon_delta = timedelta(minutes=30)
    now_dt = datetime.combine(datetime.today(), now)

    for day in data:  # 날짜 단위 루틴 (보통 하루 단위로 1개만 들어있음)
        routine_date = datetime.strptime(day["take_date"], "%Y-%m-%d").date()

        for schedule in day.get("user_schedule_dtos", []):
            take_time_str = schedule.get("take_time")
            if not take_time_str:
                continue  # take_time 없으면 skip

            try:
                time_obj = datetime.strptime(take_time_str, "%H:%M:%S").time()
            except ValueError:
                continue  # 포맷 이상할 경우 skip

            routine_date_time = datetime.combine(routine_date, time_obj)

            # (1) 전체 스케줄 요약
            medicines = ", ".join( # ex) 오라록신정100mg(오플록사신) 1정, 씬지록신정100마이크로그램(레보티록신나트륨수화물) 1정
                f"{routine.get('nickname', '')} {routine.get('dose', '')}정"
                for routine in schedule.get("routine_dtos", [])
            )
            lines.append(f"- {schedule.get('name', '')} {time_obj.strftime('%H:%M')} : {medicines}")

            # (2) 미복용 알림 (스케줄 시간 지남 + 안 먹음)
            if now > time_obj:
                not_taken = [
                    r for r in schedule.get("routine_dtos", [])
                    if not r.get("is_taken", False)
                ]
                if not_taken:
                    meds = ", ".join(r.get("nickname", "") for r in not_taken)
                    lines.append(f"아직 {schedule.get('name', '')}에 {meds}을(를) 복용하지 않으셨습니다.")

            # (3) 곧 복용 예정 안내
            schedule_dt = datetime.combine(datetime.today(), time_obj)
            if now_dt < schedule_dt <= now_dt + soon_delta:
                lines.append(f"잠시 후 {schedule.get('name', '')} 복용 시간이 다가옵니다. 준비해 주세요!")

    return {"message": "\n".join(lines)}

@router.patch(
    "/check",
    operation_id="drug_routine_completed_check",
    description="사용자가 복약을 수행하고 복약 일정을 체크하고 싶을 때 사용하는 도구"
)
async def drug_routine_completed_check(
        jwt_token: str = Query(description="Users JWT Token", required=True),
        medicine_name: str = Query(description="check routine medicine name or nickname", required=True),
        schedule_name: str = Query(description="Schedule name for when the user takes medicine", required=True, example=["아침", "점심", "저녁", "자기 전"])
):
    logger.info(f"복약 체크 도구 호출, medicine_name : {medicine_name}, schedule_name : {schedule_name}")
    url = f"{medeasy_api_url}/routine/check/medicine_name"

    # "약"이 붙은 경우를 처리하는 로직 추가 -> 아침약 체크해줘에서 스케줄 이름이 아침이 아닌 아침약으로 입력되는 문제 수정
    clean_schedule_name = schedule_name.replace("약", "") if "약" in schedule_name else schedule_name

    # user_schedules 조회
    schedules = await get_user_schedule(jwt_token)
    matching_schedule = next(
        (schedule for schedule in schedules if schedule["name"] == clean_schedule_name),
        None
    )

    if not matching_schedule:
        return "복용 체크 하려는 사용자의 스케줄 시간대가 존재하지 않습니다."

    params = {
        "medicine_name": medicine_name,
        "schedule_id": matching_schedule["user_schedule_id"],
    }

    headers = {"Authorization": f"Bearer {jwt_token}", "Content-Type": "application/json"}

    async with httpx.AsyncClient() as client:
        resp = await client.patch(url, headers=headers, params=params)
        if resp.status_code >= 400:
            raise HTTPException(status_code=resp.status_code, detail=f"조회 실패: {resp.text}")
        return resp.json()


@router.patch(
    "/all/check",
    operation_id="drug_schedule_all_routines_completed_check",
    description="사용자가 정해진 스케줄에 있는 약을 전부 복용하고 한번에 복약 여부들을 체크하고 싶을 때 사용하는 도구"
)
async def drug_schedule_all_routines_completed_check(
        jwt_token: str = Query(description="Users JWT Token", required=True),
        is_all_drugs_taken: bool = Query(description="사용자가 진짜 약을 다먹었는지 여부", required=True),
        schedule_name: str = Query(description="Schedule name for when the user takes medicine", required=True, example=["아침", "점심", "저녁", "자기 전"])
):
    logger.info("스케줄에 해당하는 복약 전부 체크 도구 호출")
    url = f"{medeasy_api_url}/routine/check/schedule"

    if not is_all_drugs_taken:
        return "사용자의 복용 여부를 다시 한번 확인해주세요."

    # "약"이 붙은 경우를 처리하는 로직 추가
    clean_schedule_name = schedule_name.replace("약", "") if "약" in schedule_name else schedule_name

    # user_schedules 조회
    schedules = await get_user_schedule(jwt_token)
    matching_schedule = next(
        (schedule for schedule in schedules if schedule["name"] == clean_schedule_name),
        None
    )

    if not matching_schedule:
        return "복용 체크 하려는 사용자의 스케줄 시간대가 존재하지 않습니다."

    params = {
        "schedule_id": matching_schedule["user_schedule_id"],
    }

    headers = {"Authorization": f"Bearer {jwt_token}", "Content-Type": "application/json"}

    async with httpx.AsyncClient() as client:
        resp = await client.patch(url, headers=headers, params=params)
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