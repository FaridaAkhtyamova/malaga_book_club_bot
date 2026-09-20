from app.bot.club_context import format_clubs_list
from app.bot.commands import format_help, member_bot_commands
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


def test_clubs_list_single_group_has_no_catalog() -> None:
    text = format_clubs_list([_club(1, "Малага")], active_id=1)
    assert "Ваши клубы" not in text
    assert "Малага" in text


def test_clubs_list_many_asks_to_pick_group() -> None:
    text = format_clubs_list([_club(1, "A"), _club(2, "B")], active_id=2)
    assert "Выберите, с какой группой работать в личке" in text
    assert "B ✓" in text


def test_member_help_omits_clubs() -> None:
    text = format_help(is_admin=False)
    assert "/clubs" not in text
    assert "/suggest" in text
    assert "/open_suggestions" not in text
    assert all(cmd.command != "clubs" for cmd in member_bot_commands())


def test_admin_help_includes_member_admin_and_clubs() -> None:
    text = format_help(is_admin=True)
    assert "/suggest" in text
    assert "/open_suggestions" in text
    assert "/clubs" in text
