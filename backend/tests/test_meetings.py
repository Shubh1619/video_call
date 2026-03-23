"""
Tests for meeting endpoints.
"""
import pytest
from fastapi import status
from datetime import datetime, timedelta, timezone


class TestScheduleMeeting:
    """Tests for scheduling meetings."""
    
    def test_create_scheduled_meeting(self, client, auth_headers):
        """Test creating a scheduled meeting."""
        start_time = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        end_time = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
        
        response = client.post(
            "/schedule",
            json={
                "title": "Test Meeting",
                "agenda": "Test agenda",
                "start_time": start_time,
                "end_time": end_time,
                "participants": []
            },
            headers=auth_headers
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "meeting_id" in data
        assert "join_link" in data
        assert data["msg"] == "Scheduled meeting created."
    
    def test_create_instant_meeting(self, client, auth_headers):
        """Test creating an instant meeting."""
        response = client.post(
            "/instant",
            json={
                "title": "Instant Meeting",
                "agenda": "Quick meeting",
                "participants": []
            },
            headers=auth_headers
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "meeting_id" in data
        assert data["msg"] == "Instant meeting started."
    
    def test_schedule_meeting_unauthenticated(self, client):
        """Test scheduling meeting without authentication."""
        start_time = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        end_time = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
        
        response = client.post(
            "/schedule",
            json={
                "title": "Test Meeting",
                "start_time": start_time,
                "end_time": end_time
            }
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestGetMeetings:
    """Tests for retrieving meetings."""
    
    def test_get_meetings_by_date(self, client, auth_headers):
        """Test getting meetings by date."""
        response = client.get(
            "/meetings?date=2024-01-15",
            headers=auth_headers
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "meetings" in data
        assert "date" in data
    
    def test_get_meetings_by_month(self, client, auth_headers):
        """Test getting meetings by month."""
        response = client.get(
            "/meetings/by-month?year=2024&month=1",
            headers=auth_headers
        )
        assert response.status_code == status.HTTP_200_OK
        assert isinstance(response.json(), list)
