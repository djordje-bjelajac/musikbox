from abc import ABC, abstractmethod
from pathlib import Path


class Downloader(ABC):
    @abstractmethod
    def download(self, url: str, output_dir: Path, format: str) -> Path: ...
