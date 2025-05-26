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

# @router.post(
#     path="/register",
#     operation_id="create_new_medicine_routine",
#     description="새로운 복약 일정을 등록할 때 사용하는 도구"
# )
# async def create_medicine_routine(
#         medicine_id: str = Query(description="medicine identifier code number", example='1', required=True),
#         nickname: str = Query(default=None, description="medicine nickname", required=False),
#         dose: int = Query(default=1, description="dose", ge=1, le=10, required=False),
#         total_quantity: int = Query(description="medicine's total quantity", ge=1, le=200, required=True),
#         interval_days: int = Query(default=1, description="medicine's interval days", ge=1, le=30, required=False),
#         user_schedule_names: list[str] = Query(description="Schedule names for when the user takes medicine", required=True),
#         jwt_token: str = Query(description="Users JWT Token", required=True),
# ):
#     # medicine_id=await search_medicine_id_by_name(jwt_token, medicine_name)
#
#     # medicine_id 검색
#     if medicine_id is None:
#         raise HTTPException(status_code=400, detail=f"존재하지 않는 약입니다.")
#
#     # user_schedules 조회
#     schedules = await get_user_schedule(jwt_token)
#
#     # OpenAI로 입력받은 user_schedule_names와 어울리는 user_schedule_id 추출
#     matched_ids=await mapping_user_schedule_ids(schedules, user_schedule_names)
#
#     if not matched_ids:
#         return {"복약 일정을 등록하실 시간대가 없습니다. 먼저 시간대를 설정해주세요."}
#
#     # 루틴 생성 API 호출
#     routine_url = f"{medeasy_api_url}/routine"
#     body = {
#         "medicine_id": medicine_id,
#         "nickname": nickname,
#         "dose": dose,
#         "total_quantity": total_quantity,
#         "interval_days": interval_days,
#         "user_schedule_ids": matched_ids,
#     }
#
#     headers = {"Authorization": f"Bearer {jwt_token}", "Content-Type": "application/json"}
#
#     async with httpx.AsyncClient() as client:
#         resp = await client.post(routine_url, headers=headers, json=body)
#         if resp.status_code >= 400:
#             raise HTTPException(status_code=502, detail=f"루틴 생성 실패: {resp.text}")
#         return resp.json()

@router.get("", operation_id="get_medicine_routine_list_by_date_detailed")  # operation_id 변경 고려
async def get_medicine_routine_list_by_date(
        jwt_token: str = Query(description="사용자 JWT 토큰", required=True),
        start_date: date = Query(default=datetime.now(kst).date(), description="조회 시작 날짜 (기본값: 오늘)"),
        end_date: date = Query(default=datetime.now(kst).date(), description="조회 종료 날짜 (기본값: 오늘)")
):
    url = f"{medeasy_api_url}/routine"
    logger.info(f"사용자 복약 일정 상세 조회 시작: {start_date} ~ {end_date}")
    params = {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat()
    }
    headers = {"Authorization": f"Bearer {jwt_token}", "Content-Type": "application/json"}

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers=headers, params=params)

        if resp.status_code >= 400:
            try:
                error_detail = resp.json().get("detail", resp.text)
            except Exception:
                error_detail = resp.text if resp.text else f"오류 코드 {resp.status_code}"
            logger.error(f"외부 API 오류 응답 (상태 코드: {resp.status_code}): {error_detail}")
            raise HTTPException(status_code=resp.status_code, detail=f"복약 일정 조회 실패: {error_detail}")

        response_data = resp.json()
        if "body" not in response_data:
            logger.error(f"외부 API 응답에 'body' 필드가 없습니다: {response_data}")
            raise HTTPException(status_code=500, detail="외부 API 응답 형식 오류: 'body' 필드 누락")

        api_data_body = response_data["body"]  # 변수명 변경 data -> api_data_body
        if not isinstance(api_data_body, list):
            logger.error(f"외부 API 응답의 'body' 필드가 리스트가 아닙니다: {api_data_body}")
            raise HTTPException(status_code=500, detail="외부 API 응답 형식 오류: 'body'가 리스트가 아님")

    except httpx.RequestError as e:
        logger.error(f"외부 API 호출 중 네트워크 오류 발생: {e}")
        raise HTTPException(status_code=503, detail=f"외부 서비스 호출 중 오류가 발생했습니다: {e}")
    except Exception as e:
        logger.error(f"복약 일정 조회 중 예기치 않은 오류 발생: {e}")
        if isinstance(e, HTTPException):
            raise
        raise HTTPException(status_code=500, detail=f"서버 내부 오류가 발생했습니다: {e}")

    now_time = datetime.now(kst).time()
    lines_for_message = []  # AI 메시지용 라인
    schedule_details_list = []  # 구조화된 상세 정보 리스트

    soon_delta = timedelta(minutes=30)
    today_for_comparison = datetime.now(kst).date()
    now_dt = datetime.combine(today_for_comparison, now_time)

    for day_data in api_data_body:
        if not isinstance(day_data, dict) or "take_date" not in day_data:
            logger.warning(f"처리할 수 없는 형식의 일일 데이터입니다: {day_data}, 해당 데이터를 건너뜁니다.")
            continue

        try:
            routine_date = datetime.strptime(day_data["take_date"], "%Y-%m-%d").date()
        except ValueError:
            logger.warning(f"날짜 형식이 잘못되었습니다: {day_data.get('take_date')}, 해당 날짜 데이터를 건너뜁니다.")
            continue

        for schedule in day_data.get("user_schedule_dtos", []):
            if not isinstance(schedule, dict):
                logger.warning(f"처리할 수 없는 형식의 스케줄 데이터입니다: {schedule}, 해당 스케줄을 건너뜁니다.")
                continue

            take_time_str = schedule.get("take_time")
            if not take_time_str:
                logger.debug(f"스케줄 ID {schedule.get('user_schedule_id')}에 복용 시간(take_time) 정보가 없어 건너뜁니다.")
                continue

            try:
                time_obj = datetime.strptime(take_time_str, "%H:%M:%S").time()
            except ValueError:
                logger.warning(
                    f"스케줄 ID {schedule.get('user_schedule_id')}의 복용 시간(take_time: {take_time_str}) 형식이 잘못되어 건너뜁니다.")
                continue

            routine_date_time = datetime.combine(routine_date, time_obj)

            # --- 구조화된 데이터(`schedule_details_list`) 생성 ---
            current_schedule_medicines_details = []
            routine_dtos_data = schedule.get("routine_dtos", [])
            for routine in routine_dtos_data:
                if isinstance(routine, dict):
                    current_schedule_medicines_details.append({
                        "routine_id": routine.get("routine_id"),
                        "medicine_id": routine.get("medicine_id"),
                        "medicine_name": routine.get("nickname", "알 수 없는 약"),
                        "dose": routine.get("dose"),
                        "is_taken": routine.get("is_taken", False)
                    })

            schedule_info_entry = {
                "date": routine_date.isoformat(),
                "time": take_time_str,
                "schedule_name": schedule.get("name", "알 수 없는 시간대"),
                "user_schedule_id": schedule.get("user_schedule_id"),
                "medicines": current_schedule_medicines_details
            }
            schedule_details_list.append(schedule_info_entry)
            # --- 구조화된 데이터 생성 끝 ---

            # --- AI 메시지(`lines_for_message`) 생성 ---
            # (1) 전체 스케줄 요약
            if not routine_dtos_data:
                medicines_summary_str = "등록된 약 정보 없음"
            else:
                medicines_summary_str = ", ".join(
                    f"{routine.get('nickname', '알 수 없는 약')} {routine.get('dose', '') if routine.get('dose') is not None else ''}정"
                    for routine in routine_dtos_data if isinstance(routine, dict)
                )
            lines_for_message.append(
                f"- {schedule.get('name', '알 수 없는 시간대')} {time_obj.strftime('%H:%M')} : {medicines_summary_str}")

            # (2) 미복용 알림 (스케줄 시간 지남 + 안 먹음 + 오늘 또는 과거 스케줄)
            if routine_date <= today_for_comparison and now_dt > routine_date_time:
                not_taken_medicines = [
                    r for r in routine_dtos_data
                    if isinstance(r, dict) and not r.get("is_taken", False)
                ]
                if not_taken_medicines:
                    meds_not_taken_str = ", ".join(r.get("nickname", "알 수 없는 약") for r in not_taken_medicines)
                    lines_for_message.append(
                        f"아직 {schedule.get('name', '')} ({time_obj.strftime('%H:%M')})에 {meds_not_taken_str}을(를) 복용하지 않으셨습니다.")

            # (3) 곧 복용 예정 안내 (오늘 스케줄 + 현재 시간 이후 30분 이내)
            if routine_date == today_for_comparison:
                schedule_dt_for_soon_check = routine_date_time
                if now_dt < schedule_dt_for_soon_check <= now_dt + soon_delta:
                    lines_for_message.append(
                        f"잠시 후 {time_obj.strftime('%H시 %M분')}에 {schedule.get('name', '')} 복용 시간이 다가옵니다. 꼭 복용해 주세요!")
            # --- AI 메시지 생성 끝 ---

    final_message_str = ""
    if not lines_for_message:  # 생성된 AI 메시지 라인이 없을 경우 (즉, 처리할 스케줄이 없었음)
        current_today_date = datetime.now(kst).date()
        if start_date == end_date:
            if start_date == current_today_date:
                final_message_str = "오늘 등록된 복약 일정이 없습니다."
            else:
                final_message_str = f"{start_date.year}년 {start_date.month}월 {start_date.day}일에 등록된 복약 일정이 없습니다."
        else:
            final_message_str = f"{start_date.year}년 {start_date.month}월 {start_date.day}일부터 {end_date.year}년 {end_date.month}월 {end_date.day}일까지 등록된 복약 일정이 없습니다."
        # schedule_details_list는 이 경우 이미 비어있을 것이므로 별도 처리 필요 없음
    else:
        final_message_str = "\n".join(lines_for_message)

    return {"message": final_message_str, "schedule_details": schedule_details_list}


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

@router.get(
    "/basic-routine-register",
    operation_id="router_routine_register_node",
    description="사용자가 특수 복용 일정 등록방식이 아닌 일반적으로 복용 일정 등록을 원할 때 사용하는 도구"
)
async def register_routine_by_pills_photo(
        jwt_token: str = Query(description="Users JWT Token", required=True),
):
    return "복용 일정을 등록하기 위해 복약 정보를 알려주세요."