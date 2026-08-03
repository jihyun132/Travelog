from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.globe import GlobeResponse
from app.services import trip_service

router = APIRouter(prefix="/globe", tags=["globe"])


@router.get("", response_model=GlobeResponse)
def get_globe(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> GlobeResponse:
    """지구본 렌더링용 일괄 조회 (SRS 1.1~1.2).

    내 전체 여행과 방문지를 한 번에 반환한다. 방문지는 visit_order 순이므로
    순서대로 이으면 경로가 되고, 마커 색상은 is_visited로 클라이언트가 구분한다.
    """
    return trip_service.get_globe_data(db, current_user)
