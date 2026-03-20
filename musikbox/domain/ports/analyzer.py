from abc import ABC, abstractmethod
from pathlib import Path

from musikbox.domain.models import AnalysisResult


class Analyzer(ABC):
    @abstractmethod
    def analyze(self, file_path: Path) -> AnalysisResult: ...
