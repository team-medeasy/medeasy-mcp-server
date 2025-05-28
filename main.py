import httpx
import os

from fastapi import FastAPI
from fastapi_mcp import FastApiMCP
from dotenv import load_dotenv
import logging
logging.basicConfig(level=logging.INFO)
from config.logging_config import setup_logging
from config.middleware_config import LoggingMiddleware
from router import api_router

logger = logging.getLogger(__name__)
load_dotenv()

app = FastAPI()
app.include_router(api_router)
setup_logging()
app.add_middleware(LoggingMiddleware)


# Add MCP server to the FastAPI app
mcp = FastApiMCP(
    app,
    name="medeasy fastapi mcp",
    description="convert fastapi to mcp server",
    describe_full_response_schema=True,  # Describe the full response JSON-schema instead of just a response example
    describe_all_responses=True,  # Describe all the possible responses instead of just the success (2XX) response
    http_client=httpx.AsyncClient(timeout=20, base_url="http://localhost:30003"),  # base_url 추가
    exclude_operations=["get_medicine_by_medicine_id"]
)

# mcp 서버 초기화 (새로 반영된 api도 추가)
mcp.setup_server()

# Mount the MCP server to the FastAPI app
mcp.mount()

if __name__ == "__main__":
    import uvicorn
    print("MCP 서버를 http://localhost:30003/mcp 에서 실행 중입니다.")
    print("매니페스트 URL: http://localhost:30003/mcp/manifest")

    uvicorn.run(app, host="0.0.0.0", port=30003)