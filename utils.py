import json
import inflect
from dateutil import parser
from datetime import date, timedelta

p = inflect.engine()


def load_constants(path="constants.json"):
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def get_singular_name(name):
    clean_name = name.lower().strip()
    singular = p.singular_noun(clean_name)
    return singular if singular else clean_name


def parse_expiry(raw_expiry):
    if raw_expiry is None:
        return None
    return parser.parse(raw_expiry, dayfirst=True).date()


def calculate_expiry_date(item_name, constants, default_days=3):
    clean_name = get_singular_name(item_name)
    shelf_life = constants.get(clean_name, {}).get("shelf_life", default_days)
    return date.today() + timedelta(days=shelf_life)
