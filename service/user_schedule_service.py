import json
from logging import exception
from typing import List, Dict, Any

import httpx
import os
from fastapi import HTTPException
from dotenv import load_dotenv
import logging

from langchain_core.messages import SystemMessage, HumanMessage
from langchain_openai import ChatOpenAI

logger=logging.getLogger(__name__)
load_dotenv()
medeasy_api_url = os.getenv("MEDEASY_API_URL")

if not medeasy_api_url:
    logger.error("medeasy api url not set")

llm = ChatOpenAI(model_name="gpt-4o-mini", temperature=0)

"""
사용자 스케줄 리스트 목록 반환 
"""
async def get_user_schedule(jwt_token: str) -> List[Dict[str, Any]]:
    schedule_url = f"{medeasy_api_url}/user/schedule"
    headers = {"Authorization": f"Bearer {jwt_token}"}

    async with httpx.AsyncClient() as client:
        resp = await client.get(schedule_url, headers=headers)
        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail=f"스케줄 조회 실패: {resp.text}")
        schedules = resp.json().get("body", [])
        logger.info(f"schedules: {schedules}")

        return schedules

async def mapping_user_schedule_ids(schedules: List[Dict[str, Any]], user_schedule_names: List[str]):
    prompt = f"""
        Available schedules:
        {json.dumps(schedules, ensure_ascii=False, indent=2)}

        Requested names: {user_schedule_names}

        Return a JSON array of integers: the user_schedule_id values whose 'name' best match the requested names.
        """
    messages = [
        SystemMessage(
            content="Match user-requested schedule names to available schedules. Return ONLY the JSON array, without any markdown code fences."),
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

    return matched_ids