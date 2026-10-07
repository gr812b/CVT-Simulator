"""Authentication transport contracts; consumed through generated frontend types."""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, EmailStr, Field, StringConstraints, field_validator

from app.application.schools import known_school

from .common import ApiModel

Password = Annotated[str, StringConstraints(min_length=8, max_length=128)]
DisplayName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class EmailRequest(ApiModel):
    email: EmailStr

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.lower()


School = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=200),
    AfterValidator(known_school),
]


class UnitPreferences(ApiModel):
    preset: Literal["recommended", "metric", "si", "imperial"] = "recommended"
    hardware_length: Literal["in", "mm", "m"] = "in"
    component_mass: Literal["g", "kg", "oz"] = "g"
    vehicle_length: Literal["m", "ft", "in"] = "m"
    vehicle_mass: Literal["kg", "lb"] = "kg"
    course_length: Literal["m", "ft"] = "m"
    speed: Literal["km/h", "m/s", "mph"] = "km/h"
    output_length: Literal["m", "ft", "mm", "in"] = "m"
    output_speed: Literal["km/h", "m/s", "mph"] = "km/h"


class RegisterRequest(EmailRequest):
    school: School = ""
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
    school: School = ""


class AuthUserResponse(ApiModel):
    school: str
    id: str
    email: str
    display_name: str
    unit_preferences: UnitPreferences = Field(default_factory=UnitPreferences)


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
