import json
import logging
import os
from datetime import date, datetime, timedelta

import httpx
import pytz
from fastapi import APIRouter, FastAPI, Query, HTTPException
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

from service.medicine_service import search_medicine_id_by_name
from service.user_schedule_service import get_user_schedule, mapping_user_schedule_ids

load_dotenv()
logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/routine",
    tags=["Routine Router"]
)

medeasy_api_url = os.getenv("MEDEASY_API_URL")
gpt_mini = ChatOpenAI(model_name="gpt-4.1-mini")
gpt_nano = ChatOpenAI(model_name="gpt-4.1-nano")

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
        schedule_name: str = Query(description="Schedule name for when the user takes medicine", required=True,
                                   example=["아침", "점심", "저녁", "자기 전"])
):
    logger.info(f"복약 체크 도구 호출, medicine_name : {medicine_name}, schedule_name : {schedule_name}")

    # 1. 오늘 루틴 데이터 조회
    today = date.today()
    routine_data = await get_routine_list(today, today, jwt_token)

    # routine_data가 리스트인지 딕셔너리인지 확인하고 처리
    if isinstance(routine_data, list):
        # 리스트인 경우 (API가 직접 리스트를 반환하는 경우)
        if not routine_data:
            return {"message": "오늘 복용 일정이 없습니다."}
        today_data = routine_data[0]
    else:
        # 딕셔너리인 경우 (기존 로직)
        if not routine_data.get("data") or not routine_data["data"]:
            return {"message": "오늘 복용 일정이 없습니다."}
        today_data = routine_data["data"][0]

    schedules = today_data.get("user_schedule_dtos", [])

    # 2. GPT mini를 활용한 매칭
    matching_prompt = f"""
다음은 사용자의 오늘 복약 일정 데이터입니다:
{json.dumps(schedules, ensure_ascii=False, indent=2)}

사용자가 체크하려는 정보:
- 약물명: {medicine_name}
- 시간대: {schedule_name}

다음 작업을 수행해주세요:
1. schedule_name과 가장 유사한 "name" 필드를 찾기 (예: "아침약" -> "아침")
2. 해당 시간대에서 medicine_name과 가장 유사한 "nickname" 필드를 찾기
3. 매칭 결과를 JSON 형태로 반환

응답 형식:
{{
    "found": true/false,
    "schedule_name": "매칭된 스케줄 이름",
    "routine_id": 매칭된 routine_id,
    "nickname": "매칭된 약물 이름",
    "is_taken": true/false,
    "analysis_reason": "매칭 근거와 분석 과정 설명",
    "message": "결과 메시지"
}}

매칭 규칙:
- 완전히 일치하지 않아도 유사한 것으로 판단
- "약" 글자는 무시 (아침약 = 아침)
- 약물명은 nickname에서 주요 성분명이나 상품명으로 매칭
- 매칭되지 않으면 found: false로 설정
- analysis_reason에는 왜 이 매칭을 선택했는지 상세한 근거를 포함
"""

    messages = [
        {"role": "system", "content": "당신은 약물 이름과 복용 시간을 정확히 매칭하는 전문가입니다. 사용자의 입력을 분석하여 가장 적합한 매칭을 찾아주세요."},
        {"role": "user", "content": matching_prompt}
    ]

    try:
        response = await gpt_mini.ainvoke(messages)
        matching_result = json.loads(response.content.strip())
    except (json.JSONDecodeError, Exception) as e:
        logger.error(f"GPT 응답 파싱 오류: {e}")
        return {"message": "약물 매칭 중 오류가 발생했습니다."}

    # 3. 매칭 결과 처리
    if not matching_result.get("found", False):
        return {"message": f"'{medicine_name}' 약물이 '{schedule_name}' 시간대에서 찾을 수 없습니다. 복용 일정을 다시 확인해주세요."}

    routine_id = matching_result.get("routine_id")
    is_already_taken = matching_result.get("is_taken", False)
    nickname = matching_result.get("nickname", "")
    analysis_reason = matching_result.get("analysis_reason", "")

    # 로깅용으로 분석 이유 기록
    logger.info(f"GPT 매칭 분석: {analysis_reason}")

    # 4. 이미 복용한 경우 체크
    if is_already_taken:
        return {
            "message": f"'{nickname}'는 이미 복용하신 약입니다.",
            "analysis_reason": analysis_reason
        }

    # 5. 복용 체크 API 호출
    check_url = f"{medeasy_api_url}/routine/check"
    headers = {"Authorization": f"Bearer {jwt_token}", "Content-Type": "application/json"}

    params = {
        "routine_id": routine_id,
        "is_taken": True
    }

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.patch(check_url, headers=headers, params=params)
            if resp.status_code >= 400:
                logger.error(f"복용 체크 API 오류: {resp.text}")
                return {"message": "복용 체크 중 오류가 발생했습니다."}

            # 성공 응답
            return {
                "message": f"'{nickname}' 복용이 완료되었습니다. 건강 관리 잘하고 계시네요! 👍",
                "routine_id": routine_id,
                "schedule_name": matching_result.get("schedule_name"),
                "medicine_name": nickname,
                "analysis_reason": analysis_reason
            }

        except Exception as e:
            logger.error(f"복용 체크 요청 오류: {e}")
            return {"message": "복용 체크 중 네트워크 오류가 발생했습니다."}


# 보조 함수: 루틴 데이터 조회
async def get_routine_list(start_date: date, end_date: date, jwt_token: str):
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

        # API 응답 구조 확인 및 적절히 처리
        response_data = resp.json()
        if "body" in response_data:
            return response_data["body"]  # body 필드가 있으면 그것을 반환
        else:
            return response_data  # 없으면 전체 데이터 반환


@router.patch(
    "/all/check",
    operation_id="drug_schedule_all_routines_completed_check",
    description="사용자가 정해진 스케줄에 있는 약을 전부 복용하고 한번에 복약 여부들을 체크하고 싶을 때 사용하는 도구"
)
async def drug_schedule_all_routines_completed_check(
        jwt_token: str = Query(description="Users JWT Token", required=True),
        is_all_drugs_taken: bool = Query(description="사용자가 진짜 약을 다먹었는지 여부", required=True),
        schedule_name: str = Query(description="Schedule name for when the user takes medicine", required=True,
                                   example=["아침", "점심", "저녁", "자기 전"])
):
    logger.info(f"스케줄 전체 복약 체크 도구 호출 - schedule_name: {schedule_name}, is_all_drugs_taken: {is_all_drugs_taken}")

    if not is_all_drugs_taken:
        return {"message": "복용을 완료하신 후 다시 체크해주세요. 정확한 복약 관리가 중요합니다."}

    # 1. 사용자 스케줄 데이터 조회
    try:
        schedules = await get_user_schedule(jwt_token)
    except Exception as e:
        logger.error(f"스케줄 조회 오류: {e}")
        return {"message": "스케줄 정보를 가져오는 중 오류가 발생했습니다."}

    # 2. GPT mini를 활용한 스마트 스케줄 매칭
    matching_prompt = f"""
다음은 사용자의 복약 스케줄 목록입니다:
{json.dumps(schedules, ensure_ascii=False, indent=2)}

사용자가 입력한 스케줄명: "{schedule_name}"

다음 작업을 수행해주세요:
1. 입력한 스케줄명과 가장 유사한 스케줄을 찾기
2. "약" 글자는 무시하고 매칭 (예: "아침약" -> "아침")
3. 유사성 판단 (완전 일치가 아니어도 의미상 같으면 매칭)

응답 형식:
{{
    "found": true/false,
    "schedule_id": 매칭된_user_schedule_id,
    "schedule_name": "매칭된 스케줄 이름",
    "take_time": "복용 시간",
    "analysis_reason": "매칭 근거 설명"
}}

매칭되지 않으면 found: false로 설정해주세요.
"""

    messages = [
        {"role": "system", "content": "당신은 사용자의 복약 스케줄을 정확히 매칭하는 전문가입니다. 입력된 스케줄명을 분석하여 가장 적합한 스케줄을 찾아주세요."},
        {"role": "user", "content": matching_prompt}
    ]

    try:
        response = await gpt_mini.ainvoke(messages)
        matching_result = json.loads(response.content.strip())
    except (json.JSONDecodeError, Exception) as e:
        logger.error(f"GPT 스케줄 매칭 오류: {e}")
        # Fallback: 기존 로직 사용
        clean_schedule_name = schedule_name.replace("약", "") if "약" in schedule_name else schedule_name
        matching_schedule = next(
            (schedule for schedule in schedules if schedule["name"] == clean_schedule_name),
            None
        )

        if not matching_schedule:
            return {"message": f"'{schedule_name}' 시간대를 찾을 수 없습니다. 등록된 스케줄을 확인해주세요."}

        matching_result = {
            "found": True,
            "schedule_id": matching_schedule["user_schedule_id"],
            "schedule_name": matching_schedule["name"],
            "take_time": matching_schedule["take_time"],
            "analysis_reason": "기본 매칭 로직 사용"
        }

    # 3. 매칭 결과 확인
    if not matching_result.get("found", False):
        available_schedules = [s["name"] for s in schedules]
        return {
            "message": f"'{schedule_name}' 시간대를 찾을 수 없습니다. 등록된 스케줄: {', '.join(available_schedules)}",
            "analysis_reason": matching_result.get("analysis_reason", "")
        }

    schedule_id = matching_result.get("schedule_id")
    matched_schedule_name = matching_result.get("schedule_name")
    analysis_reason = matching_result.get("analysis_reason", "")

    logger.info(f"스케줄 매칭 완료 - {analysis_reason}")

    # 4. 해당 스케줄의 현재 복용 상태 확인 (선택사항)
    today = date.today()
    try:
        routine_data = await get_routine_list(today, today, jwt_token)
        current_status = get_schedule_status(routine_data, matched_schedule_name)
        if current_status and current_status.get("all_taken"):
            return {
                "message": f"'{matched_schedule_name}' 시간대의 모든 약이 이미 복용 완료되었습니다.",
                "schedule_name": matched_schedule_name,
                "analysis_reason": analysis_reason
            }
    except Exception as e:
        logger.warning(f"현재 상태 확인 중 오류 (계속 진행): {e}")

    # 5. 전체 복용 완료 API 호출
    url = f"{medeasy_api_url}/routine/check/schedule"
    params = {
        "schedule_id": schedule_id,
        "start_date": today.isoformat(),
        "end_date": today.isoformat()
    }
    headers = {"Authorization": f"Bearer {jwt_token}", "Content-Type": "application/json"}

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.patch(url, headers=headers, params=params)
            if resp.status_code >= 400:
                logger.error(f"스케줄 전체 체크 API 오류: {resp.text}")
                return {"message": "복용 체크 중 오류가 발생했습니다. 잠시 후 다시 시도해주세요."}

            # 성공 응답
            response_data = resp.json()
            return {
                "message": f"'{matched_schedule_name}' 시간대의 모든 약 복용이 완료되었습니다! 꾸준한 복약 관리 정말 잘하고 계시네요! 🎉",
                "schedule_id": schedule_id,
                "schedule_name": matched_schedule_name,
                "take_time": matching_result.get("take_time"),
                "analysis_reason": analysis_reason,
                "api_response": response_data
            }

        except Exception as e:
            logger.error(f"스케줄 전체 체크 요청 오류: {e}")
            return {"message": "복용 체크 중 네트워크 오류가 발생했습니다."}


# 보조 함수들
async def get_user_schedule(jwt_token: str):
    """사용자 스케줄 조회"""
    url = f"{medeasy_api_url}/user/schedule"
    headers = {"Authorization": f"Bearer {jwt_token}", "Content-Type": "application/json"}

    async with httpx.AsyncClient() as client:
        resp = await client.get(url, headers=headers)
        if resp.status_code >= 400:
            raise HTTPException(status_code=resp.status_code, detail=f"스케줄 조회 실패: {resp.text}")

        response_data = resp.json()
        if "body" in response_data:
            return response_data["body"]
        else:
            return response_data


async def get_routine_list(start_date: date, end_date: date, jwt_token: str):
    """루틴 리스트 조회"""
    url = f"{medeasy_api_url}/routine"
    params = {
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "jwt_token": jwt_token  # JWT 토큰도 파라미터로 전달하는 경우
    }
    headers = {"Authorization": f"Bearer {jwt_token}", "Content-Type": "application/json"}

    async with httpx.AsyncClient() as client:
        # GET 요청에서는 params를 사용하여 query parameter로 전달
        resp = await client.get(url, headers=headers, params=params)
        if resp.status_code >= 400:
            logger.error(f"루틴 조회 API 오류 - Status: {resp.status_code}, Response: {resp.text}")
            raise HTTPException(status_code=resp.status_code, detail=f"루틴 조회 실패: {resp.text}")

        response_data = resp.json()
        logger.info(f"루틴 조회 성공 - Response: {response_data}")

        if "body" in response_data:
            return response_data["body"]
        else:
            return response_data


def get_schedule_status(routine_data, schedule_name):
    """특정 스케줄의 현재 복용 상태 확인"""
    try:
        if isinstance(routine_data, list) and routine_data:
            today_data = routine_data[0]
            schedules = today_data.get("user_schedule_dtos", [])

            for schedule in schedules:
                if schedule.get("name") == schedule_name:
                    routines = schedule.get("routine_dtos", [])
                    all_taken = all(routine.get("is_taken", False) for routine in routines)
                    return {
                        "all_taken": all_taken,
                        "total_count": len(routines),
                        "taken_count": sum(1 for r in routines if r.get("is_taken", False))
                    }
        return None
    except Exception:
        return None



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

@router.delete(
    path="/delete/routine",
    operation_id="delete_medication_routine",
    description="사용자가 복약 일정 삭제를 원할 때 사용하는 도구"
)
async def delete_routine():
    return "삭제 하실 복약 일정을 말씀해주세요."