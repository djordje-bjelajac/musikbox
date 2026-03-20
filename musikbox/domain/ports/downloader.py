from abc import ABC, abstractmethod
from collections.abc import Iterator
from pathlib import Path


class Downloader(ABC):
    @abstractmethod
    def download(self, url: str, output_dir: Path, format: str) -> Path: ...

    @abstractmethod
    def download_playlist(
        self, url: str, output_dir: Path, format: str
    ) -> Iterator[tuple[Path, str]]:
        """Download all entries in a playlist, yielding (file_path, entry_url) per track."""
        ...
