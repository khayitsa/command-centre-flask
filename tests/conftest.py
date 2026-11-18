import pytest

from command_centre import create_app


@pytest.fixture()
def app(tmp_path):
    return create_app({
        "TESTING": True,
        "SECRET_KEY": "test-secret",
        "DATABASE": str(tmp_path / "test.db"),
        "SESSION_COOKIE_SECURE": False,
        "ALLOW_SIGNUP": False,
    })
