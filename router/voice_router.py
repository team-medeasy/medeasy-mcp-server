import logging
import os
from datetime import date, datetime, time
from typing import Optional

import httpx
import pytz
from fastapi import APIRouter, FastAPI, Query, HTTPException
from dotenv import load_dotenv

from auth.jwt_token_helper import get_user_id_from_token
from voice import AVAILABLE_SPEAKERS, voice_setting_repo

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
    path="/voice",
    operation_id="update_user_custom_agent_voice",
    description="사용자별 커스텀 AI TTS 설정",
    summary="사용자 음성 설정 업데이트"
)
async def update_voice_setting(
        jwt_token: str = Query(
            description="사용자 JWT 토큰 (인증용)",
            example="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
            required=True
        ),
        speaker: Optional[str] = Query(
            default=None,
            description="음성 화자 선택 (절대값으로 변경)",
            example="nara",
            enum=list(AVAILABLE_SPEAKERS.keys())
        ),
        speed: Optional[int] = Query(
            default=None,
            description="말하기 속도 상대 조절 (기존값에 +/- 적용)",
            example=1,
            ge=-5,
            le=5
        ),
        pitch: Optional[int] = Query(
            default=None,
            description="음성 높낮이 상대 조절 (기존값에 +/- 적용)",
            example=-1,
            ge=-5,
            le=5
        ),
        volume: Optional[int] = Query(
            default=None,
            description="음성 볼륨 상대 조절 (기존값에 +/- 적용)",
            example=2,
            ge=-5,
            le=5
        )
):
    """
    사용자별 커스텀 AI TTS 음성 설정을 부분 업데이트합니다.

    PATCH 방식으로 전달된 파라미터만 업데이트됩니다.

    설정 가능한 항목:
    - **speaker**: 음성 화자 (절대값으로 변경)
    - **speed**: 말하기 속도 (기존값에서 +/- 적용, 범위: -5~5)
    - **pitch**: 음성 높낮이 (기존값에서 +/- 적용, 범위: -5~5)
    - **volume**: 음성 볼륨 (기존값에서 +/- 적용, 범위: -5~5)

    예시:
    - 현재 speed=1이고 speed=2를 전달하면 → 최종 speed=3
    - 현재 pitch=0이고 pitch=-1을 전달하면 → 최종 pitch=-1
    - 현재 volume=2이고 volume=3을 전달하면 → 최종 volume=5 (최대값 5로 제한)

    Returns:
        음성 설정 업데이트 결과 및 현재 설정 정보
    """
    try:
        # JWT 토큰에서 사용자 ID 추출
        user_id = get_user_id_from_token(jwt_token)

        if not user_id:
            raise HTTPException(status_code=401, detail="유효하지 않은 JWT 토큰")

        if not voice_setting_repo:
            raise HTTPException(status_code=503, detail="음성 설정 서비스를 사용할 수 없습니다")

        # 기존 사용자 설정 조회 (없으면 기본값 생성 및 저장)
        current_settings = voice_setting_repo.get_or_default(user_id)

        logger.info(f"사용자 {user_id} 현재 설정: speaker={current_settings.speaker}, "
                    f"speed={current_settings.speed}, pitch={current_settings.pitch}, volume={current_settings.volume}")

        # 업데이트할 필드들 계산
        update_fields = {}
        changed_fields = []
        calculation_log = []

        # speaker는 절대값으로 변경
        if speaker is not None:
            update_fields["speaker"] = speaker
            changed_fields.append(f"speaker: {current_settings.speaker} → {speaker}")
            calculation_log.append(f"speaker: 절대값 변경 {speaker}")

        # speed는 상대값으로 계산
        if speed is not None:
            new_speed = current_settings.speed + speed
            # 범위 제한 (-5 ~ 5)
            new_speed = max(-5, min(5, new_speed))
            update_fields["speed"] = new_speed
            changed_fields.append(f"speed: {current_settings.speed} + ({speed}) = {new_speed}")
            calculation_log.append(f"speed: {current_settings.speed} + {speed} = {new_speed}")

        # pitch는 상대값으로 계산
        if pitch is not None:
            new_pitch = current_settings.pitch + pitch
            # 범위 제한 (-5 ~ 5)
            new_pitch = max(-5, min(5, new_pitch))
            update_fields["pitch"] = new_pitch
            changed_fields.append(f"pitch: {current_settings.pitch} + ({pitch}) = {new_pitch}")
            calculation_log.append(f"pitch: {current_settings.pitch} + {pitch} = {new_pitch}")

        # volume은 상대값으로 계산
        if volume is not None:
            new_volume = current_settings.volume + volume
            # 범위 제한 (-5 ~ 5)
            new_volume = max(-5, min(5, new_volume))
            update_fields["volume"] = new_volume
            changed_fields.append(f"volume: {current_settings.volume} + ({volume}) = {new_volume}")
            calculation_log.append(f"volume: {current_settings.volume} + {volume} = {new_volume}")

        # 업데이트할 필드가 없으면 에러
        if not update_fields:
            raise HTTPException(
                status_code=400,
                detail="업데이트할 필드가 없습니다. speaker, speed, pitch, volume 중 하나 이상을 전달해주세요."
            )

        logger.info(f"사용자 {user_id} 음성 설정 계산 결과: {'; '.join(calculation_log)}")

        # 계산된 값으로 업데이트 실행
        success = voice_setting_repo.update(user_id, **update_fields)

        if not success:
            logger.error(f"사용자 {user_id} 음성 설정 업데이트 실패")
            raise HTTPException(status_code=500, detail="음성 설정 업데이트에 실패했습니다")

        # 업데이트된 전체 설정 조회
        updated_settings = voice_setting_repo.get_or_default(user_id)

        logger.info(f"사용자 {user_id} 음성 설정 업데이트 완료")

        return {
            "success": True,
            "message": f"음성 설정이 성공적으로 업데이트되었습니다 ({len(changed_fields)}개 항목)",
            "user_id": user_id,
            "calculation_details": {
                "input_values": {
                    "speaker": speaker,
                    "speed_delta": speed,
                    "pitch_delta": pitch,
                    "volume_delta": volume
                },
                "previous_settings": {
                    "speaker": current_settings.speaker,
                    "speed": current_settings.speed,
                    "pitch": current_settings.pitch,
                    "volume": current_settings.volume
                },
                "calculation_log": calculation_log
            },
            "changed_summary": changed_fields,
            "final_settings": {
                "speaker": updated_settings.speaker,
                "speaker_info": AVAILABLE_SPEAKERS.get(updated_settings.speaker, "알 수 없는 화자"),
                "speed": updated_settings.speed,
                "pitch": updated_settings.pitch,
                "volume": updated_settings.volume,
                "format": updated_settings.format
            },
            "timestamp": datetime.now(kst).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"음성 설정 업데이트 중 오류 발생: {str(e)}")
        raise HTTPException(status_code=500, detail=f"서버 오류: {str(e)}")


def clamp_value(value: int, min_val: int = -5, max_val: int = 5) -> int:
    """
    값을 지정된 범위로 제한

    Args:
        value: 제한할 값
        min_val: 최소값 (기본값: -5)
        max_val: 최대값 (기본값: 5)

    Returns:
        int: 범위 내로 제한된 값
    """
    return max(min_val, min(max_val, value))