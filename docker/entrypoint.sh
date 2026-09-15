#!/bin/sh
set -e

python - <<'PY'
import asyncio
import os
import sys

import asyncpg


async def wait_for_postgres() -> None:
    last_error = ""
    for _ in range(40):
        try:
            conn = await asyncpg.connect(
                host=os.environ["DB_HOST"],
                port=int(os.environ.get("DB_PORT", "5432")),
                user=os.environ["DB_USER"],
                password=os.environ["DB_PASS"],
                database=os.environ["DB_NAME"],
            )
            await conn.close()
            return
        except Exception as exc:
            last_error = str(exc)
            await asyncio.sleep(1)
    print(f"Postgres is not ready: {last_error}", file=sys.stderr)
    raise SystemExit(1)


asyncio.run(wait_for_postgres())
PY

alembic upgrade head
exec python main.py
