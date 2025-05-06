import json
import logging
import os

import httpx
from fastapi import APIRouter, FastAPI, Query, HTTPException
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
from openai import base_url

load_dotenv()
logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/routine",
    tags=["Routine Router"]
)

llm = ChatOpenAI(model_name="gpt-4o-mini", temperature=0)

@router.post("/register", operation_id="create_medicine_routine")
async def create_medicine_routine(
        medicine_id: str = Query(description="medicine identifier", required=True),
        nickname: str = Query(default=None, description="medicine nickname", required=False),
        dose: int = Query(default=1, description="dose", ge=1, le=10, required=False),
        total_quantity: int = Query(description="medicine's total quantity", ge=1, le=200, required=True),
        interval_days: int = Query(default=1, description="medicine's interval days", ge=1, le=30, required=False),
        user_schedule_names: list[str] = Query(description="Schedule names for when the user takes medicine", required=True),
        jwt_token: str = Query(description="Users JWT Token", required=True),
):
    medeasy_api_url = os.getenv("MEDEASY_API_URL")
    logging.info(f"user_schedule_names: {user_schedule_names}")
    # 1) 사용자 스케줄 목록 조회
    schedule_url = f"{medeasy_api_url}/user/schedule"
    headers = {"Authorization": f"Bearer {jwt_token}"}
    async with httpx.AsyncClient() as client:
        resp = await client.get(schedule_url, headers=headers)
        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail=f"스케줄 조회 실패: {resp.text}")
        schedules = resp.json().get("body", [])
        logger.info(f"schedules: {schedules}")

    # 2) OpenAI로 이름 매칭 수행
    prompt = f"""
    Available schedules:
    {json.dumps(schedules, ensure_ascii=False, indent=2)}

    Requested names: {user_schedule_names}

    Return a JSON array of integers: the user_schedule_id values whose 'name' best match the requested names.
    """
    messages = [
        SystemMessage(content="Match user-requested schedule names to available schedules. Return ONLY the JSON array, without any markdown code fences."),
        HumanMessage(content=prompt)
    ]
    # agenerate 는 메시지 리스트를 리스트로 감싸서 전달
    chat_result = await llm.agenerate([messages])
    logger.info(f"chat_result: {chat_result}")
    matched_text = chat_result.generations[0][0].message.content
    try:
        matched_ids = json.loads(matched_text)
    except Exception:
        # 파싱 실패시 빈 리스트 처리
        matched_ids = []

    logger.info(f"matched_ids: {matched_ids}")

    # 3) 루틴 생성 API 호출
    routine_url = f"{medeasy_api_url}/routine"
    body = {
        "medicine_id": medicine_id,
        "nickname": nickname,
        "dose": dose,
        "total_quantity": total_quantity,
        "interval_days": interval_days,
        "user_schedule_ids": matched_ids,
    }
    headers["Content-Type"] = "application/json"

    async with httpx.AsyncClient() as client:
        resp = await client.post(routine_url, headers=headers, json=body)
        if resp.status_code >= 400:
            raise HTTPException(status_code=502, detail=f"루틴 생성 실패: {resp.text}")
        return resp.json()