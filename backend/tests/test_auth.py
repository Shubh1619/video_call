"""
Tests for authentication endpoints.
"""
import pytest
from fastapi import status


class TestAuthRegister:
    """Tests for user registration."""
    
    def test_register_success(self, client):
        """Test successful user registration."""
        response = client.post(
            "/auth/register",
            json={
                "email": "newuser@example.com",
                "password": "SecurePass123!",
                "name": "New User"
            }
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
    
    def test_register_weak_password(self, client):
        """Test registration with weak password."""
        response = client.post(
            "/auth/register",
            json={
                "email": "weak@example.com",
                "password": "123",
                "name": "Weak User"
            }
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "password" in response.json()["detail"].lower()
    
    def test_register_duplicate_email(self, client, test_user):
        """Test registration with existing email."""
        response = client.post(
            "/auth/register",
            json={
                "email": "test@example.com",
                "password": "DifferentPass123!",
                "name": "Another User"
            }
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "already registered" in response.json()["detail"].lower()


class TestAuthLogin:
    """Tests for user login."""
    
    def test_login_success(self, client, test_user):
        """Test successful login."""
        response = client.post(
            "/auth/login",
            data={
                "username": "test@example.com",
                "password": "TestPass123!"
            }
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
    
    def test_login_wrong_password(self, client, test_user):
        """Test login with wrong password."""
        response = client.post(
            "/auth/login",
            data={
                "username": "test@example.com",
                "password": "WrongPassword123!"
            }
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    def test_login_nonexistent_user(self, client):
        """Test login with non-existent email."""
        response = client.post(
            "/auth/login",
            data={
                "username": "nonexistent@example.com",
                "password": "SomePass123!"
            }
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED


class TestAuthUser:
    """Tests for getting current user."""
    
    def test_get_user_authenticated(self, client, auth_headers):
        """Test getting current user when authenticated."""
        response = client.get("/auth/user", headers=auth_headers)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["email"] == "test@example.com"
        assert data["name"] == "Test User"
    
    def test_get_user_unauthenticated(self, client):
        """Test getting current user without authentication."""
        response = client.get("/auth/user")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
