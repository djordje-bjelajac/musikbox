from musikbox.adapters.fake_enricher import FakeEnricher
from musikbox.domain.models import EnrichmentResult
from musikbox.domain.ports.metadata_enricher import MetadataEnricher


def test_fake_enricher_implements_port() -> None:
    enricher = FakeEnricher()
    assert isinstance(enricher, MetadataEnricher)


def test_fake_enricher_returns_enrichment_result() -> None:
    enricher = FakeEnricher()
    result = enricher.enrich("DJ Harvey - Locussolus Edit")
    assert isinstance(result, EnrichmentResult)
    assert result.artist is not None
    assert result.title is not None


def test_fake_enricher_result_has_tags() -> None:
    enricher = FakeEnricher()
    result = enricher.enrich("Some Track Title")
    assert isinstance(result.tags, list)
    assert len(result.tags) > 0
