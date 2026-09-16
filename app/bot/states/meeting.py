from aiogram.fsm.state import State, StatesGroup


class MeetingInviteStates(StatesGroup):
    waiting_title = State()
    waiting_time = State()
