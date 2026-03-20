from pathlib import Path

from musikbox.adapters.fake_analyzer import FakeAnalyzer
from musikbox.domain.models import AnalysisResult
from musikbox.domain.ports.analyzer import Analyzer


def test_fake_analyzer_returns_analysis_result() -> None:
    analyzer = FakeAnalyzer()
    result = analyzer.analyze(Path("/tmp/test.mp3"))
    assert isinstance(result, AnalysisResult)


def test_fake_analyzer_default_values() -> None:
    analyzer = FakeAnalyzer()
    result = analyzer.analyze(Path("/tmp/test.mp3"))
    assert result.bpm == 120.0
    assert result.key == "Am"
    assert result.key_camelot == "8A"
    assert result.genre == "Electronic"
    assert result.mood == "Energetic"
    assert result.confidence == {"bpm": 0.9, "key": 0.9, "genre": 0.9, "mood": 0.9}


def test_fake_analyzer_custom_values() -> None:
    analyzer = FakeAnalyzer(bpm=140.0, key="Cm", genre="Techno")
    result = analyzer.analyze(Path("/tmp/test.mp3"))
    assert result.bpm == 140.0
    assert result.key == "Cm"
    assert result.genre == "Techno"
    # Non-overridden values keep defaults
    assert result.key_camelot == "8A"
    assert result.mood == "Energetic"


def test_fake_analyzer_implements_analyzer_port() -> None:
    analyzer = FakeAnalyzer()
    assert isinstance(analyzer, Analyzer)
