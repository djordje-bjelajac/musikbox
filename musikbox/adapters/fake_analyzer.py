from pathlib import Path

from musikbox.domain.models import AnalysisResult
from musikbox.domain.ports.analyzer import Analyzer


class FakeAnalyzer(Analyzer):
    """Analyzer implementation that returns hardcoded results.

    Useful for testing and development without Essentia installed.
    """

    def __init__(self, **overrides: float | str | dict[str, float]) -> None:
        self._defaults: dict[str, float | str | dict[str, float]] = {
            "bpm": 120.0,
            "key": "Am",
            "key_camelot": "8A",
            "genre": "Electronic",
            "mood": "Energetic",
            "confidence": {"bpm": 0.9, "key": 0.9, "genre": 0.9, "mood": 0.9},
        }
        self._defaults.update(overrides)

    def analyze(self, file_path: Path) -> AnalysisResult:
        return AnalysisResult(
            bpm=float(self._defaults["bpm"]),
            key=str(self._defaults["key"]),
            key_camelot=str(self._defaults["key_camelot"]),
            genre=str(self._defaults["genre"]),
            mood=str(self._defaults["mood"]),
            confidence=dict(self._defaults["confidence"]),  # type: ignore[arg-type]
        )
