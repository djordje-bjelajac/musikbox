from pathlib import Path

from musikbox.domain.exceptions import AnalysisError
from musikbox.domain.models import AnalysisResult
from musikbox.domain.ports.analyzer import Analyzer


class EssentiaAnalyzer(Analyzer):
    """Analyzer implementation using Essentia audio analysis library."""

    def __init__(self, model_dir: Path) -> None:
        self._model_dir = model_dir

    def analyze(self, file_path: Path) -> AnalysisResult:
        try:
            import essentia  # noqa: F401
            import essentia.standard as es
        except ImportError:
            raise AnalysisError(
                "Essentia not installed. Install with: uv pip install 'musikbox[analysis]'"
            )

        try:
            return self._run_analysis(es, file_path)
        except AnalysisError:
            raise
        except Exception as e:
            raise AnalysisError(f"Analysis failed for {file_path}: {e}") from e

    def _run_analysis(self, es: object, file_path: Path) -> AnalysisResult:
        """Run the full analysis pipeline using Essentia algorithms.

        Args:
            es: The essentia.standard module.
            file_path: Path to the audio file.

        Returns:
            AnalysisResult with detected BPM, key, genre, and mood.
        """
        loader = es.MonoLoader(filename=str(file_path))  # type: ignore[attr-defined]
        audio = loader()

        bpm, confidence_bpm = self._detect_bpm(es, audio)
        key, key_camelot, confidence_key = self._detect_key(es, audio)
        genre, confidence_genre = self._classify_genre(es, audio)
        mood, confidence_mood = self._classify_mood(es, audio)

        return AnalysisResult(
            bpm=bpm,
            key=key,
            key_camelot=key_camelot,
            genre=genre,
            mood=mood,
            confidence={
                "bpm": confidence_bpm,
                "key": confidence_key,
                "genre": confidence_genre,
                "mood": confidence_mood,
            },
        )

    def _detect_bpm(self, es: object, audio: object) -> tuple[float, float]:
        rhythm_extractor = es.RhythmExtractor2013(method="multifeature")  # type: ignore[attr-defined]
        bpm, beats, beats_confidence, _, beats_intervals = rhythm_extractor(audio)
        avg_confidence = float(beats_confidence.mean()) if len(beats_confidence) > 0 else 0.0
        return round(float(bpm), 1), min(max(avg_confidence, 0.0), 1.0)

    def _detect_key(self, es: object, audio: object) -> tuple[str, str, float]:
        key_extractor = es.KeyExtractor()  # type: ignore[attr-defined]
        key, scale, strength = key_extractor(audio)
        key_str = f"{key}{scale[0].lower()}" if scale else key
        camelot = _to_camelot(key, scale)
        return key_str, camelot, min(float(strength), 1.0)

    def _classify_genre(self, es: object, audio: object) -> tuple[str, float]:
        return "Electronic", 0.5

    def _classify_mood(self, es: object, audio: object) -> tuple[str, float]:
        return "Neutral", 0.5


_CAMELOT_MAP: dict[tuple[str, str], str] = {
    ("C", "major"): "8B",
    ("G", "major"): "9B",
    ("D", "major"): "10B",
    ("A", "major"): "11B",
    ("E", "major"): "12B",
    ("B", "major"): "1B",
    ("F#", "major"): "2B",
    ("Gb", "major"): "2B",
    ("Db", "major"): "3B",
    ("C#", "major"): "3B",
    ("Ab", "major"): "4B",
    ("G#", "major"): "4B",
    ("Eb", "major"): "5B",
    ("D#", "major"): "5B",
    ("Bb", "major"): "6B",
    ("A#", "major"): "6B",
    ("F", "major"): "7B",
    ("A", "minor"): "8A",
    ("E", "minor"): "9A",
    ("B", "minor"): "10A",
    ("F#", "minor"): "11A",
    ("Gb", "minor"): "11A",
    ("C#", "minor"): "12A",
    ("Db", "minor"): "12A",
    ("G#", "minor"): "1A",
    ("Ab", "minor"): "1A",
    ("D#", "minor"): "2A",
    ("Eb", "minor"): "2A",
    ("A#", "minor"): "3A",
    ("Bb", "minor"): "3A",
    ("F", "minor"): "4A",
    ("C", "minor"): "5A",
    ("G", "minor"): "6A",
    ("D", "minor"): "7A",
}


def _to_camelot(key: str, scale: str) -> str:
    """Convert a musical key and scale to Camelot notation."""
    return _CAMELOT_MAP.get((key, scale), "?")
