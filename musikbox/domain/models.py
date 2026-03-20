from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from uuid import uuid4


@dataclass
class TrackId:
    """Value object - generates UUID on construction."""

    value: str = field(default_factory=lambda: str(uuid4()))


@dataclass
class Track:
    id: TrackId
    title: str
    artist: str | None
    album: str | None
    duration_seconds: float
    file_path: Path
    format: str
    bpm: float | None
    key: str | None
    genre: str | None
    mood: str | None
    source_url: str | None
    downloaded_at: datetime | None
    analyzed_at: datetime | None
    created_at: datetime
    remix: str | None = None
    year: int | None = None
    tags: str | None = None
    enriched_at: datetime | None = None


@dataclass
class EnrichmentResult:
    artist: str | None
    title: str | None
    album: str | None
    remix: str | None
    year: int | None
    genre: str | None
    tags: list[str]


@dataclass
class AnalysisResult:
    bpm: float
    key: str
    key_camelot: str
    genre: str
    mood: str
    confidence: dict[str, float]


@dataclass
class Playlist:
    id: str  # UUID
    name: str
    created_at: datetime
    updated_at: datetime


@dataclass
class SearchFilter:
    bpm_min: float | None = None
    bpm_max: float | None = None
    key: str | None = None
    genre: str | None = None
    mood: str | None = None
    artist: str | None = None
    title: str | None = None
    query: str | None = None
