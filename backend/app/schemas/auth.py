"""Authentication transport contracts; consumed through generated frontend types."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import EmailStr, Field, StringConstraints, field_validator

from .common import ApiModel

Password = Annotated[str, StringConstraints(min_length=12, max_length=128)]
DisplayName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]


class EmailRequest(ApiModel):
    email: EmailStr

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.lower()


class RegisterRequest(EmailRequest):
    display_name: DisplayName
    password: Password


class LoginRequest(EmailRequest):
    password: str = Field(min_length=1, max_length=128)


class ResetPasswordRequest(ApiModel):
    token: str = Field(min_length=32, max_length=128)
    password: Password


class ChangePasswordRequest(ApiModel):
    current_password: str = Field(min_length=1, max_length=128)
    password: Password


class UpdateProfileRequest(ApiModel):
    display_name: DisplayName


class AuthUserResponse(ApiModel):
    id: str
    email: str
    display_name: str


class AuthAccountResponse(ApiModel):
    id: str
    name: str
    role: Literal["owner", "admin", "editor", "viewer"]


class AuthSessionResponse(ApiModel):
    user: AuthUserResponse
    account: AuthAccountResponse
    csrf_token: str
    expires_at: datetime


class AuthMessageResponse(ApiModel):
    message: str
