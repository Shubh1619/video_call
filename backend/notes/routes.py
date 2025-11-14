from fastapi import APIRouter, Depends, Body
from sqlalchemy.orm import Session
from datetime import datetime
from backend.email.db import get_db
from backend.auth.utils import get_current_user
from backend.models.notes import Note
from backend.email.utils import send_note_reminder_email
from backend.scheduler.note_scheduler import schedule_note_reminder

router = APIRouter()

@router.post("/notes/create")
def create_note(
    note_text: str = Body(...),
    note_date: str = Body(...),   # format YYYY-MM-DD
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    date_obj = datetime.strptime(note_date, "%Y-%m-%d").date()

    new_note = Note(
        user_id=current_user.id,
        note_date=date_obj,
        note_text=note_text
    )
    db.add(new_note)
    db.commit()
    db.refresh(new_note)

    # Schedule email reminder
    schedule_note_reminder(
        note_id=new_note.id,
        user_email=current_user.email,
        note_text=note_text,
        note_date=date_obj
    )

    return {"msg": "Note saved", "note": new_note}


@router.get("/notes/by-date")
def get_notes_by_date(
    date: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    target_date = datetime.strptime(date, "%Y-%m-%d").date()

    notes = db.query(Note).filter(
        Note.user_id == current_user.id,
        Note.note_date == target_date
    ).all()

    return {"date": date, "notes": notes}
