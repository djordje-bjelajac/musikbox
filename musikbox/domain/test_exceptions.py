import pytest

from musikbox.domain.exceptions import (
    AnalysisError,
    ConfigError,
    DatabaseError,
    DownloadError,
    MetadataWriteError,
    MusikboxError,
    TrackNotFoundError,
    UnsupportedFormatError,
)

ALL_EXCEPTIONS = [
    TrackNotFoundError,
    DownloadError,
    AnalysisError,
    UnsupportedFormatError,
    ConfigError,
    DatabaseError,
    MetadataWriteError,
]


def test_musikbox_error_inherits_from_exception() -> None:
    assert issubclass(MusikboxError, Exception)


@pytest.mark.parametrize("exc_class", ALL_EXCEPTIONS)
def test_all_exceptions_inherit_from_musikbox_error(
    exc_class: type[MusikboxError],
) -> None:
    assert issubclass(exc_class, MusikboxError)


@pytest.mark.parametrize("exc_class", ALL_EXCEPTIONS)
def test_exception_carries_message(exc_class: type[MusikboxError]) -> None:
    msg = f"test message for {exc_class.__name__}"
    exc = exc_class(msg)
    assert str(exc) == msg


@pytest.mark.parametrize("exc_class", ALL_EXCEPTIONS)
def test_exception_can_be_caught_as_musikbox_error(
    exc_class: type[MusikboxError],
) -> None:
    with pytest.raises(MusikboxError):
        raise exc_class("something went wrong")


def test_musikbox_error_can_be_raised_and_caught() -> None:
    with pytest.raises(MusikboxError, match="base error"):
        raise MusikboxError("base error")
