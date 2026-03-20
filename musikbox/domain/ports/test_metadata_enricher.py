import pytest

from musikbox.domain.models import EnrichmentResult
from musikbox.domain.ports.metadata_enricher import MetadataEnricher


def test_metadata_enricher_cannot_be_instantiated_directly() -> None:
    with pytest.raises(TypeError):
        MetadataEnricher()  # type: ignore[abstract]


def test_concrete_metadata_enricher_can_be_instantiated() -> None:
    class StubEnricher(MetadataEnricher):
        def enrich(
            self,
            raw_title: str,
            bpm: float | None = None,
            key: str | None = None,
        ) -> EnrichmentResult:
            return EnrichmentResult(
                artist=None,
                title=None,
                album=None,
                remix=None,
                year=None,
                genre=None,
                tags=[],
            )

    enricher = StubEnricher()
    assert isinstance(enricher, MetadataEnricher)
