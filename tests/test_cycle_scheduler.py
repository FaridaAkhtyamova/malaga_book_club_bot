from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

from app.services import club_scheduler
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


async def test_scheduler_rolls_back_and_continues_after_club_failure(monkeypatch) -> None:
    clubs = [
        SimpleNamespace(id=1, group_chat_id=-1001),
        SimpleNamespace(id=2, group_chat_id=-1002),
    ]
    sessions: list[SimpleNamespace] = []

    class SessionContext:
        async def __aenter__(self):
            session = SimpleNamespace(rollback=AsyncMock())
            sessions.append(session)
            return session

        async def __aexit__(self, exc_type, exc, traceback):
            return None

    services = [
        SimpleNamespace(run_scheduled=AsyncMock(side_effect=RuntimeError("database failure"))),
        SimpleNamespace(run_scheduled=AsyncMock(return_value=None)),
    ]
    service_index = 0

    class Repository:
        def __init__(self, session_arg):
            self.session = session_arg

        async def list_bound(self):
            return clubs

        async def get_by_chat_id(self, chat_id):
            return next(club for club in clubs if club.group_chat_id == chat_id)

    def service_factory(session_arg, club):
        nonlocal service_index
        service = services[service_index]
        service_index += 1
        return service

    monkeypatch.setattr(club_scheduler, "AsyncSessionLocal", SessionContext)
    monkeypatch.setattr(club_scheduler, "get_settings", lambda: SimpleNamespace(TIMEZONE="UTC"))
    monkeypatch.setattr(
        club_scheduler,
        "SettingsRepository",
        lambda session_arg: Repository(session_arg),
    )
    monkeypatch.setattr(club_scheduler, "CycleService", service_factory)
    monkeypatch.setattr(club_scheduler, "destination_of", lambda club: object())

    await club_scheduler.run_scheduled_jobs(AsyncMock())

    assert len(sessions) == 3
    sessions[1].rollback.assert_awaited_once()
    sessions[2].rollback.assert_not_awaited()
    for service in services:
        service.run_scheduled.assert_awaited_once()