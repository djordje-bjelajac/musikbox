import glob as globmod
from pathlib import Path

import yt_dlp

from musikbox.domain.exceptions import DownloadError
from musikbox.domain.ports.downloader import Downloader


class YtdlpDownloader(Downloader):
    """Downloads audio from URLs using yt-dlp."""

    def __init__(self, audio_quality: str = "best") -> None:
        self._audio_quality = audio_quality

    def download(self, url: str, output_dir: Path, format: str) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        output_template = str(output_dir / "%(title)s.%(ext)s")

        ydl_opts: dict[str, object] = {
            "format": "bestaudio/best",
            "extract_audio": True,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": format,
                    "preferredquality": self._audio_quality,
                }
            ],
            "outtmpl": output_template,
            "quiet": True,
            "no_warnings": True,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
        except yt_dlp.utils.DownloadError as e:
            raise DownloadError(f"Failed to download {url}: {e}") from e

        if info is None:
            raise DownloadError(f"Failed to download {url}: no info returned")

        # yt-dlp may name the file differently than expected after post-processing.
        # Try the expected path first, then fall back to globbing.
        title = info.get("title", "unknown")
        expected_path = output_dir / f"{title}.{format}"
        if expected_path.exists():
            return expected_path

        # Glob for any file matching the title with any extension
        pattern = str(output_dir / f"{globmod.escape(title)}.*")
        matches = globmod.glob(pattern)
        if matches:
            return Path(matches[0])

        # Last resort: find the most recently modified file in the output dir
        files = sorted(output_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
        for f in files:
            if f.is_file():
                return f

        raise DownloadError(f"Download succeeded but output file not found for {url}")
