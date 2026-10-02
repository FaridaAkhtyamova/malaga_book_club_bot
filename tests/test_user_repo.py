from unittest.mock import AsyncMock, Mock

from app.db.models import User
from app.repositories.user_repo import UserRepository


async def test_get_or_create_user_refreshes_existing_profile() -> None:
    session = AsyncMock()
    result = Mock()
    user = User(id=123, username=None, full_name=None)
    result.scalar_one_or_none.return_value = user
    session.execute.return_value = result

    saved = await UserRepository(session).get_or_create_user(
        telegram_id=123,
        username="ann",
        full_name="Anna Example",
    )

    assert saved.full_name == "Anna Example"
    assert saved.username == "ann"
    session.commit.assert_awaited_once()
    session.refresh.assert_awaited_once_with(user)


async def test_get_or_create_user_keeps_profile_when_values_are_missing() -> None:
    session = AsyncMock()
    result = Mock()
    user = User(id=123, username="ann", full_name="Anna Example")
    result.scalar_one_or_none.return_value = user
    session.execute.return_value = result

    saved = await UserRepository(session).get_or_create_user(
        telegram_id=123,
        username=None,
        full_name=None,
    )

    assert saved.full_name == "Anna Example"
    assert saved.username == "ann"
    session.commit.assert_not_awaited()