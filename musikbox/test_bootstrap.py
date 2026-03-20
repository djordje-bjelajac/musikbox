import builtins
from pathlib import Path

import pytest

from musikbox.adapters.fake_analyzer import FakeAnalyzer
from musikbox.bootstrap import App, create_app
from musikbox.services.analysis_service import AnalysisService
from musikbox.services.download_service import DownloadService
from musikbox.services.library_service import LibraryService


def test_create_app_returns_app_with_all_services(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("MUSIKBOX_MUSIC_DIR", str(tmp_path / "music"))
    monkeypatch.setenv("MUSIKBOX_DB_PATH", str(tmp_path / "test.db"))

    app = create_app()

    assert isinstance(app, App)
    assert app.library_service is not None
    assert app.download_service is not None
    assert app.analysis_service is not None
    assert app.config is not None


def test_create_app_services_are_wired_correctly(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("MUSIKBOX_MUSIC_DIR", str(tmp_path / "music"))
    monkeypatch.setenv("MUSIKBOX_DB_PATH", str(tmp_path / "test.db"))

    app = create_app()

    assert isinstance(app.library_service, LibraryService)
    assert isinstance(app.download_service, DownloadService)
    assert isinstance(app.analysis_service, AnalysisService)


def test_create_app_uses_fake_analyzer_when_no_real_analyzer_available(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("MUSIKBOX_MUSIC_DIR", str(tmp_path / "music"))
    monkeypatch.setenv("MUSIKBOX_DB_PATH", str(tmp_path / "test.db"))

    # Block both librosa and essentia so bootstrap falls back to FakeAnalyzer
    real_import = builtins.__import__

    def _block_analyzers(name: str, *args: object, **kwargs: object) -> object:
        if name in ("librosa", "essentia"):
            raise ImportError("blocked for test")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _block_analyzers)

    app = create_app()

    assert isinstance(app.analysis_service._analyzer, FakeAnalyzer)
