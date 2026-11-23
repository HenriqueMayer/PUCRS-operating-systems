"""Extração local de PDFs, preservando texto por página e evidência visual.

Também define os limites de recurso e os estados de falha por fonte usados pelos
demais helpers. Uma falha registrada não é omissão: o manifesto guarda estado e motivo.
"""
from __future__ import annotations

import contextlib
import dataclasses
import functools
import hashlib
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import warnings

import pypdf
from pypdf import PdfReader
from pypdf import errors as pypdf_errors

PDF_EXTRACTION_VERSION = 4
DEFAULT_TIMEOUT_SECONDS = 600
DEFAULT_MAX_IMAGE_PIXELS = 89_478_485  # Valor padrão do Pillow; acima dele a imagem vira falha registrada.
HASH_CHUNK_BYTES = 1024 * 1024
# Limites explícitos de pypdf.Configuration (API de 6.18+). Valores iguais aos padrões da 6.21.
PYPDF_LIMITS = {
    "maximum_declared_stream_length": 75_000_000,
    "zlib_maximum_output_length": 75_000_000,
    "lzw_maximum_output_length": 75_000_000,
    "run_length_maximum_output_length": 75_000_000,
    "jbig2_maximum_output_length": 75_000_000,
    "brotli_maximum_output_length": 75_000_000,
    "image_maximum_buffer_size": 75_000_000,
    "stream_decoding_work_maximum_length": 300_000_000,
}
IMAGE_FORMATS = {".png": ("PNG",), ".jpg": ("JPEG",), ".jpeg": ("JPEG",), ".gif": ("GIF",),
                 ".webp": ("WEBP",), ".tif": ("TIFF",), ".tiff": ("TIFF",), ".jp2": ("JPEG2000",)}

STATUS_OK = "extraído"
STATUS_UNSUPPORTED = "formato sem adaptador"
STATUS_UNREADABLE = "ilegível"
STATUS_NOT_UTF8 = "não UTF-8"
STATUS_MALFORMED = "malformado"
STATUS_ENCRYPTED = "criptografado"
STATUS_LIMIT = "limite de recurso"
STATUS_LINK = "link não seguido"
STATUS_EXCLUDED = "excluído"


class SourceFailure(Exception):
    """Falha de uma fonte; o lote registra estado e motivo e continua com as demais."""

    def __init__(self, status: str, reason: str):
        super().__init__(reason)
        self.status = status
        self.reason = reason


def _positive_env(name: str, default: int) -> int:
    value = os.environ.get(name, "").strip()
    if not value:
        return default
    try:
        number = int(value)
    except ValueError as exc:
        raise ValueError(f"{name} deve ser um inteiro positivo.") from exc
    if number < 1:
        raise ValueError(f"{name} deve ser um inteiro positivo.")
    return number


def timeout_seconds() -> int:
    return _positive_env("CONTENT_EXTRACT_TIMEOUT", DEFAULT_TIMEOUT_SECONDS)


def max_image_pixels() -> int:
    return _positive_env("CONTENT_EXTRACT_MAX_IMAGE_PIXELS", DEFAULT_MAX_IMAGE_PIXELS)


def image_formats(path) -> tuple[str, ...] | None:
    """Formato Pillow esperado pela extensão; None quando a extensão não define um formato."""
    return IMAGE_FORMATS.get(Path(path).suffix.lower())


def limit_errors() -> tuple[type[BaseException], ...]:
    from PIL import Image
    errors = [Image.DecompressionBombError, Image.DecompressionBombWarning]
    limit = getattr(pypdf_errors, "LimitReachedError", None)
    if limit is not None:
        errors.append(limit)
    return tuple(errors)


@contextlib.contextmanager
def resource_limits():
    """Aplica os limites do pypdf e do Pillow; bombas de descompressão viram exceções."""
    from PIL import Image
    apply = getattr(pypdf, "apply_configuration", None)
    configuration = getattr(pypdf, "Configuration", None)
    if apply is not None and configuration is not None:
        fields = {field.name for field in dataclasses.fields(configuration)}
        pypdf_context = apply(**{key: value for key, value in PYPDF_LIMITS.items() if key in fields})
    else:
        pypdf_context = contextlib.nullcontext()
    previous = Image.MAX_IMAGE_PIXELS
    with pypdf_context, warnings.catch_warnings():
        warnings.simplefilter("error", Image.DecompressionBombWarning)
        Image.MAX_IMAGE_PIXELS = max_image_pixels()
        try:
            yield
        finally:
            Image.MAX_IMAGE_PIXELS = previous


def pdf_tool(name: str) -> str:
    """Find the requested tool without changing the user's global PATH."""
    override = os.environ.get(f"CONTENT_EXTRACT_{name.upper()}")
    if override:
        resolved = shutil.which(override)
        if not resolved:
            raise FileNotFoundError(f"Executável configurado não encontrado: {name}")
        return resolved
    found = shutil.which(name)
    if found:
        return found
    if os.name == "nt":
        if name == "pdftotext":
            git = shutil.which("git")
            if git:
                candidate = Path(git).resolve().parent.parent / "mingw64/bin/pdftotext.exe"
                if candidate.is_file():
                    return str(candidate)
        elif name == "pdftoppm":
            candidate = (Path.home() / ".cache/codex-runtimes/codex-primary-runtime"
                         / "dependencies/native/poppler/Library/bin/pdftoppm.exe")
            if candidate.is_file():
                return str(candidate)
    raise FileNotFoundError(f"{name} não encontrado; configure CONTENT_EXTRACT_{name.upper()} ou o PATH do processo.")


def run_tool(name: str, args: list[str], source: Path, **kwargs) -> subprocess.CompletedProcess:
    """Executa pdftotext/pdftoppm com tempo limite. Falhas da fonte viram SourceFailure."""
    seconds = timeout_seconds()
    try:
        completed = subprocess.run([pdf_tool(name), *args], check=True, timeout=seconds,
                                   stderr=subprocess.PIPE, **kwargs)
    except subprocess.TimeoutExpired as exc:
        raise SourceFailure(STATUS_LIMIT, f"{name} excedeu o tempo limite de {seconds} s.") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or b"").decode("utf-8", "replace").replace(str(source), source.name)
        last = next((line.strip() for line in reversed(detail.splitlines()) if line.strip()), "")
        raise SourceFailure(STATUS_MALFORMED, f"{name} terminou com código {exc.returncode}"
                            + (f": {last}" if last else ".")) from exc
    if completed.stderr:
        # Avisos das ferramentas continuam visíveis, como antes da captura.
        sys.stderr.write(completed.stderr.decode("utf-8", "replace"))
    return completed


@functools.cache
def _tool_version(executable: str) -> str:
    try:
        completed = subprocess.run([executable, "-v"], capture_output=True, timeout=min(30, timeout_seconds()))
    except (OSError, subprocess.SubprocessError):
        return "indisponível"
    text = (completed.stdout + completed.stderr).decode("utf-8", "replace")
    return next((line.strip() for line in text.splitlines() if line.strip()), "desconhecida")


def tool_versions(*names: str) -> dict:
    """Versões das bibliotecas e das ferramentas externas usadas nesta execução."""
    import PIL
    versions = {"python": platform.python_version(), "pypdf": pypdf.__version__, "Pillow": PIL.__version__}
    for name in names:
        try:
            versions[name] = _tool_version(pdf_tool(name))
        except FileNotFoundError:
            versions[name] = "indisponível"
    return versions


def pdf_text(source: Path) -> str:
    completed = run_tool("pdftotext", ["-layout", "-enc", "UTF-8", str(source), "-"], source,
                         stdout=subprocess.PIPE)
    # Mesmo resultado do modo texto anterior: UTF-8 estrito e quebras de linha universais.
    return completed.stdout.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(HASH_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resource_key(resource):
    return list(resource) if isinstance(resource, (tuple, list)) else resource


def image_error(exc: BaseException) -> tuple[str, str]:
    if isinstance(exc, limit_errors()):
        return STATUS_LIMIT, f"{type(exc).__name__}: {exc}"
    return STATUS_MALFORMED, f"{type(exc).__name__}: {exc}"


def pdf_image_items(page) -> list:
    """Return (resource, image, error) per unique resource; error is (status, reason) or None.

    pypdf can repeat an inline resource ID when traversing nested forms. Call inside
    resource_limits(). A failed resource keeps its numeric position, so file names stay stable.
    """
    try:
        images = page.images
        keys = list(images.keys())
    except Exception as exc:  # A falha de listagem é registrada para a página inteira.
        return [(None, None, image_error(exc))]
    items, seen = [], set()
    for resource in keys:
        key = tuple(resource) if isinstance(resource, (tuple, list)) else resource
        if key in seen:
            continue
        seen.add(key)
        try:
            image = images[resource]
            if image.image is None:
                raise ValueError("pypdf não decodificou a imagem")
            image.image.width, image.image.height
        except Exception as exc:
            items.append((resource, None, image_error(exc)))
        else:
            items.append((resource, image, None))
    return items


def embedded_filename(number: int, index: int, image) -> str:
    return f"imagens/pagina-{number:03d}-imagem-{index:03d}{Path(image.name).suffix.lower()}"


def extract_pdf(source: Path, asset_dir: Path) -> dict:
    with resource_limits():
        try:
            reader = PdfReader(source)
            encrypted = reader.is_encrypted
            page_count = 0 if encrypted else len(reader.pages)
        except limit_errors() as exc:
            raise SourceFailure(STATUS_LIMIT, f"Limite atingido ao abrir o PDF: {type(exc).__name__}: {exc}") from exc
        except OSError as exc:
            raise SourceFailure(STATUS_UNREADABLE, f"Leitura impossível: {exc.strerror or type(exc).__name__}.") from exc
        except Exception as exc:
            raise SourceFailure(STATUS_MALFORMED, f"pypdf não abriu o PDF: {type(exc).__name__}: {exc}") from exc
        if encrypted:
            raise SourceFailure(STATUS_ENCRYPTED, "PDF criptografado; forneça uma cópia sem proteção ou registre o limite.")
        raw = pdf_text(source)
        texts = raw.split("\f")
        if texts and not texts[-1].strip():
            texts.pop()
        if len(texts) != page_count:
            raise SourceFailure(STATUS_MALFORMED, f"Contagem de páginas divergente: pdftotext {len(texts)}, pypdf {page_count}.")
        asset_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="content-extract-pdf-") as tmp:
            prefix = Path(tmp) / "pagina"
            run_tool("pdftoppm", ["-png", "-scale-to", "1600", str(source), str(prefix)], source,
                     stdout=subprocess.DEVNULL)
            rendered = sorted(Path(tmp).glob("pagina-*.png"))
            if len(rendered) != len(texts):
                raise SourceFailure(STATUS_MALFORMED, f"Renderização incompleta: {len(rendered)} de {len(texts)} páginas.")
            for number, path in enumerate(rendered, 1):
                target = asset_dir / f"pagina-{number:03d}.png"
                content = path.read_bytes()
                if not target.exists() or target.read_bytes() != content:
                    target.write_bytes(content)
        pages = []
        for number, text in enumerate(texts, 1):
            try:
                page = reader.pages[number - 1]
            except Exception as exc:
                raise SourceFailure(STATUS_MALFORMED, f"pypdf não leu a página {number}: {type(exc).__name__}: {exc}") from exc
            embedded, failures = [], []
            for index, (resource, image, error) in enumerate(pdf_image_items(page), 1):
                if error is not None:
                    failures.append({"index": index, "resource": resource_key(resource),
                                     "status": error[0], "reason": error[1]})
                    continue
                filename = embedded_filename(number, index, image)
                target = asset_dir / filename
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.exists() or target.read_bytes() != image.data:
                    target.write_bytes(image.data)
                embedded.append({
                    "file": filename,
                    "resource": resource_key(resource),
                    "name": image.name,
                    "width": image.image.width,
                    "height": image.image.height,
                    "sha256": hashlib.sha256(image.data).hexdigest(),
                })
            record = {
                "number": number,
                "text": text.rstrip(),
                "secondary_text": "",
                "image": f"pagina-{number:03d}.png",
                "text_characters": len(text.strip()),
                "ocr_candidate": not text.strip(),
                "embedded_images": embedded,
                "image_failures": failures,
            }
            try:
                record["secondary_text"] = page.extract_text() or ""
            except Exception as exc:
                record["secondary_text_error"] = f"{type(exc).__name__}: {exc}"
            pages.append(record)
    return {
        "source": source.name,
        "source_sha256": sha256(source),
        "format": "pdf",
        "pdf_extraction_version": PDF_EXTRACTION_VERSION,
        "tools": tool_versions("pdftotext", "pdftoppm"),
        "limits": {"timeout_seconds": timeout_seconds(), "max_image_pixels": max_image_pixels()},
        "pages": pages,
        "stats": {"pages": len(texts), "page_images": len(texts),
                  "embedded_images": sum(len(page["embedded_images"]) for page in pages),
                  "image_failures": sum(len(page["image_failures"]) for page in pages),
                  "ocr_candidates": sum(1 for page in pages if page["ocr_candidate"])},
    }


def contact_sheets(metadata: dict, asset_dir: Path, destination: Path) -> None:
    """Auxílio de revisão; folhas de contato não entram no acervo final."""
    from PIL import Image, ImageDraw
    destination.mkdir(parents=True, exist_ok=True)
    pages = metadata["pages"]
    with resource_limits():
        for start in range(0, len(pages), 4):
            canvas = Image.new("RGB", (1520, 1030), "#ddd")
            draw = ImageDraw.Draw(canvas)
            for pos, page in enumerate(pages[start:start + 4]):
                path = asset_dir / page["image"]
                img = Image.open(path, formats=image_formats(path)).convert("RGB")
                img.thumbnail((748, 472))
                x = (pos % 2) * 760 + 6
                y = (pos // 2) * 515 + 25
                label = page.get("label", f"pagina {page['number']}")
                draw.text((x, y - 21), f"{metadata['source']} - {label}", fill="black")
                canvas.paste(img, (x, y))
            canvas.save(destination / f"contato-{start // 4 + 1:03d}.jpg", quality=94)
