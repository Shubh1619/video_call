from fastapi import APIRouter, Depends, Body, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, date, timezone
import re
from backend.email.db import get_db
from backend.auth.utils import get_current_user
from backend.models.notes import Note
from backend.scheduler.unified_scheduler import schedule_note_reminder

router = APIRouter()


def _is_meaningful_note(value: str) -> bool:
    text = (value or "").strip()
    return bool(text) and not re.fullmatch(r"[.\s]+", text)

# ------------------------------------------------------
# Helper: Serialize Note
# ------------------------------------------------------
def note_to_dict(n: Note):
    return {
        "id": n.id,
        "note_text": n.content,  # backward-compatible response key
        "content": n.content,
        "note_date": n.note_date.isoformat() if n.note_date else None,
        "meeting_id": n.meeting_id,
    }

# ------------------------------------------------------
# CREATE NOTE
# ------------------------------------------------------
@router.post("/notes/create")
def create_note(
    note_text: str = Body(...),
    note_date: str = Body(...),  # YYYY-MM-DD
    meeting_id: int | None = Body(None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not _is_meaningful_note(note_text):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Note cannot be empty or meaningless",
        )

    try:
        date_obj = datetime.strptime(note_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid date format. Use YYYY-MM-DD",
        )

    new_note = Note(
        user_id=current_user.id,
        meeting_id=meeting_id,
        note_date=date_obj,
        content=note_text,
    )

    db.add(new_note)
    db.commit()
    db.refresh(new_note)

    # Schedule reminder email
    schedule_note_reminder(
        note_id=new_note.id,
        user_email=current_user.email,
        note_text=note_text,
        note_date=date_obj,
    )

    return {
        "msg": "Note saved",
        "note": note_to_dict(new_note),
    }


@router.put("/notes/{note_id}")
def update_note(
    note_id: int,
    note_text: str = Body(..., embed=True),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if not _is_meaningful_note(note_text):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Note cannot be empty or meaningless",
        )

    note = db.query(Note).filter(
        Note.id == note_id,
        Note.user_id == current_user.id,
    ).first()

    if not note:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")

    note.content = note_text.strip()
    db.commit()
    db.refresh(note)

    return {"msg": "Note updated", "note": note_to_dict(note)}


@router.delete("/notes/{note_id}")
def delete_note(
    note_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    note = db.query(Note).filter(
        Note.id == note_id,
        Note.user_id == current_user.id,
    ).first()

    if not note:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")

    db.delete(note)
    db.commit()
    return {"msg": "Note deleted", "id": note_id}

# ------------------------------------------------------
# GET NOTES BY DATE (DETAIL VIEW)
# ------------------------------------------------------
@router.get("/notes/by-date")
def get_notes_by_date(
    date: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    try:
        target_date = datetime.strptime(date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid date format. Use YYYY-MM-DD",
        )

    notes = db.query(Note).filter(
        Note.user_id == current_user.id,
        Note.note_date == target_date,
    ).all()

    return {
        "date": date,
        "notes": [note_to_dict(n) for n in notes],
    }

# ------------------------------------------------------
# GET NOTES BY MONTH (CALENDAR MARKERS)
# ------------------------------------------------------
@router.get("/notes/by-month")
def get_notes_by_month(
    year: int,
    month: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    if month < 1 or month > 12:
        raise HTTPException(status_code=400, detail="Invalid month")

    start_date = date(year, month, 1)
    end_date = (
        date(year + 1, 1, 1)
        if month == 12
        else date(year, month + 1, 1)
    )

    notes = db.query(Note.note_date).filter(
        Note.user_id == current_user.id,
        Note.note_date >= start_date,
        Note.note_date < end_date,
    ).distinct().all()

    return {
        "dates": [n.note_date.isoformat() for n in notes],
        "notes": [{"note_date": n.note_date.isoformat()} for n in notes]
    }


# Backward-compatible endpoint (matches frontend expectations)
@router.get("/notes/month")
def get_notes_by_month_compat(
    month: str,  # Format: "YYYY-MM"
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    try:
        year, mon = map(int, month.split("-"))
    except (ValueError, AttributeError):
        return {"dates": [], "notes": []}
    
    return get_notes_by_month(year, mon, db, current_user)
