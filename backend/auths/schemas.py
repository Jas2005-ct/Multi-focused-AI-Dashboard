from pydantic import BaseModel
from typing import Optional


class UserSchema(BaseModel):
    id: int
    email: str
    name: Optional[str] = None

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
