"""
Tests for password validation utilities.
"""
import pytest
from backend.auth.utils import validate_password_strength, is_password_too_long


class TestPasswordValidation:
    """Tests for password strength validation."""
    
    def test_valid_password(self):
        """Test that strong passwords pass validation."""
        is_valid, error = validate_password_strength("SecurePass123!")
        assert is_valid is True
        assert error == ""
    
    def test_password_too_short(self):
        """Test that short passwords fail validation."""
        is_valid, error = validate_password_strength("Short1!")
        assert is_valid is False
        assert "at least" in error.lower()
    
    def test_password_no_uppercase(self):
        """Test that passwords without uppercase fail."""
        is_valid, error = validate_password_strength("nouppercase123")
        assert is_valid is False
        assert "uppercase" in error.lower()
    
    def test_password_no_lowercase(self):
        """Test that passwords without lowercase fail."""
        is_valid, error = validate_password_strength("NOLOWERCASE123")
        assert is_valid is False
        assert "lowercase" in error.lower()
    
    def test_password_no_digit(self):
        """Test that passwords without digits fail."""
        is_valid, error = validate_password_strength("NoDigitsHere!")
        assert is_valid is False
        assert "digit" in error.lower()
    
    def test_password_no_special_char(self):
        """Test that passwords without special characters fail."""
        is_valid, error = validate_password_strength("NoSpecialChar123")
        assert is_valid is False
        assert "special" in error.lower()
    
    def test_common_password(self):
        """Test that common passwords are rejected."""
        is_valid, error = validate_password_strength("Password123!")
        assert is_valid is False
        assert "too common" in error.lower()
    
    def test_password_too_long_for_bcrypt(self):
        """Test password length check for bcrypt."""
        long_password = "A" * 73
        assert is_password_too_long(long_password) is True
        assert is_password_too_long("ShortPass1!") is False
