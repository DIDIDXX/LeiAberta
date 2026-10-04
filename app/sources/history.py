"""Common normalized representation of official amendment references."""
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class OfficialRelation:
    source_id: str
    device_ref: str
    relation: str
    event_label: str
    event_url: str
    signed_at: date | None
    publication_date: date | None
    evidence: str
