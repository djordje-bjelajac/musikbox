import json
import sys
from unittest.mock import MagicMock, patch

from musikbox.domain.models import EnrichmentResult
from musikbox.domain.ports.metadata_enricher import MetadataEnricher


def _make_anthropic_response(text: str) -> MagicMock:
    """Build a mock Anthropic message response with the given text content."""
    content_block = MagicMock()
    content_block.text = text
    response = MagicMock()
    response.content = [content_block]
    return response


def _make_enricher() -> tuple[object, MagicMock]:
    """Create a HaikuEnricher with a mocked Anthropic client.

    We inject a fake 'anthropic' module into sys.modules so the lazy
    import inside __init__ resolves to our mock.
    """
    mock_client = MagicMock()
    mock_module = MagicMock()
    mock_module.Anthropic.return_value = mock_client

    with patch.dict(sys.modules, {"anthropic": mock_module}):
        from musikbox.adapters.haiku_enricher import HaikuEnricher

        enricher = HaikuEnricher(api_key="test-key")

    return enricher, mock_client


def test_haiku_enricher_implements_port() -> None:
    enricher, _ = _make_enricher()
    assert isinstance(enricher, MetadataEnricher)


def test_haiku_enricher_parses_valid_json_response() -> None:
    enricher, mock_client = _make_enricher()

    valid_json = json.dumps(
        {
            "artist": "DJ Harvey",
            "title": "Locussolus",
            "album": None,
            "remix": "Locussolus Edit",
            "year": 1987,
            "genre": "dark disco",
            "tags": ["balearic", "cosmic"],
        }
    )
    mock_client.messages.create.return_value = _make_anthropic_response(valid_json)

    result = enricher.enrich("DJ Harvey - Locussolus (Locussolus Edit)", bpm=118.0, key="Am")

    assert isinstance(result, EnrichmentResult)
    assert result.artist == "DJ Harvey"
    assert result.title == "Locussolus"
    assert result.remix == "Locussolus Edit"
    assert result.year == 1987
    assert result.genre == "dark disco"
    assert result.tags == ["balearic", "cosmic"]
    assert result.album is None

    mock_client.messages.create.assert_called_once()


def test_haiku_enricher_handles_malformed_json() -> None:
    enricher, mock_client = _make_enricher()

    mock_client.messages.create.return_value = _make_anthropic_response(
        "This is not JSON at all, sorry!"
    )

    result = enricher.enrich("Some Track")

    assert isinstance(result, EnrichmentResult)
    assert result.artist is None
    assert result.title is None
    assert result.album is None
    assert result.remix is None
    assert result.year is None
    assert result.genre is None
    assert result.tags == []


def test_haiku_enricher_handles_api_error() -> None:
    enricher, mock_client = _make_enricher()

    mock_client.messages.create.side_effect = Exception("API connection failed")

    result = enricher.enrich("Some Track")

    assert isinstance(result, EnrichmentResult)
    assert result.artist is None
    assert result.title is None
    assert result.tags == []
