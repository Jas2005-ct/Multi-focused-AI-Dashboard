import re
from pydantic import BaseModel, field_validator
from typing import Optional


EMAIL_REGEX = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')


class UserSchema(BaseModel):
    id: int
    email: str
    name: Optional[str] = None
    
    @field_validator('email')
    @classmethod
    def validate_email_format(cls, v):
        if not EMAIL_REGEX.match(v):
            raise ValueError('Invalid email format')
        return v.lower()

    model_config = {
        "json_schema_extra": {
            "example": {
                "id": 1,
                "email": "jaswant@gmail.com",
                "name": "Jaswant"
            }
        }
    }


class ValidateErrorSchema(BaseModel):
    error: str
    message: str

    model_config = {
        "json_schema_extra": {
            "example": {
                "error": "Email already exists",
                "message": "Please login with Google"
            }
        }
    }


class ValidateSuccessSchema(BaseModel):
    token: str
    user: UserSchema

    model_config = {
        "json_schema_extra": {
            "example": {
                "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoxLCJlbWFpbCI6Imphc3dhbnRoc2FuaUBnbWFpbC5jb20iLCJleHAiOjE2OTYyNzQzNjR9.1234567890",
                "user": {
                    "id": 1,
                    "email": "jaswant@gmail.com",
                    "name": "Jaswant"
                }
            }
        }
    }


class RegisterRequest(BaseModel):
    email: str
    password: str
    name: Optional[str] = None
    
    @field_validator('email')
    @classmethod
    def validate_email_format(cls, v):
        if not EMAIL_REGEX.match(v):
            raise ValueError('Invalid email format')
        return v.lower()
    
    @field_validator('password')
    @classmethod
    def validate_password_strength(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters')
        if not re.search(r'[A-Z]', v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not re.search(r'[a-z]', v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not re.search(r'\d', v):
            raise ValueError('Password must contain at least one digit')
        return v


class LoginRequest(BaseModel):
    email: str
    password: str
    
    @field_validator('email')
    @classmethod
    def validate_email_format(cls, v):
        if not EMAIL_REGEX.match(v):
            raise ValueError('Invalid email format')
        return v.lower()
