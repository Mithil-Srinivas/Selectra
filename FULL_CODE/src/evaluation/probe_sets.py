"""Query sets for retrieval probing. Gold products are defined by catalogue filters, never hand-picked IDs.

- TWISTED: descriptive / Hinglish requests that name no brand or product line ("baal sukhane wali machine").
- OUT_OF_CATALOGUE: things the store does not sell; the interpreter should return sub_category = null.
- synth_queries(): misspelt / split brand + line names generated from catalogue titles.
Written independently of questions_test.csv so test questions never leak into tuning.
"""
from __future__ import annotations

import random
import re

import pandas as pd

# (query, gold sub_category, required attributes)
TWISTED: list[tuple[str, str, dict]] = [
    ("baal sukhane wali machine", "Hair Dryers", {}),
    ("chai ke liye paani garam karne wala electric", "Electric Kettles", {}),
    ("daadi trim karne ki machine", "Trimmers", {}),
    ("garmi me hawa ke liye ghoomne wala", "Fans", {"oscillation": True}),
    ("sardi me kamra garam karne ke liye kuch", "Room Heaters", {}),
    ("kapde press karne wala steam wala", "Irons", {"iron_type": "steam"}),
    ("phone charge karne ka battery wala dabba 20000 wala", "Power Banks", {"capacity_mah": 20000}),
    ("bachon ke liye lego jaisa kuch", "Building Blocks", {}),
    ("dhoop se bachne ki cream spf 50", "Sunscreen", {"spf": 50}),
    ("pasine ki badbu ke liye spray", "Deodorants & Perfumes", {}),
    ("tiffin dabba steel ka", "Lunch Boxes", {"material": "stainless steel"}),
    ("pressure cooker 5 litre", "Pressure Cookers", {"capacity_l": 5}),
    ("gym me haath chhil jaate hai uske liye kuch", "Gym Gloves", {}),
    ("kasrat ke liye kudne wali rassi", "Skipping Ropes", {}),
    ("5 kg ka dumbbell", "Dumbbells", {"weight_kg": 5}),
    ("kaan me lagane wale bina taar wale", "Wireless Earbuds", {}),
    ("taar wale kaan ke headphone", "Wired Earphones", {}),
    ("computer ka chuha", "Computer Mouse", {}),
    ("15.6 inch laptop rakhne ka cover", "Laptop Sleeves", {"fits_laptop_upto_in": 15.6}),
    ("safar ke liye pahiye wala bada bag", "Trolley Bags", {}),
    ("paise aur card rakhne ka chhota purse aadmi ke liye", "Wallets", {}),
    ("parde jo roshni bilkul rok de", "Curtains", {"blackout": True}),
    ("double bed ki chadar", "Bedsheets", {"bed_size": "double"}),
    ("nahane ke baad pochne wala kapda", "Towels", {}),
    ("pani ki bottle jo der tak thanda rakhe", "Water Bottles", {"insulated": True}),
    ("shaadi ke liye festive kurti", "Kurtis", {"occasion": "festive"}),
    ("scientific wala hisaab lagane ka machine", "Calculators", {"calculator_type": "scientific"}),
    ("bacchon ke rang bharne ke liye crayons", "Colours & Crayons", {}),
    ("remote se chalne wali gaadi", "Remote Control Cars", {}),
    ("masala pisne ki machine", "Mixer Grinders", {}),
    ("bina tel ke fry karne wala", "Air Fryers", {}),
    ("double roti senkne wala", "Toasters", {}),
    ("chulha jo bina gas ke chale", "Induction Cooktops", {}),
    ("cricket khelne ka balla", "Cricket Bats", {}),
    ("bachon ke school ke kaale joote", "Kids School Shoes", {"colour": "black"}),
]

OUT_OF_CATALOGUE = ["samsung galaxy s24 ka price", "aashirvaad atta 10 kg", "dolo 650 tablet strip", "gold chain dikhao",
                    "honda activa ka rate", "printer ink cartridge", "redmi phone ka back cover", "43 inch LED TV",
                    "dell laptop i5 16gb", "basmati chawal 5 kg"]


def _attr_match(attrs: dict, key: str, want) -> bool:
    if key not in attrs:
        return False
    have = attrs[key]
    if isinstance(want, bool):
        return have is want
    if isinstance(want, (int, float)):
        try:
            return float(have) == float(want)
        except (TypeError, ValueError):
            return False
    return str(have).lower() == str(want).lower()


def twisted_gold(cat: pd.DataFrame, sub: str, attrs: dict) -> set[str]:
    m = (cat.sub_category == sub) & cat.attributes.map(lambda a: all(_attr_match(a, k, v) for k, v in attrs.items()))
    return set(cat.product_id[m])


def _typo(w: str, rng: random.Random) -> str:
    if len(w) < 4:
        return w
    i = rng.randrange(1, len(w) - 1)
    op = rng.choice(["del", "dup", "swap", "vowel"])
    if op == "del":
        return w[:i] + w[i + 1:]
    if op == "dup":
        return w[:i] + w[i] + w[i:]
    if op == "swap":
        return w[:i] + w[i + 1] + w[i] + w[i + 2:]
    return re.sub("[aeiou]", lambda m: rng.choice("aeiou"), w, count=1)


TAILS = ["kitne ka hai", "price", "kitne ki hai", "stock me hai?", "rate?", "dikhao", "ka price kya hai", "chahiye", ""]
SKIP = {"men's", "women's", "boys'", "girls'", "kids'", "with", "and", "for"}


def synth_queries(cat: pd.DataFrame, n: int = 200, seed: int = 7) -> list[dict]:
    """One query per sampled product line: brand (maybe misspelt) + line (maybe split/misspelt) + product noun."""
    rng = random.Random(seed)
    lines = cat.assign(line=cat.brand + " " + cat.line_name).sample(frac=1, random_state=1).drop_duplicates("line")
    out = []
    for r in lines.sample(n, random_state=11).itertuples():
        head, _, variant = r.title.partition(" - ")
        words = [w for w in head.split()[2:] if w.lower() not in SKIP]
        noun = " ".join([w for w in words if w.isalpha()][-2:]).lower()
        if m := re.search(r"(Pack of \d+|\d+ Pieces)", head):
            noun += " " + m.group(1).lower()
        brand = r.brand.lower() if rng.random() < 0.4 else _typo(r.brand.lower(), rng)
        line = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", r.line_name).lower() if rng.random() < 0.5 else r.line_name.lower()
        if rng.random() < 0.3:
            line = _typo(line, rng)
        parts = [brand, line, variant.lower() if variant and rng.random() < 0.6 else "", noun, rng.choice(TAILS)]
        out.append({"q": " ".join(p for p in parts if p),
                    "gold": set(cat.product_id[(cat.brand == r.brand) & (cat.line_name == r.line_name)])})
    return out
