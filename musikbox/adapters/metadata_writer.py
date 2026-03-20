from pathlib import Path

from musikbox.domain.exceptions import MetadataWriteError, UnsupportedFormatError
from musikbox.domain.models import AnalysisResult
from musikbox.domain.ports.metadata_writer import MetadataWriter


class MutagenMetadataWriter(MetadataWriter):
    """Writes analysis results as metadata tags using mutagen."""

    def write(self, file_path: Path, analysis: AnalysisResult) -> None:
        suffix = file_path.suffix.lower()
        try:
            if suffix == ".mp3":
                self._write_mp3(file_path, analysis)
            elif suffix == ".flac":
                self._write_flac(file_path, analysis)
            elif suffix == ".ogg":
                self._write_ogg(file_path, analysis)
            elif suffix == ".wav":
                self._write_wav(file_path, analysis)
            else:
                raise UnsupportedFormatError(f"Unsupported format: {suffix}")
        except (UnsupportedFormatError, MetadataWriteError):
            raise
        except Exception as e:
            raise MetadataWriteError(f"Failed to write metadata to {file_path}: {e}") from e

    def _write_mp3(self, file_path: Path, analysis: AnalysisResult) -> None:
        from mutagen.id3 import ID3, TBPM, TCON, TKEY, ID3NoHeaderError

        try:
            tags = ID3(file_path)
        except ID3NoHeaderError:
            tags = ID3()

        tags.add(TBPM(encoding=3, text=[str(int(round(analysis.bpm)))]))
        tags.add(TKEY(encoding=3, text=[analysis.key]))
        tags.add(TCON(encoding=3, text=[analysis.genre]))

        tags.save(file_path)

    def _write_flac(self, file_path: Path, analysis: AnalysisResult) -> None:
        from mutagen.flac import FLAC

        audio = FLAC(file_path)
        audio["BPM"] = str(int(round(analysis.bpm)))
        audio["INITIALKEY"] = analysis.key
        audio["GENRE"] = analysis.genre
        audio["MOOD"] = analysis.mood
        audio["CAMELOT_KEY"] = analysis.key_camelot
        audio.save()

    def _write_ogg(self, file_path: Path, analysis: AnalysisResult) -> None:
        from mutagen.oggvorbis import OggVorbis

        audio = OggVorbis(file_path)
        audio["BPM"] = str(int(round(analysis.bpm)))
        audio["INITIALKEY"] = analysis.key
        audio["GENRE"] = analysis.genre
        audio["MOOD"] = analysis.mood
        audio["CAMELOT_KEY"] = analysis.key_camelot
        audio.save()

    def _write_wav(self, file_path: Path, analysis: AnalysisResult) -> None:
        """Write metadata to WAV files.

        WAV metadata support via mutagen is limited. We attempt to use
        mutagen's wave module but skip gracefully if unsupported.
        """
        try:
            from mutagen.wave import WAVE

            audio = WAVE(file_path)
            if audio.tags is None:

                audio.add_tags()
                if audio.tags is None:
                    return

            from mutagen.id3 import TBPM, TCON, TKEY

            audio.tags.add(TBPM(encoding=3, text=[str(int(round(analysis.bpm)))]))
            audio.tags.add(TKEY(encoding=3, text=[analysis.key]))
            audio.tags.add(TCON(encoding=3, text=[analysis.genre]))
            audio.save()
        except Exception:
            # WAV metadata support is limited; skip gracefully
            pass
