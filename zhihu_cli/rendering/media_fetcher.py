"""Safe downloading, validation and temporary caching of Zhihu images."""

from __future__ import annotations

import hashlib
import logging
import os
import stat
import tempfile
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from PIL import Image, UnidentifiedImageError

from ..config import get_browser_headers

logger = logging.getLogger(__name__)

MEDIA_CACHE_DIR = Path("/tmp") / f"zhihu-cli-{os.getuid()}" / "media"
MEDIA_CACHE_MAX_BYTES = 10 * 1024 * 1024 * 1024
MEDIA_CACHE_MAX_AGE_SECONDS = 30 * 24 * 60 * 60
MAX_IMAGE_BYTES = 20 * 1024 * 1024
DOWNLOAD_TIMEOUT = (5, 20)
MAX_REDIRECTS = 5
_ALLOWED_IMAGE_DOMAINS = ("zhihu.com", "zhimg.com")
_KNOWN_EXTENSIONS = {".bmp", ".gif", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}
_CONTENT_TYPE_EXTENSIONS = {
    "image/bmp": ".bmp",
    "image/gif": ".gif",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/tiff": ".tiff",
    "image/webp": ".webp",
}


def _url_extension(url: str) -> str:
    suffix = Path(urlparse(url).path).suffix.lower()
    if suffix == ".jpeg":
        return ".jpg"
    return suffix if suffix in _KNOWN_EXTENSIONS else ".jpg"


def is_trusted_image_url(url: str) -> bool:
    """Return whether an image URL is HTTPS and hosted by Zhihu."""
    try:
        parsed = urlparse(url)
        host = (parsed.hostname or "").rstrip(".").lower()
    except ValueError:
        return False
    if parsed.scheme.lower() != "https" or not host:
        return False
    return any(host == domain or host.endswith(f".{domain}") for domain in _ALLOWED_IMAGE_DOMAINS)


class MediaFetcher:
    """Download public Zhihu images without forwarding authentication cookies."""

    def __init__(
        self,
        client=None,
        *,
        session: requests.Session | None = None,
        cache_dir: Path = MEDIA_CACHE_DIR,
    ):
        # ``client`` remains accepted for compatibility, but its authenticated
        # session is deliberately never used for media requests.
        self.client = client
        self.session = session or requests.Session()
        headers = get_browser_headers()
        headers["Accept"] = "image/avif,image/webp,image/apng,image/*,*/*;q=0.8"
        self.session.headers.update(headers)
        self.cache_dir = cache_dir
        self.last_error: str | None = None
        self._cleaned = False

    @staticmethod
    def _cache_key(url: str) -> str:
        return hashlib.sha256(url.strip().encode("utf-8")).hexdigest()

    @staticmethod
    def _formula_cache_key(tex: str, theme: str) -> str:
        return hashlib.sha256(f"{theme}\0{tex}".encode()).hexdigest()

    def fetch_image(self, url: str) -> Path | None:
        self.last_error = None
        if not url:
            self.last_error = "图片地址为空"
            return None
        if not is_trusted_image_url(url):
            self.last_error = "第三方图片，出于安全考虑未加载"
            return None

        try:
            self._ensure_cache_dir()
            if not self._cleaned:
                self._cleanup_cache()
                self._cleaned = True
        except OSError as exc:
            self.last_error = "无法使用图片缓存"
            logger.debug("Media cache unavailable: %s", exc)
            return None

        key = self._cache_key(url)
        for candidate in self.cache_dir.glob(f"{key}.*"):
            if candidate.is_file() and self._validate_image(candidate):
                try:
                    candidate.touch()
                except OSError:
                    pass
                return candidate

        destination = self.cache_dir / f"{key}{_url_extension(url)}"
        downloaded = self._download(url, destination)
        return downloaded if downloaded and self._validate_image(downloaded) else None

    def _download(self, url: str, destination: Path) -> Path | None:
        temp_path: Path | None = None
        try:
            response = self._request_image(url)
            if response is None:
                return None
            with response:
                response.raise_for_status()

                content_type = response.headers.get("Content-Type", "").split(";", 1)[0].lower()
                if not content_type.startswith("image/") or content_type == "image/svg+xml":
                    self.last_error = "响应不是支持的图片格式"
                    return None

                declared_size = response.headers.get("Content-Length")
                if declared_size:
                    try:
                        if int(declared_size) > MAX_IMAGE_BYTES:
                            self.last_error = "图片超过 20 MB，未加载"
                            return None
                    except ValueError:
                        pass

                suffix = _CONTENT_TYPE_EXTENSIONS.get(content_type, destination.suffix)
                final_destination = destination.with_suffix(suffix)
                with tempfile.NamedTemporaryFile(
                    mode="wb",
                    prefix=f".{final_destination.name}.",
                    suffix=".tmp",
                    dir=self.cache_dir,
                    delete=False,
                ) as output:
                    temp_path = Path(output.name)
                    downloaded = 0
                    for chunk in response.iter_content(chunk_size=64 * 1024):
                        if not chunk:
                            continue
                        downloaded += len(chunk)
                        if downloaded > MAX_IMAGE_BYTES:
                            self.last_error = "图片超过 20 MB，未加载"
                            return None
                        output.write(chunk)
                    output.flush()
                    os.fsync(output.fileno())

                if not self._validate_image(temp_path):
                    self.last_error = "下载内容不是有效图片"
                    return None
                os.replace(temp_path, final_destination)
                temp_path = None
                self._cleanup_cache()
                return final_destination
        except (requests.RequestException, OSError) as exc:
            self.last_error = "图片下载失败"
            logger.debug("Image download failed for %s: %s", url, exc)
            return None
        finally:
            if temp_path is not None:
                try:
                    temp_path.unlink(missing_ok=True)
                except OSError:
                    pass

    def _request_image(self, url: str):
        """Follow only redirects that remain on trusted Zhihu hosts."""
        current_url = url
        redirect_codes = {301, 302, 303, 307, 308}
        for _ in range(MAX_REDIRECTS + 1):
            response = self.session.get(
                current_url,
                stream=True,
                timeout=DOWNLOAD_TIMEOUT,
                allow_redirects=False,
            )
            if response.status_code not in redirect_codes:
                return response

            location = response.headers.get("Location", "")
            response.close()
            next_url = urljoin(current_url, location)
            if not is_trusted_image_url(next_url):
                self.last_error = "图片重定向到第三方地址，出于安全考虑未加载"
                return None
            current_url = next_url

        self.last_error = "图片重定向次数过多"
        return None

    @staticmethod
    def _validate_image(path: Path) -> bool:
        try:
            if not path.is_file() or path.stat().st_size > MAX_IMAGE_BYTES:
                return False
            with Image.open(path) as image:
                image.verify()
            return True
        except (OSError, UnidentifiedImageError, ValueError):
            return False

    def _ensure_cache_dir(self):
        parent = self.cache_dir.parent
        parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.cache_dir.mkdir(mode=0o700, exist_ok=True)
        for directory in (parent, self.cache_dir):
            info = directory.lstat()
            if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
                raise OSError(f"Unsafe media cache path: {directory}")
            if info.st_uid != os.getuid():
                raise OSError(f"Media cache is not owned by current user: {directory}")
            directory.chmod(0o700)

    def _cleanup_cache(self):
        now = time.time()
        files: list[tuple[float, int, Path]] = []
        total = 0
        for path in self.cache_dir.iterdir():
            try:
                info = path.lstat()
                if not stat.S_ISREG(info.st_mode):
                    continue
                if now - info.st_mtime > MEDIA_CACHE_MAX_AGE_SECONDS:
                    path.unlink()
                    continue
                files.append((info.st_mtime, info.st_size, path))
                total += info.st_size
            except OSError:
                continue

        if total <= MEDIA_CACHE_MAX_BYTES:
            return
        for _, size, path in sorted(files):
            try:
                path.unlink()
                total -= size
            except OSError:
                continue
            if total <= MEDIA_CACHE_MAX_BYTES:
                break
