from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_or_create_user(
        self,
        telegram_id: int,
        username: str | None,
        full_name: str | None,
    ) -> User:
        result = await self.session.execute(select(User).where(User.id == telegram_id))
        user = result.scalar_one_or_none()

        if user is not None:
            return user

        user = User(
            id=telegram_id,
            username=username,
            full_name=full_name,
        )

        self.session.add(user)
        await self.session.commit()
        await self.session.refresh(user)

        return user
