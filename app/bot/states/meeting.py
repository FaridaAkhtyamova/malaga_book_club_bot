from aiogram.fsm.state import State, StatesGroup


class MeetingInviteStates(StatesGroup):
    waiting_date = State()
    waiting_time = State()
