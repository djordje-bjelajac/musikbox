from pathlib import Path

from musikbox.domain.exceptions import AnalysisError
from musikbox.domain.models import AnalysisResult
from musikbox.domain.ports.analyzer import Analyzer

# Camelot wheel mapping
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

# Chroma index to pitch class
_CHROMA_TO_KEY = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# Key profile templates (Krumhansl-Schmuckler)
_MAJOR_PROFILE = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
_MINOR_PROFILE = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]


class LibrosaAnalyzer(Analyzer):
    """Analyzer implementation using librosa for BPM and key detection."""

    def analyze(self, file_path: Path) -> AnalysisResult:
        try:
            import librosa
            import numpy as np
        except ImportError:
            raise AnalysisError("librosa not installed. Install with: uv pip install librosa")

        try:
            y, sr = librosa.load(str(file_path), sr=None, mono=True)

            bpm, bpm_confidence = self._detect_bpm(librosa, y, sr)
            key, scale, camelot, key_confidence = self._detect_key(librosa, np, y, sr)
            key_str = f"{key}{scale[0].lower()}" if scale else key

            return AnalysisResult(
                bpm=bpm,
                key=key_str,
                key_camelot=camelot,
                genre="Unknown",
                mood="Unknown",
                confidence={
                    "bpm": bpm_confidence,
                    "key": key_confidence,
                    "genre": 0.0,
                    "mood": 0.0,
                },
            )
        except AnalysisError:
            raise
        except Exception as e:
            raise AnalysisError(f"Analysis failed for {file_path}: {e}") from e

    def _detect_bpm(self, librosa: object, y: object, sr: int) -> tuple[float, float]:
        tempo, beats = librosa.beat.beat_track(y=y, sr=sr)
        bpm = float(tempo[0]) if hasattr(tempo, "__len__") else float(tempo)

        # Confidence based on beat regularity
        if hasattr(beats, "__len__") and len(beats) > 1:
            import numpy as np

            beat_times = librosa.frames_to_time(beats, sr=sr)
            intervals = np.diff(beat_times)
            if len(intervals) > 0:
                cv = float(np.std(intervals) / np.mean(intervals))
                confidence = max(0.0, min(1.0, 1.0 - cv))
            else:
                confidence = 0.3
        else:
            confidence = 0.3

        return round(bpm, 1), confidence

    def _detect_key(
        self, librosa: object, np: object, y: object, sr: int
    ) -> tuple[str, str, str, float]:
        chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
        chroma_avg = np.mean(chroma, axis=1)

        best_corr = -1.0
        best_key = "C"
        best_scale = "major"

        for i in range(12):
            major_rotated = np.roll(_MAJOR_PROFILE, i)
            minor_rotated = np.roll(_MINOR_PROFILE, i)

            major_corr = float(np.corrcoef(chroma_avg, major_rotated)[0, 1])
            minor_corr = float(np.corrcoef(chroma_avg, minor_rotated)[0, 1])

            if major_corr > best_corr:
                best_corr = major_corr
                best_key = _CHROMA_TO_KEY[i]
                best_scale = "major"

            if minor_corr > best_corr:
                best_corr = minor_corr
                best_key = _CHROMA_TO_KEY[i]
                best_scale = "minor"

        camelot = _CAMELOT_MAP.get((best_key, best_scale), "?")
        confidence = max(0.0, min(1.0, best_corr))

        return best_key, best_scale, camelot, confidence
