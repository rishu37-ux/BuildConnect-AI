"""Gazetteer for Punjab, Himachal Pradesh and Chandigarh."""

from __future__ import annotations

import re

from .models import State

# district -> list of extra place names (towns / alternate spellings) that map to it
PUNJAB_DISTRICTS: dict[str, list[str]] = {
    "Amritsar": [], "Barnala": [], "Bathinda": ["Bhatinda"], "Faridkot": [], "Fatehgarh Sahib": ["Sirhind"],
    "Fazilka": ["Abohar"], "Ferozepur": ["Firozpur"], "Gurdaspur": ["Batala"],
    "Hoshiarpur": [], "Jalandhar": ["Jullundur", "Phagwara"], "Kapurthala": [], "Ludhiana": ["Khanna"],
    "Malerkotla": [], "Mansa": [], "Moga": [], "Muktsar": ["Sri Muktsar Sahib"], "Pathankot": [],
    "Patiala": ["Rajpura"], "Rupnagar": ["Ropar"], "Sangrur": [],
    "Sahibzada Ajit Singh Nagar": ["Mohali", "SAS Nagar", "Zirakpur", "Kharar"],
    "Shaheed Bhagat Singh Nagar": ["Nawanshahr"], "Tarn Taran": [],
}

HIMACHAL_DISTRICTS: dict[str, list[str]] = {
    "Bilaspur": [], "Chamba": ["Dalhousie"], "Hamirpur": [], "Kangra": ["Dharamshala", "Dharamsala", "Palampur"],
    "Kinnaur": [], "Kullu": ["Manali"], "Lahaul and Spiti": ["Keylong"], "Mandi": ["Sundernagar"],
    "Shimla": [], "Sirmaur": ["Nahan", "Paonta Sahib"], "Solan": ["Baddi", "Parwanoo", "Kasauli"], "Una": [],
}


def _build_index() -> list[tuple[re.Pattern[str], str, str, State]]:
    index = []
    for districts, state in ((PUNJAB_DISTRICTS, State.PUNJAB), (HIMACHAL_DISTRICTS, State.HIMACHAL_PRADESH)):
        for district, towns in districts.items():
            for place in [district, *towns]:
                index.append((re.compile(rf"\b{re.escape(place)}\b", re.I), place, district, state))
    index.append((re.compile(r"\bChandigarh\b", re.I), "Chandigarh", "Chandigarh", State.CHANDIGARH))
    # Prefer longer (more specific) names first, e.g. "Sri Muktsar Sahib" over "Muktsar".
    index.sort(key=lambda t: -len(t[1]))
    return index


_INDEX = _build_index()
_STATE_NAMES = [
    # "HP" is matched case-sensitively to avoid false hits on words like "hp" (horsepower).
    (re.compile(r"(?i:\bhimachal\b)|\bH\.P\.|\bHP\b"), State.HIMACHAL_PRADESH),
    (re.compile(r"\bpunjab\b", re.I), State.PUNJAB),
]


# Places outside the target region. A match means "explicitly elsewhere", which
# stops the extractor from falling back to the page's location.
_ELSEWHERE = re.compile(
    r"\b(Delhi|New Delhi|Gurugram|Gurgaon|Noida|Faridabad|Mumbai|Pune|Bengaluru|Bangalore|Chennai|Hyderabad|"
    r"Kolkata|Ahmedabad|Jaipur|Lucknow|Dehradun|Jammu|Srinagar|Panchkula|Ambala|Karnal|"
    r"Haryana|Rajasthan|Uttarakhand|Uttar Pradesh|Maharashtra|Karnataka|Gujarat|Tamil Nadu|Jammu and Kashmir)\b",
    re.I,
)


def locate(text: str) -> tuple[str | None, str | None, State]:
    """Return (city, district, state) for the first known place mentioned in `text`."""
    for pattern, place, district, state in _INDEX:
        if pattern.search(text):
            return place, district, state
    for pattern, state in _STATE_NAMES:
        if pattern.search(text):
            return None, None, state
    if m := _ELSEWHERE.search(text):
        return m.group(0), None, State.OTHER
    return None, None, State.OTHER
