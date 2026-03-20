from abc import ABC, abstractmethod

from musikbox.domain.models import EnrichmentResult


class MetadataEnricher(ABC):
    @abstractmethod
    def enrich(
        self,
        raw_title: str,
        bpm: float | None = None,
        key: str | None = None,
    ) -> EnrichmentResult: ...
