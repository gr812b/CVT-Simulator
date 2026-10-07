"""Worker capacity and deployment readiness settings fail early when invalid."""

import os

import pytest

from app.core.settings import Settings


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    for name in os.environ:
        if name.startswith("CVT_"):
            monkeypatch.delenv(name)


def test_worker_defaults_keep_one_slot_and_local_development_independent():
    settings = Settings.from_environment()
    assert settings.worker_max_concurrency == 1
    assert settings.worker_api_url == ""


def test_worker_settings_read_capacity_and_normalize_api_url(monkeypatch):
    monkeypatch.setenv("CVT_WORKER_MAX_CONCURRENCY", "5")
    monkeypatch.setenv("CVT_WORKER_API_URL", "http://cvt-backend:8000/")
    settings = Settings.from_environment()
    assert settings.worker_max_concurrency == 5
    assert settings.worker_api_url == "http://cvt-backend:8000"


@pytest.mark.parametrize("value", ["0", "-1", "1.5", "five", "", "nan"])
def test_invalid_capacity_environment_is_rejected(monkeypatch, value):
    monkeypatch.setenv("CVT_WORKER_MAX_CONCURRENCY", value)
    with pytest.raises(ValueError, match="CVT_WORKER_MAX_CONCURRENCY.*positive integer"):
        Settings.from_environment()


@pytest.mark.parametrize("value", [0, -1, 1.5, True, False, "5", None])
def test_invalid_capacity_constructor_is_rejected(value):
    with pytest.raises(ValueError, match="CVT_WORKER_MAX_CONCURRENCY.*positive integer"):
        Settings(worker_max_concurrency=value)


@pytest.mark.parametrize(
    "url", ["cvt-backend:8000", "file:///tmp/api", "https://", "http://api/?q=x", "http://api/#x"]
)
def test_worker_readiness_url_must_be_an_http_base_url(url):
    with pytest.raises(ValueError, match="CVT_WORKER_API_URL"):
        Settings(worker_api_url=url)
