from app.db.models import ClubSettings
from app.services.club_destination import club_label, select_club


def _club(club_id: int, title: str | None = None) -> ClubSettings:
    return ClubSettings(
        id=club_id,
        group_chat_id=-1000 - club_id,
        title=title,
        announce_hour=10,
    )


def test_select_club_uses_active_when_still_available() -> None:
    clubs = [_club(1, "A"), _club(2, "B")]
    assert select_club(clubs, active_id=2) is clubs[1]


def test_select_club_ignores_stale_active() -> None:
    clubs = [_club(1, "A"), _club(2, "B")]
    assert select_club(clubs, active_id=9) is None


def test_select_club_single_club() -> None:
    clubs = [_club(1, "A")]
    assert select_club(clubs, active_id=None) is clubs[0]


def test_select_club_prefers_unique_open_cycle() -> None:
    clubs = [_club(1, "A"), _club(2, "B")]
    assert select_club(clubs, active_id=None, prefer_ids=[2]) is clubs[1]


def test_select_club_does_not_guess_when_several_are_open() -> None:
    clubs = [_club(1, "A"), _club(2, "B")]
    assert select_club(clubs, active_id=None, prefer_ids=[1, 2]) is None


def test_club_label_uses_title() -> None:
    assert club_label(_club(1, "Малага")) == "Малага"


def test_club_label_falls_back_to_chat_id() -> None:
    assert club_label(_club(3)) == "группа -1003"


def test_club_label_truncates_for_buttons() -> None:
    long_title = "К" * 80
    assert club_label(_club(1, long_title), limit=64) == "К" * 63 + "…"
