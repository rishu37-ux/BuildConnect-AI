"""Contact, name, profession and location extraction from HTML."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from urllib.parse import urldefrag, urljoin, urlsplit

from bs4 import BeautifulSoup, Tag

from .geo import locate
from .models import Lead, Profession, State

# --- contacts -----------------------------------------------------------------

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_OBFUSCATIONS = [
    (re.compile(r"\s*[\[({]\s*at\s*[\])}]\s*", re.I), "@"),
    (re.compile(r"\s*[\[({]\s*dot\s*[\])}]\s*", re.I), "."),
]
_EMAIL_JUNK = re.compile(r"\.(png|jpe?g|gif|webp|svg)$|^(noreply|no-reply|donotreply)@|@(example|sentry|wixpress)\.", re.I)
# Indian mobile: optional +91 / 91 / 0 prefix, then 10 digits starting 6-9, with
# common separators (spaces, dots, hyphens) between digit groups.
_MOBILE = re.compile(r"(?<![\d+])(?:(?:\+|00)?91[\s.-]*|0)?([6-9](?:[\s.-]?\d){9})(?!\d)")


def deobfuscate(text: str) -> str:
    for pattern, repl in _OBFUSCATIONS:
        text = pattern.sub(repl, text)
    return text


def find_emails(text: str) -> list[str]:
    found = (m.group(0).strip(".").lower() for m in _EMAIL.finditer(deobfuscate(text)))
    return list(dict.fromkeys(e for e in found if not _EMAIL_JUNK.search(e)))


def normalize_mobile(raw: str) -> str | None:
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    elif len(digits) == 14 and digits.startswith("0091"):
        digits = digits[4:]
    return f"+91{digits}" if re.fullmatch(r"[6-9]\d{9}", digits) else None


def find_mobiles(text: str) -> list[str]:
    out = (normalize_mobile(m.group(0)) for m in _MOBILE.finditer(text))
    return list(dict.fromkeys(p for p in out if p))


def contacts_in(el: Tag) -> tuple[list[str], list[str]]:
    """(mobiles, emails) found in an element's text and its tel:/mailto: links."""
    text = el.get_text(" ", strip=True)
    links = [a.get("href", "") for a in el.find_all("a", href=True)]
    if el.name == "a" and el.get("href"):
        links.append(el["href"])
    tel = " ".join(h[4:] for h in links if h.lower().startswith("tel:"))
    mail = " ".join(h[7:].split("?")[0] for h in links if h.lower().startswith("mailto:"))
    return find_mobiles(f"{text} {tel}"), find_emails(f"{text} {mail}")


# --- classification -------------------------------------------------------------

_PROFESSION_KEYWORDS: dict[Profession, list[tuple[re.Pattern[str], float]]] = {
    Profession.ARCHITECT: [
        (re.compile(r"\barchitect(s|ure|ural)?\b", re.I), 2.0),
        (re.compile(r"\bAr\.\s?[A-Z]"), 2.5),
        (re.compile(r"\bCOA\b|council of architecture|\bIIA\b", re.I), 1.5),
        (re.compile(r"\binterior design(er)?s?\b|\burban design", re.I), 0.5),
    ],
    Profession.STRUCTURAL_ENGINEER: [
        (re.compile(r"\bstructural\s+(engineer|consultant|design|engineering)", re.I), 3.0),
        (re.compile(r"\bstructural\b", re.I), 1.0),
        (re.compile(r"\bcivil\s+engineer", re.I), 1.5),
        (re.compile(r"\bEr\.\s?[A-Z]"), 1.0),
        (re.compile(r"\bM\.?\s?Tech\b.*\bstructur", re.I), 1.5),
    ],
    Profession.CONTRACTOR: [
        (re.compile(r"\bcontractors?\b", re.I), 2.5),
        (re.compile(r"\bbuilders?\b|\bconstructions?\b|\bdevelopers?\b", re.I), 1.5),
        (re.compile(r"\bcivil works\b|\bturnkey\b|\bthekedar\b|\bPWD\b", re.I), 1.0),
    ],
}


def classify_profession(text: str) -> tuple[Profession, float]:
    """Best-matching profession and a 0..1 strength score."""
    scores = {
        prof: sum(weight for pattern, weight in patterns if pattern.search(text))
        for prof, patterns in _PROFESSION_KEYWORDS.items()
    }
    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return Profession.OTHER, 0.0
    return best, min(scores[best] / 3.0, 1.0)


# --- names ----------------------------------------------------------------------

_HONORIFIC = re.compile(r"^(Ar|Er|Dr|Mr|Mrs|Ms|Shri|Smt|Sh|S|Sardar)\.?\s+", re.I)
_FIRM_WORDS = re.compile(
    r"\b(associates|architects|consultants?|builders|constructions?|contractors|developers|engineers|"
    r"infra(structure)?|studio|design(s|ers)?|group|pvt|private|ltd|limited|llp|co\.|company|enterprises|"
    r"&|and sons)\b",
    re.I,
)
_GENERIC_HEADINGS = re.compile(
    r"^(contact( us| details| info(rmation)?)?|get in touch|address|phone|email|mobile|call us|"
    r"our team|team|about( us)?|home|menu|search|enquiry|enquire now|follow us|location)$",
    re.I,
)
_PERSON_NAME = re.compile(r"^[A-Z][a-zA-Z'’-]+(\s+[A-Z][a-zA-Z'’.-]*){1,3}$")


def clean_name(raw: str | None) -> str | None:
    if not raw:
        return None
    name = " ".join(raw.split()).strip(" :-|,•")
    if not (2 < len(name) <= 100) or re.search(r"\d|@|https?:", name) or _GENERIC_HEADINGS.match(name):
        return None
    return name


def looks_like_person(name: str) -> bool:
    if _HONORIFIC.match(name):
        return True
    return bool(_PERSON_NAME.match(name)) and not _FIRM_WORDS.search(name)


def looks_like_firm(name: str) -> bool:
    return bool(_FIRM_WORDS.search(name)) and not _HONORIFIC.match(name)


# --- page-level extraction --------------------------------------------------------

_NAME_SELECTORS = (
    "[itemprop=name], .name, .member-name, .profile-name, .title, h1, h2, h3, h4, h5, h6, strong, b"
)


@dataclass
class PageContext:
    url: str
    title: str = ""
    text_head: str = ""  # title + top headings, used as fallback context
    profession: Profession = Profession.OTHER
    profession_strength: float = 0.0
    location: tuple[str | None, str | None, State] = (None, None, State.OTHER)
    links: list[tuple[str, str]] = field(default_factory=list)


def parse(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


def page_context(soup: BeautifulSoup, url: str) -> PageContext:
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    headings = " ".join(h.get_text(" ", strip=True) for h in soup.find_all(["h1", "h2"], limit=5))
    meta = soup.find("meta", attrs={"name": "description"})
    head = f"{title} {headings} {meta.get('content', '') if meta else ''}"
    prof, strength = classify_profession(head)
    return PageContext(
        url=url, title=title, text_head=head, profession=prof, profession_strength=strength,
        location=locate(head), links=extract_links(soup, url),
    )


def extract_links(soup: BeautifulSoup, base_url: str) -> list[tuple[str, str]]:
    out: dict[str, str] = {}
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith(("mailto:", "tel:", "javascript:", "#", "whatsapp:")):
            continue
        absolute, _ = urldefrag(urljoin(base_url, href))
        if urlsplit(absolute).scheme in ("http", "https"):
            out.setdefault(absolute, " ".join(a.get_text(" ", strip=True).split())[:200])
    return list(out.items())


def _jsonld_items(soup: BeautifulSoup):
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            item = stack.pop()
            if isinstance(item, dict):
                if "@graph" in item:
                    stack.extend(item["@graph"])
                yield item


_JSONLD_TYPES = {"person", "localbusiness", "organization", "professionalservice", "generalcontractor",
                 "homeandconstructionbusiness", "architect"}


def extract_jsonld(soup: BeautifulSoup, ctx: PageContext) -> list[Lead]:
    leads = []
    for item in _jsonld_items(soup):
        types = item.get("@type", [])
        types = {t.lower() for t in (types if isinstance(types, list) else [types]) if isinstance(t, str)}
        if not types & _JSONLD_TYPES:
            continue
        name = clean_name(item.get("name"))
        phones = find_mobiles(str(item.get("telephone", "")))
        emails = find_emails(str(item.get("email", "")).removeprefix("mailto:"))
        if not name or not (phones or emails):
            continue
        addr = item.get("address") if isinstance(item.get("address"), dict) else {}
        loc_text = " ".join(str(addr.get(k, "")) for k in ("addressLocality", "addressRegion", "streetAddress"))
        blob = f"{name} {item.get('description', '')} {item.get('jobTitle', '')} {' '.join(types)}"
        leads.append(_build_lead(ctx, name, phones, emails, blob, loc_text, structured=True,
                                 website=item.get("url") if isinstance(item.get("url"), str) else None))
    return leads


def _contact_container(el: Tag, max_levels: int = 6) -> Tag:
    """Climb from a contact element to the smallest ancestor that also holds a name."""
    node = el
    for _ in range(max_levels):
        parent = node.parent
        if parent is None or parent.name in ("body", "html", "[document]"):
            break
        mobiles, emails = contacts_in(parent)
        if len(set(mobiles)) + len(set(emails)) > 3:
            break  # we've reached a list of several people; stay at the card level
        node = parent
        if node.select_one(_NAME_SELECTORS):
            break
    return node


def _name_in(container: Tag) -> str | None:
    for el in container.select(_NAME_SELECTORS):
        name = clean_name(el.get_text(" ", strip=True))
        if name:
            return name
    return None


def extract_cards(soup: BeautifulSoup, ctx: PageContext) -> list[Lead]:
    """Find directory-style "cards": a block with a name and a mobile/email."""
    root = soup.body or soup
    seen_containers: list[Tag] = []
    for el in root.find_all(string=lambda s: bool(_MOBILE.search(s) or _EMAIL.search(deobfuscate(s)))):
        if el.parent and el.parent.name not in ("script", "style", "noscript"):
            seen_containers.append(_contact_container(el.parent))
    for a in root.find_all("a", href=re.compile(r"^(tel|mailto):", re.I)):
        seen_containers.append(_contact_container(a))

    leads, used = [], set()
    for container in seen_containers:
        if id(container) in used:
            continue
        used.add(id(container))
        mobiles, emails = contacts_in(container)
        name = _name_in(container)
        if not name or not (mobiles or emails):
            continue
        text = container.get_text(" ", strip=True)
        leads.append(_build_lead(ctx, name, mobiles, emails, text, text, structured=False))
    return leads


def _build_lead(ctx: PageContext, name: str, mobiles: list[str], emails: list[str], blob: str,
                loc_text: str, structured: bool, website: str | None = None) -> Lead:
    profession, strength = classify_profession(blob)
    if profession is Profession.OTHER and ctx.profession is not Profession.OTHER:
        profession, strength = ctx.profession, ctx.profession_strength * 0.6
    city, district, state = locate(loc_text)
    if state is State.OTHER and city is None:  # block names no place at all
        city, district, state = ctx.location

    firm = None
    full_name = name
    if looks_like_firm(name):
        firm = name
        person = next((ln for ln in re.split(r"[\n|•,]", blob) if looks_like_person(ln.strip())
                       and clean_name(ln.strip())), None)
        if person:
            full_name = clean_name(person.strip())

    confidence = 0.25
    confidence += 0.2 if looks_like_person(full_name) else 0.05
    confidence += 0.25 * strength
    confidence += 0.15 if state is not State.OTHER else 0.0
    confidence += 0.1 if structured else 0.0
    confidence += 0.05 if mobiles and emails else 0.0

    return Lead(
        full_name=full_name, firm_name=firm, phone=mobiles[0] if mobiles else None,
        email=emails[0] if emails else None, profession=profession, city=city, district=district,
        state=state, website=website, source_url=ctx.url, confidence=min(confidence, 1.0),
    )


def extract_leads(html: str, url: str) -> tuple[list[Lead], PageContext]:
    soup = parse(html)
    ctx = page_context(soup, url)
    by_key: dict[str, Lead] = {}
    for lead in [*extract_jsonld(soup, ctx), *extract_cards(soup, ctx)]:
        existing = by_key.get(lead.key())
        if existing is None or lead.confidence > existing.confidence:
            by_key[lead.key()] = lead
    return list(by_key.values()), ctx
