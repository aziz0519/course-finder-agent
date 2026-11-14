"""Authentication API contracts."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=1024)


class LoginResponse(BaseModel):
    user_id: str
    role: Literal["student", "adviser", "admin"]
    student_id: str | None = None
    adviser_id: str | None = None
    csrf_token: str


class MeResponse(BaseModel):
    user_id: str
    username: str
    role: Literal["student", "adviser", "admin"]
    student_id: str | None = None
    adviser_id: str | None = None


class LogoutResponse(BaseModel):
    success: bool = True
