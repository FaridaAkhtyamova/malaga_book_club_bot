from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.services.club_scheduler import create_scheduler
from app.services.cycle_service import CycleService, ScheduledSuggestionReminder


def _service(*, cycle: object | None, vote_day: int = 15) -> CycleService:
    club = SimpleNamespace(
        id=1,
        group_chat_id=-100123,
        announce_hour=10,
        suggest_day=None,
        vote_day=vote_day,
    )
    service = CycleService(None, club)  # type: ignore[arg-type]
    service._localized_now = lambda now: now
    service.cycle_repo.get_latest_suggesting = AsyncMock(return_value=cycle)
    return service


def test_scheduler_runs_daily_at_announce_hour() -> None:
    scheduler = create_scheduler(AsyncMock())
    job = scheduler.get_job("club_cycle_daily")

    assert job is not None
    fields = {field.name: str(field) for field in job.trigger.fields}
    assert fields["hour"] == "10"
    assert fields["minute"] == "0"


async def test_run_scheduled_reminds_one_day_before_vote() -> None:
    cycle = SimpleNamespace(target_month=10)
    service = _service(cycle=cycle)

    action = await service.run_scheduled(datetime(2026, 10, 14, 10, tzinfo=UTC))

    assert isinstance(action, ScheduledSuggestionReminder)
    assert action.cycle is cycle
    service.cycle_repo.get_latest_suggesting.assert_awaited_once_with(1)


async def test_run_scheduled_skips_reminder_without_open_cycle() -> None:
    service = _service(cycle=None)

    action = await service.run_scheduled(datetime(2026, 10, 14, 10, tzinfo=UTC))

    assert action is None