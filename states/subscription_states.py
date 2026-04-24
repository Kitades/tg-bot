from aiogram.fsm.state import State, StatesGroup


class FreePostCreation(StatesGroup):
    waiting_for_photo = State()
    waiting_for_content = State()
    confirming_post = State()


class SubscriptionStates(StatesGroup):
    waiting_email = State()
    waiting_tariff = State()
