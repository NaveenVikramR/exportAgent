"""Names that ground a destination country in the email text: the country, its usual short
forms, and the cities and ports buyers write instead ("lands in Melbourne", "our Vancouver
warehouse"). A destination with none of these in the email was inferred, not stated.
"""

import re

PLACES: dict[str, tuple[str, ...]] = {
    "United States": ("united states", "USA", "U.S.A", "U.S.", "US", "america", "new york", "los angeles", "long beach",
                      "savannah", "seattle", "chicago", "houston", "miami", "newark", "oakland", "charleston",
                      "san francisco", "dallas", "atlanta", "boston", "norfolk"),
    "United Kingdom": ("united kingdom", "UK", "U.K.", "great britain", "britain", "england", "scotland", "wales",
                       "london", "manchester", "bristol", "birmingham", "leeds", "glasgow", "felixstowe", "southampton",
                       "liverpool"),
    "Germany": ("germany", "deutschland", "hamburg", "bremen", "bremerhaven", "berlin", "munich", "münchen",
                "düsseldorf", "dusseldorf", "cologne", "köln", "frankfurt", "stuttgart"),
    "Japan": ("japan", "nippon", "tokyo", "osaka", "yokohama", "kobe", "nagoya"),
    "Australia": ("australia", "melbourne", "sydney", "brisbane", "perth", "adelaide"),
    "Canada": ("canada", "vancouver", "toronto", "montreal", "montréal", "calgary"),
    "Ireland": ("ireland", "éire", "dublin", "cork"),
    "Spain": ("spain", "españa", "madrid", "barcelona", "valencia"),
    "France": ("france", "paris", "lyon", "marseille", "le havre"),
    "Netherlands": ("netherlands", "holland", "nederland", "rotterdam", "amsterdam"),
    "Austria": ("austria", "österreich", "vienna", "wien", "graz"),
    "Norway": ("norway", "norge", "oslo", "bergen"),
    "United Arab Emirates": ("united arab emirates", "UAE", "U.A.E", "dubai", "abu dhabi", "jebel ali"),
    "Italy": ("italy", "italia", "milan", "milano", "genoa", "genova"),
    "Sweden": ("sweden", "sverige", "stockholm", "gothenburg", "göteborg"),
    "Denmark": ("denmark", "danmark", "copenhagen", "københavn", "aarhus"),
    "Belgium": ("belgium", "antwerp", "brussels"),
    "Poland": ("poland", "polska", "warsaw", "gdansk"),
}


def _mentions(text: str, name: str) -> bool:
    # Whole words only. Codes in capitals (US, UK, UAE) match case-sensitively, so the
    # pronoun in "please send us" does not ground the United States.
    pattern = rf"(?<![\w.]){re.escape(name)}(?![\w])"
    if name.isupper():
        return re.search(pattern, text) is not None
    return re.search(pattern, text.casefold()) is not None


def names_country(text: str, country: str) -> bool:
    """True when `text` names `country`, one of its short forms, or one of its cities or ports."""
    names = PLACES.get(country, ()) + (country.casefold(),)
    return any(_mentions(text, name) for name in names)
