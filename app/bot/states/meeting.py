from aiogram.fsm.state import State, StatesGroup


class MeetingInviteStates(StatesGroup):
    waiting_date = State()
    waiting_title = State()
    waiting_time = State()


class MeetingPollStates(StatesGroup):
    waiting_title = State()
