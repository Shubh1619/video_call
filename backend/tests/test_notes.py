"""
Tests for notes endpoints.
"""
import pytest
from fastapi import status


class TestNotes:
    """Tests for notes functionality."""
    
    def test_create_note(self, client, auth_headers):
        """Test creating a note."""
        response = client.post(
            "/notes/create",
            json={
                "note_text": "Test note content",
                "note_date": "2024-01-15"
            },
            headers=auth_headers
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["msg"] == "Note saved"
        assert "note" in data
    
    def test_get_notes_by_date(self, client, auth_headers):
        """Test getting notes by date."""
        response = client.get(
            "/notes/by-date?date=2024-01-15",
            headers=auth_headers
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "notes" in data
        assert "date" in data
    
    def test_get_notes_by_month(self, client, auth_headers):
        """Test getting notes by month."""
        response = client.get(
            "/notes/by-month?year=2024&month=1",
            headers=auth_headers
        )
        assert response.status_code == status.HTTP_200_OK
        assert isinstance(response.json(), list)
    
    def test_delete_notes_by_date(self, client, auth_headers):
        """Test deleting notes by date."""
        response = client.delete(
            "/notes/delete-by-date?date=2024-01-15",
            headers=auth_headers
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "msg" in data
    
    def test_create_note_invalid_date(self, client, auth_headers):
        """Test creating a note with invalid date format."""
        response = client.post(
            "/notes/create",
            json={
                "note_text": "Test note",
                "note_date": "invalid-date"
            },
            headers=auth_headers
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
