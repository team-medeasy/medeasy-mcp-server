import httpx
import os
from fastapi import FastAPI, Query
from fastapi_mcp import FastApiMCP
from dotenv import load_dotenv
import logging
logging.basicConfig(level=logging.INFO)
from config.logging_config import setup_logging
from config.middleware_config import LoggingMiddleware

logger = logging.getLogger(__name__)
load_dotenv()

# mcp 서버의 엔드포인트는 기본적으로 /mcp로 접근 가능
# http://localhost:8000/mcp/manifest -> 매니페스트 정보 확인 가능

app = FastAPI()
setup_logging()
app.add_middleware(LoggingMiddleware)

@app.get("/medicine", operation_id="search_medicine")
async def search_medicine(
        jwt_token: str = Query(None, description="Users JWT Token"),
        medicine_name: str = Query(None, description="Medicine Name"),
        size: int= Query(1, description="result size")
):
    logger.info("search_medicine 도구 execute")
    # API 엔드포인트 설정
    api_url = "https://api.medeasy.dev/medicine/search"

    if not jwt_token:
        return {"error": "authorization token is required"}

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

@app.get("/weather/{city}", operation_id="get_weather")
async def getWeather(city: str):
    return {"result": f"{city} weather is very nice"}


@app.post("/medication/routine", operation_id="create_medicine_routine")
async def create_medicine_routine(
        medicine_id: str,
        nickname: str,
        dose: int,
        total_quantity: int,
        interval_days: int,
        user_schedule_ids: list[int] = None,
        jwt_token: str = None
):
    # API 엔드포인트 설정
    api_url = "https://api.medeasy.dev/routine"

    if not jwt_token:
        return {"error": "authorization token is required"}

    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Content-Type": "application/json"
    }

    # 요청 본문 설정
    request_body = {
        "medicine_id": medicine_id,
        "nickname": nickname,
        "dose": dose,
        "total_quantity": total_quantity,
        "interval_days": interval_days
    }

    # user_schedule_ids가 제공된 경우에만 추가
    if user_schedule_ids:
        request_body["user_schedule_ids"] = user_schedule_ids

    # 비동기 HTTP 클라이언트를 사용하여 API 요청 보내기
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(api_url, headers=headers, json=request_body)
            response.raise_for_status()  # 4XX, 5XX 에러 발생 시 예외 발생

            logger.info("mcp 서버 응답 성공")
            return response.json()  # API 응답을 JSON으로 변환하여 반환
        except httpx.HTTPStatusError as e:
            # HTTP 상태 코드 에러 처리
            return {"error": f"API 요청 실패: {e.response.status_code}", "detail": e.response.text}
        except httpx.RequestError as e:
            # 네트워크 관련 에러 처리 (타임아웃, 연결 오류 등)
            return {"error": f"API 요청 중 오류 발생: {str(e)}"}

# Add MCP server to the FastAPI app
mcp = FastApiMCP(
    app,
    name="medeasy fastapi mcp",
    description="convert fastapi to mcp server",
    describe_full_response_schema=True,  # Describe the full response JSON-schema instead of just a response example
    describe_all_responses=True,  # Describe all the possible responses instead of just the success (2XX) response
    http_client=httpx.AsyncClient(timeout=20, base_url="http://localhost:8000"),  # base_url 추가
)

# mcp 서버 초기화 (새로 반영된 api도 추가)
mcp.setup_server()

# Mount the MCP server to the FastAPI app
mcp.mount()

if __name__ == "__main__":
    import uvicorn
    print("MCP 서버를 http://localhost:8000/mcp 에서 실행 중입니다.")
    print("매니페스트 URL: http://localhost:8000/mcp/manifest")

    uvicorn.run(app, host="0.0.0.0", port=8000)