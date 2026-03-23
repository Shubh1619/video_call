from fastapi import APIRouter, Depends, Body, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, date, timezone
from backend.email.db import get_db
from backend.auth.utils import get_current_user
from backend.models.notes import Note
from backend.scheduler.unified_scheduler import schedule_note_reminder

router = APIRouter()

# ------------------------------------------------------
# Helper: Serialize Note
# ------------------------------------------------------
def note_to_dict(n: Note):
    return {
        "id": n.id,
        "note_text": n.note_text,
        "note_date": n.note_date.isoformat() if n.note_date else None,
    }

# ------------------------------------------------------
# CREATE NOTE
# ------------------------------------------------------
@router.post("/notes/create")
def create_note(
    note_text: str = Body(...),
    note_date: str = Body(...),  # YYYY-MM-DD
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    try:
        date_obj = datetime.strptime(note_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid date format. Use YYYY-MM-DD",
        )

    new_note = Note(
        user_id=current_user.id,
        note_date=date_obj,
        note_text=note_text,
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

# ------------------------------------------------------
# DELETE NOTES BY DATE
# ------------------------------------------------------
@router.delete("/notes/delete-by-date")
def delete_notes_by_date(
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

    if not notes:
        return {
            "msg": "No notes found for this date",
            "date": date,
        }

    for note in notes:
        db.delete(note)

    db.commit()

    return {
        "msg": "Notes deleted successfully",
        "deleted_count": len(notes),
        "date": date,
    }
