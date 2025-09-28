from aiogram.dispatcher.filters.state import State, StatesGroup

class States(StatesGroup):
    subject = State()
    topic = State()
    grade = State()
    count = State()
    language = State()
    qtype = State()

class AdminStates(StatesGroup):
    broadcast_text = State()
    broadcast_photo = State()

class WikiStates(StatesGroup):
    query = State()
    pick = State()

class ModifyStates(StatesGroup):
    collecting = State()
    answers = State()
    choose_mod = State()