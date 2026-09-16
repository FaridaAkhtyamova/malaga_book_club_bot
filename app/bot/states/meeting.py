from aiogram.fsm.state import State, StatesGroup


class MeetingInviteStates(StatesGroup):
    waiting_time = State()
