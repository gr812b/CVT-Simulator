"""Public identity deliberately excludes email and account credentials."""

from app.schemas.common import ApiModel


class SchoolSource(ApiModel):
    event: str
    url: str


class SchoolCatalog(ApiModel):
    updated: str
    sources: list[SchoolSource]
    schools: list[str]


class PublicUser(ApiModel):
    id: str
    display_name: str
    school: str


class PublicUserPage(ApiModel):
    items: list[PublicUser]
    total: int
    limit: int
    offset: int
