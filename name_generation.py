from mimesis.locales import Locale
from mimesis.enums import Gender
from mimesis import Person
from mimesis import Food
from mimesis import Text
import random

def generate_random_soldier_info() -> dict:
    person = Person(Locale.EN)
    last_name = person.last_name()
    suffixes = ['bimb', 'bloop', 'ungundes', 'bobowy', 'gloop', 'floof', 'snooncc', 'succ', 'klooc', 'fdoof', 'geschnitzel', 'benpis', 'BRAP', 'unc', 'fart', 'shart', 'dundles', 'fug', 'shitten', 'ecksdee']
    name = last_name.replace(" ", "") + random.choice(suffixes) + " " + Food().fruit()
    name = name.title()
    rank = person.title()
    nationality = person.nationality()
    political_views = person.political_views()
    title = person.title()
    university = person.university()
    worldview_prefix = ["radical", "extremist", "shy", "curious", "martyrdom-based", "communist", "capitalist", "jungian", "archaist", "demi-", "fucking", "happy", "depressive", "social", "technical", "marxist", "platonic", "idealistic", "mathematical", "degenerate", "orthodox", "alcohol driven", "idiotic"]
    worldview = random.choice(worldview_prefix).title() + " " + person.worldview().title()
    txt = Text(Locale.EN)
    fav_sentence = txt.sentence()
    fav_dish = Food().dish()
    occupation_prefix = ["shitty", "skilled", "demotivated", "overworked", "lousy", "decent", "normal", "world class", "known", "great", "incompetent", "beginner"]
    occupation = random.choice(occupation_prefix) + " " + person.occupation()
    return {"name": name, "rank": rank, "nationality": nationality, "political_views": political_views, "title": title, "university": university, "worldview": worldview, "favorite_sentence": fav_sentence, "favorite_dish": fav_dish, "occupation": occupation}

def generate_team_name() -> str:
    food = Food(Locale.EN)
    text = Text(Locale.EN)
    return f"{food.vegetable().title()} {text.level().title()}s"

def main():
    for _ in range(10):
        info = generate_random_soldier_info()
        print(info)
    print("Team name:", generate_team_name())

main()