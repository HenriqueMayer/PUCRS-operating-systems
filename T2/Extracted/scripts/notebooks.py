"""Extract notebook sources and saved outputs without executing any cell.

Only Python's standard library is required. ``asset_url`` is the URL of
``asset_dir`` relative to the Markdown document which consumes ``units``.
Cell numbering is one-based and includes empty cells. Every MIME representation
is retained, even when the same output has both an image and a text fallback.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import posixpath
import re
from urllib.parse import quote, unquote, urlsplit


def _text(value) -> str:
    """Notebook multiline strings may be encoded as strings or string lists."""
    if isinstance(value, str):
        return value
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return "".join(value)
    return json.dumps(value, ensure_ascii=False, indent=2)


def _fence(value: str, language: str = "text") -> str:
    # A literal fence inside a source or an output must not terminate our fence.
    width = max([2] + [len(run) for run in re.findall(r"`+", value)]) + 1
    fence = "`" * width
    return f"{fence}{language}\n{value}" + ("" if value.endswith("\n") else "\n") + fence


def _url(asset_url: str, filename: str) -> str:
    return quote(unquote(asset_url).rstrip("/") + "/" + filename, safe="/.:~_-@")


def _local_url(target: Path, asset_dir: Path, asset_url: str) -> str:
    # The asset path provides a known relative coordinate without assuming a
    # documents directory name. Preserve leading '..' with posixpath.normpath.
    relative = Path(os.path.relpath(target, asset_dir)).as_posix()
    url = posixpath.normpath(unquote(asset_url).rstrip("/") + "/" + relative)
    return quote(url, safe="/.:~_-@")


def _mime_filename(stem: str, mime: str) -> str:
    extension = {
        "image/png": ".png", "image/jpeg": ".jpg", "image/svg+xml": ".svg",
        "image/gif": ".gif", "image/webp": ".webp", "application/pdf": ".pdf",
        "text/html": ".html", "text/latex": ".tex", "text/plain": ".txt",
        "text/markdown": ".md", "application/javascript": ".js",
    }.get(mime, ".json" if mime.endswith("json") else ".txt")
    label = re.sub(r"[^A-Za-z0-9_-]+", "-", mime).strip("-")
    return stem + "-" + label + extension


def extract_notebook(source: Path, asset_dir: Path, asset_url: str) -> dict:
    """Return units, stats, dependencies and files for a saved ``.ipynb``.

    The routine reads JSON and decodes assets only. It never imports the
    notebook's libraries, evaluates code, opens HTML or downloads dependencies.
    Original cell/output metadata are stored in ``notebook-metadata.json``;
    source text and all saved output payloads are preserved in the units/assets.
    """
    source = Path(source).resolve()
    asset_dir = Path(asset_dir).resolve()
    raw = source.read_bytes()
    notebook = json.loads(raw)
    if not isinstance(notebook, dict) or not isinstance(notebook.get("cells"), list):
        raise ValueError(f"Notebook sem lista de células: {source.name}")
    asset_dir.mkdir(parents=True, exist_ok=True)
    files: list[Path] = []
    units = []
    dependencies: dict[str, dict] = {}
    stats = dict(cells=0, markdown_cells=0, code_cells=0, raw_cells=0,
                 outputs=0, images=0, attachments=0)
    warnings = []
    metadata = {
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "nbformat": notebook.get("nbformat"),
        "nbformat_minor": notebook.get("nbformat_minor"),
        "metadata": notebook.get("metadata", {}),
        "cells": [],
    }

    def save(filename: str, content: str | bytes) -> tuple[Path, str]:
        path = asset_dir / filename
        if isinstance(content, bytes):
            if not path.exists() or path.read_bytes() != content:
                path.write_bytes(content)
        else:
            if not path.exists() or path.read_bytes() != content.encode("utf-8"):
                path.write_bytes(content.encode("utf-8"))
        files.append(path)
        return path, _url(asset_url, filename)

    def dependency(path_text: str, cell_number: int, kind: str) -> None:
        parsed = urlsplit(path_text)
        if parsed.scheme or parsed.netloc or not parsed.path:
            return
        local = unquote(parsed.path)
        resolved = (source.parent / local).resolve()
        entry = dependencies.setdefault(local, {
            "path": local, "resolved_path": str(resolved),
            "exists": resolved.exists(), "cells": [], "kinds": [],
        })
        if cell_number not in entry["cells"]:
            entry["cells"].append(cell_number)
        if kind not in entry["kinds"]:
            entry["kinds"].append(kind)

    def mime_asset(stem: str, mime: str, value) -> tuple[str, str]:
        filename = _mime_filename(stem, mime)
        if mime in {"image/png", "image/jpeg", "image/gif", "image/webp", "application/pdf"}:
            content = base64.b64decode(_text(value), validate=False)
        elif mime.endswith("json") and not isinstance(value, str):
            content = json.dumps(value, ensure_ascii=False, indent=2) + "\n"
        else:
            content = _text(value)
        _, link = save(filename, content)
        if mime.startswith("image/"):
            stats["images"] += 1
        return filename, link

    def rewrite_links(markdown: str, number: int, attachment_links: dict) -> str:
        def replace_target(target: str) -> str:
            bare = target[1:-1] if target.startswith("<") and target.endswith(">") else target
            if bare.startswith("attachment:"):
                name = unquote(bare[len("attachment:"):])
                if name in attachment_links:
                    return "<" + attachment_links[name] + ">"
                warnings.append(f"Célula {number}: attachment ausente: {name}")
                return target
            parsed = urlsplit(bare)
            if parsed.scheme or parsed.netloc or not parsed.path:
                return target
            dependency(bare, number, "markdown_link")
            origin = (source.parent / unquote(parsed.path)).resolve()
            if not origin.exists():
                return target
            new = _local_url(origin, asset_dir, asset_url)
            if parsed.query:
                new += "?" + parsed.query
            if parsed.fragment:
                new += "#" + parsed.fragment
            return "<" + new + ">"

        def inline(match):
            return match[1] + replace_target(match[2]) + match[3]

        def reference(match):
            return match[1] + replace_target(match[2]) + match[3]

        # Standard Markdown destinations, including <paths with spaces>, plus
        # reference definitions. Literal code fragments are kept untouched.
        inline_pattern = re.compile(r"(!?\[[^\]\n]*\]\()(<[^>\n]+>|[^\s)]+)((?:\s+[^)\n]*)?\))")
        reference_pattern = re.compile(r"^(\s{0,3}\[[^\]]+\]:\s*)(<[^>\n]+>|[^\s]+)(.*)$", re.MULTILINE)
        segments = re.split(r"(`{3,}[^\n]*\n.*?\n`{3,}(?:\n|$)|~{3,}[^\n]*\n.*?\n~{3,}(?:\n|$)|`+[^`\n]*`+)", markdown, flags=re.DOTALL)
        for i in range(0, len(segments), 2):
            segments[i] = reference_pattern.sub(reference, inline_pattern.sub(inline, segments[i]))
        return "".join(segments)

    for number, cell in enumerate(notebook["cells"], 1):
        stats["cells"] += 1
        kind = cell.get("cell_type", "raw")
        counter = kind + "_cells"
        if counter in stats:
            stats[counter] += 1
        else:
            warnings.append(f"Célula {number}: tipo desconhecido {kind!r}; preservado como texto bruto.")
            stats["raw_cells"] += 1
        text = _text(cell.get("source", ""))
        # Include paths in comments/Markdown too: optional data still matter to
        # reproducibility. Do not mistake a URL for a local CSV dependency.
        for match in re.finditer(r"[\"'`]([^\"'`\n]+\.csv)[\"'`]", text, flags=re.IGNORECASE):
            dependency(match[1], number, "csv_reference")
        cell_record = {key: value for key, value in cell.items()
                       if key not in {"source", "outputs", "attachments"}}
        cell_record["number"] = number
        cell_record["source_sha256"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
        cell_record["attachments"] = {}
        cell_record["outputs"] = []
        attachment_links = {}
        attachment_notes = []
        for attachment_number, (name, bundle) in enumerate(cell.get("attachments", {}).items(), 1):
            stats["attachments"] += 1
            saved = {}
            for mime, value in bundle.items():
                filename, link = mime_asset(f"celula-{number:03}-anexo-{attachment_number:03}", mime, value)
                saved[mime] = filename
                if name not in attachment_links or mime.startswith("image/"):
                    attachment_links[name] = link
                attachment_notes.append(f"[Anexo `{name}` — `{mime}`](<{link}>)")
            cell_record["attachments"][name] = saved
        title = {"markdown": "Texto", "code": "Código", "raw": "Texto bruto"}.get(kind, "Texto bruto")
        if kind == "markdown":
            rendered = rewrite_links(text, number, attachment_links)
            headings = re.findall(r"^#{1,6}\s+(.+)$", text, flags=re.MULTILINE)
            if headings:
                title = headings[0].strip()
        elif kind == "code":
            rendered = _fence(text, notebook.get("metadata", {}).get("language_info", {}).get("name", "python"))
            rendered += f"\n\nContagem de execução salva: `{cell.get('execution_count')}`."
            if not cell.get("outputs"):
                rendered += "\n\n*Nenhuma saída salva nesta célula; o código não foi executado na extração.*"
        else:
            rendered = _fence(text, "text")
        if attachment_notes:
            rendered += "\n\n" + " · ".join(attachment_notes)
        for output_number, output in enumerate(cell.get("outputs", []), 1):
            stats["outputs"] += 1
            output_type = output.get("output_type", "unknown")
            rendered += f"\n\n#### Saída salva {output_number} — `{output_type}`\n\n"
            output_record = {key: value for key, value in output.items()
                             if key not in {"data", "text", "traceback"}}
            output_record["number"] = output_number
            output_record["payload_files"] = {}
            if "text" in output:
                plain = _text(output["text"])
                filename = f"celula-{number:03}-saida-{output_number:03}-stream.txt"
                save(filename, plain)
                output_record["payload_files"]["stream"] = filename
                rendered += f"Fluxo `{output.get('name', 'stream')}`:\n\n" + _fence(plain) + "\n"
            if "traceback" in output:
                traceback = "\n".join(output["traceback"]) if isinstance(output["traceback"], list) else _text(output["traceback"])
                filename = f"celula-{number:03}-saida-{output_number:03}-traceback.txt"
                save(filename, traceback)
                output_record["payload_files"]["traceback"] = filename
                rendered += _fence(traceback) + "\n"
            for mime, value in output.get("data", {}).items():
                filename, link = mime_asset(f"celula-{number:03}-saida-{output_number:03}", mime, value)
                output_record["payload_files"][mime] = filename
                if mime.startswith("image/"):
                    rendered += f"\n![Saída salva da célula {number}, representação {mime}](<{link}>)\n"
                elif mime == "text/html":
                    rendered += f"\n[HTML original salvo](<{link}>) — fonte preservada abaixo, sem execução:\n\n" + _fence(_text(value), "html") + "\n"
                elif mime == "text/latex":
                    rendered += f"\nRepresentação LaTeX ([arquivo original](<{link}>)):\n\n" + _fence(_text(value), "latex") + "\n"
                elif mime in {"text/plain", "text/markdown"}:
                    rendered += f"\nRepresentação `{mime}`:\n\n" + _fence(_text(value), "text") + "\n"
                else:
                    language = "json" if mime.endswith("json") else "text"
                    representation = (json.dumps(value, ensure_ascii=False, indent=2)
                                      if language == "json" and not isinstance(value, str)
                                      else _text(value))
                    rendered += f"\nRepresentação `{mime}` ([arquivo preservado](<{link}>)):\n\n" + _fence(representation, language) + "\n"
            if not any(key in output for key in ("data", "text", "traceback")):
                rendered += _fence(json.dumps(output, ensure_ascii=False, indent=2), "json")
            cell_record["outputs"].append(output_record)
        units.append({"number": number, "title": title, "markdown": rendered,
                      "cell_type": kind, "source_sha256": cell_record["source_sha256"]})
        metadata["cells"].append(cell_record)
    save("notebook-metadata.json", json.dumps(metadata, ensure_ascii=False, indent=2) + "\n")
    return {"units": units, "stats": stats, "dependencies": list(dependencies.values()),
            "files": files, "metadata": notebook.get("metadata", {}), "warnings": warnings}
