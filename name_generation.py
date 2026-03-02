from mimesis.locales import Locale
from mimesis.enums import Gender
from mimesis import Person
from mimesis import Food
from mimesis import Text
import random

def generate_random_soldier_info() -> dict:
    person = Person(Locale.EN)
    last_name = person.last_name()
    suffixes = ['bimb', 'bloop', 'ungundes', 'bobowy', 'gloop', 'floof', 'snooncc', 'succ', 'klooc', 'fdoof', 'geschnitzel', 'benpis', 'BRAP']
    name = last_name.replace(" ", "") + random.choice(suffixes) + " " + Food().fruit()
    name = name.title()
    rank = person.title()
    nationality = person.nationality()
    political_views = person.political_views()
    title = person.title()
    university = person.university()
    worldview = person.worldview()
    txt = Text(Locale.EN)
    fav_sentence = txt.sentence()
    fav_dish = Food().dish()
    return {"name": name, "rank": rank, "nationality": nationality, "political_views": political_views, "title": title, "university": university, "worldview": worldview, "favorite_sentence": fav_sentence, "favorite_dish": fav_dish}

def main():
    for _ in range(10):
        info = generate_random_soldier_info()
        print(info)
main()