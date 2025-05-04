# 입력 모델 정의
from typing import List

from pydantic import BaseModel


class MedicineSearchRequest(BaseModel):
    medicine_name: str

class UserScheduleRequest(BaseModel):
    user_id: str  # 사용자 ID

class RoutineCreationRequest(BaseModel):
    medicine_name: str  # 약 이름
    nickname: str       # 약 별명
    dose: int           # 복용량
    total_quantity: int # 총 수량
    interval_days: int  # 복용 간격(일)
    schedule_times: List[str]  # 사용자가 선택한 시간대 (예: "아침", "점심", "저녁")