from abc import ABC, abstractmethod
from pathlib import Path

from musikbox.domain.models import AnalysisResult


class MetadataWriter(ABC):
    @abstractmethod
    def write(self, file_path: Path, analysis: AnalysisResult) -> None: ...
