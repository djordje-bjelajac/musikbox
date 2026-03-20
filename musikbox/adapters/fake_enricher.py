from musikbox.domain.models import EnrichmentResult
from musikbox.domain.ports.metadata_enricher import MetadataEnricher


class FakeEnricher(MetadataEnricher):
    """Returns hardcoded results for testing."""

    def enrich(
        self,
        raw_title: str,
        bpm: float | None = None,
        key: str | None = None,
    ) -> EnrichmentResult:
        return EnrichmentResult(
            artist="Test Artist",
            title="Test Title",
            album=None,
            remix=None,
            year=None,
            genre="Electronic",
            tags=["synth", "ambient"],
        )
