import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from backend.auth.utils import get_current_user
from backend.email.db import get_db
from backend.models.meeting import Meeting

router = APIRouter()


@router.post("/meetings/cleanup")
def cleanup_expired_meetings(db: Session = Depends(get_db)):
    from backend.scheduler.unified_scheduler import delete_expired_meetings

    try:
        delete_expired_meetings()
        return {"message": "Expired meetings cleaned up successfully"}
    except Exception as exc:
        logging.error("Cleanup failed: %s", exc)
        return {"error": str(exc)}


@router.delete("/meetings/{meeting_id}")
def delete_scheduled_meeting(
    meeting_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    meeting = (
        db.query(Meeting)
        .filter(
            Meeting.id == meeting_id,
            Meeting.owner_id == current_user.id,
            Meeting.meeting_type == "regular",
        )
        .first()
    )

    if not meeting:
        return JSONResponse(
            status_code=404,
            content={"error": "Scheduled meeting not found or not authorized"},
        )

    db.delete(meeting)
    db.commit()
    logging.info("Deleted scheduled meeting %s", meeting_id)
    return {"message": "Scheduled meeting deleted successfully", "id": meeting_id}
