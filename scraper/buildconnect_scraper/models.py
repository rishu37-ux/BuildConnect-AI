from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum


class Profession(str, Enum):
    ARCHITECT = "architect"
    STRUCTURAL_ENGINEER = "structural_engineer"
    CONTRACTOR = "contractor"
    OTHER = "other"


class State(str, Enum):
    PUNJAB = "punjab"
    HIMACHAL_PRADESH = "himachal_pradesh"
    CHANDIGARH = "chandigarh"
    OTHER = "other"


@dataclass
class Lead:
    full_name: str
    source_url: str
    phone: str | None = None
    email: str | None = None
    firm_name: str | None = None
    profession: Profession = Profession.OTHER
    city: str | None = None
    district: str | None = None
    state: State = State.OTHER
    website: str | None = None
    confidence: float = 0.5

    def key(self) -> str:
        return self.phone or self.email or self.full_name

    def to_payload(self) -> dict:
        data = asdict(self)
        data["profession"] = self.profession.value
        data["state"] = self.state.value
        data["confidence"] = round(self.confidence, 3)
        return data


@dataclass
class ScrapeGoal:
    """What the agent is trying to find."""

    professions: set[Profession] = field(
        default_factory=lambda: {Profession.ARCHITECT, Profession.STRUCTURAL_ENGINEER, Profession.CONTRACTOR}
    )
    states: set[State] = field(default_factory=lambda: {State.PUNJAB, State.HIMACHAL_PRADESH})
    max_pages: int = 200
    max_depth: int = 3
    min_confidence: float = 0.4

    def describe(self) -> dict:
        return {
            "professions": sorted(p.value for p in self.professions),
            "states": sorted(s.value for s in self.states),
            "max_pages": self.max_pages,
            "max_depth": self.max_depth,
        }
