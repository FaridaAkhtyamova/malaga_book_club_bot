from alembic.config import Config
from sqlalchemy.engine import make_url

from app.core.config import Settings


def test_async_pg_url_preserves_reserved_credentials() -> None:
    password = "p@ss:/100%value"
    settings = Settings(
        BOT_TOKEN="test-token",
        DB_HOST="localhost",
        DB_PORT=5432,
        DB_USER="club@admin",
        DB_PASS=password,
        DB_NAME="book_club",
    )

    assert settings.async_pg_url.username == "club@admin"
    assert settings.async_pg_url.password == password

    alembic_config = Config()
    rendered_url = settings.async_pg_url.render_as_string(hide_password=False)
    alembic_config.set_main_option("sqlalchemy.url", rendered_url.replace("%", "%%"))

    assert make_url(alembic_config.get_main_option("sqlalchemy.url")).password == password