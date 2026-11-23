#!/usr/bin/env python3
"""Extrator local incremental. Não executa notebooks nem acessa a rede.

Fontes sem adaptador, ilegíveis, não UTF-8, malformadas ou links não seguidos ficam no
manifesto com ID permanente, status e motivo; as demais fontes continuam.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import fnmatch
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import sys
import unicodedata
from urllib.parse import quote
from zoneinfo import ZoneInfo

from pdf_adapter import (PDF_EXTRACTION_VERSION, STATUS_EXCLUDED, STATUS_LINK, STATUS_MALFORMED,
                         STATUS_NOT_UTF8, STATUS_OK, STATUS_UNREADABLE, STATUS_UNSUPPORTED,
                         SourceFailure, extract_pdf, sha256)

MANIFEST_SCHEMA_VERSION = 2
TEXT_SUFFIXES = {".md", ".txt", ".json", ".csv", ".tsv", ".py", ".r", ".tex"}
SUPPORTED = {".pdf", ".ipynb"} | TEXT_SUFFIXES
POLICY = ("Adicionar novos, atualizar hashes alterados, reparar saídas corrompidas; registrar falhas por fonte; "
          "preservar ausentes, saídas obsoletas e IDs.")
LINK_REASON = ("Link simbólico quebrado ou que aponta para fora da origem; o destino não foi lido nem copiado. "
               "Copie o arquivo pretendido para a origem ou selecione a pasta real.")


def write_if_changed(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() == content.encode("utf-8"):
        return
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(content.encode("utf-8"))
    tmp.replace(path)


def dump(path: Path, value: dict) -> None:
    write_if_changed(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def read_json(path: Path, default=None):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def _is_link(path: Path) -> bool:
    return path.is_symlink() or getattr(path, "is_junction", lambda: False)()


def scan_sources(source_dir: Path) -> tuple[list[Path], list[str]]:
    """Lista arquivos regulares sem percorrer links de diretório.

    Retorna também os links quebrados ou que apontam para fora da origem; o extrator os registra
    com status "link não seguido", sem ler o destino. Links internos de arquivo são lidos; links
    internos de diretório não são percorridos, pois o conteúdo já é alcançado pelo caminho real.
    """
    root = source_dir.resolve()
    files, rejected = [], []
    for folder, dirs, names in os.walk(root, followlinks=False):
        base = Path(folder)
        for name in list(dirs) + names:
            path = base / name
            if _is_link(path):
                target = path.resolve()
                if not target.exists() or not target.is_relative_to(root):
                    rejected.append(path.relative_to(root).as_posix())
                    continue
            if name in names and path.is_file():
                if path.resolve().is_relative_to(root):
                    files.append(path)
                else:
                    rejected.append(path.relative_to(root).as_posix())
        dirs[:] = [d for d in dirs if not _is_link(base / d)]
    return files, sorted(rejected)


def excluded_by(relative: str, patterns: list[str]) -> str | None:
    """Primeiro padrão glob que corresponde ao caminho relativo POSIX; '*' também cobre '/'."""
    return next((pattern for pattern in patterns if fnmatch.fnmatchcase(relative, pattern)), None)


def migrate_manifest(manifest) -> dict:
    """Converte o manifesto da versão 1 para a 2 sem alterar IDs, slugs nem caminhos."""
    if not isinstance(manifest, dict):
        raise ValueError("Manifesto inválido; recupere antes de atualizar.")
    version = manifest.get("schema_version", 1)
    if type(version) is not int or not 1 <= version <= MANIFEST_SCHEMA_VERSION:
        raise ValueError(f"schema_version {version!r} não é suportado por estes scripts; "
                         "use a versão dos scripts que criou o manifesto.")
    documents = manifest.get("documents")
    if not isinstance(documents, list) or any(not isinstance(e, dict) for e in documents):
        raise ValueError("Manifesto inválido; recupere antes de atualizar.")
    for entry in documents:
        entry.setdefault("status", STATUS_OK)
        entry.setdefault("stale_outputs", [])
    manifest.setdefault("exclude", [])
    manifest.setdefault("excluded", [])
    manifest["schema_version"] = MANIFEST_SCHEMA_VERSION
    return manifest


def is_extracted(entry: dict) -> bool:
    return entry.get("status", STATUS_OK) == STATUS_OK


def is_failure(entry: dict) -> bool:
    return entry.get("status", STATUS_OK) not in (STATUS_OK, STATUS_EXCLUDED)


def slugify(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", value).strip("-") or "documento"


def relative_url(target: Path, start: Path) -> str:
    return quote(Path(os.path.relpath(target, start)).as_posix(), safe="/.-_")


def fence(text: str, language="text") -> str:
    size = max([len(m.group()) for m in re.finditer(r"`+", text)] + [2]) + 1
    token = "`" * size
    return f"{token}{language}\n{text.rstrip()}\n{token}"


def utf8_reason(exc: UnicodeDecodeError) -> str:
    data = exc.object if isinstance(exc.object, (bytes, bytearray)) else b""
    byte = data[exc.start:exc.start + 1].hex() or "??"
    return (f"Byte 0x{byte} inválido em UTF-8 na posição {exc.start}; a fonte não foi convertida. "
            "Salve a fonte em UTF-8 ou use um adaptador adequado.")


def review_for(root: Path, source: Path, source_hash: str, slug: str, relative: str) -> tuple[dict, str]:
    canonical = root / "revisoes" / f"{slug}.json"
    if canonical.exists():
        data = read_json(canonical, {})
    elif "/" not in relative and source.suffix.lower() == ".ipynb":
        data = read_json(root / "revisoes/notebooks.json", {}).get(source.name, {})
    elif "/" not in relative:
        path = root / "revisoes" / f"{source.stem}.json"
        if not path.exists():
            path = root / "revisoes" / f"{slugify(source.stem)}.json"
        data = read_json(path, {})
    else:
        data = {}
    if not isinstance(data, dict):
        raise ValueError(f"Revisão inválida: {relative}; esperado objeto JSON.")
    signature = hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    if data.get("source_sha256") != source_hash or data.get("source_relative", relative) != relative:
        return {}, signature
    return data, signature


def files_ok(root: Path, entry: dict) -> bool:
    return bool(entry.get("output_hashes")) and all((root / rel).is_file() and sha256(root / rel) == digest
               for rel, digest in entry.get("output_hashes", {}).items())


def natural_key(path: Path):
    return tuple((0, int(part)) if part.isdigit() else (1, part.casefold())
                 for part in re.split(r"(\d+)", path.as_posix()))


def reviewed_images(root: Path, entry: dict, review: dict) -> tuple[set, set]:
    """Return declared/expected notebook image filenames, including attachments."""
    saved = read_json(root / "assets" / entry["slug"] / "notebook-metadata.json", {})
    expected, coordinates = set(), {}
    for cell in saved.get("cells", []):
        for output in cell.get("outputs", []):
            for mime, filename in output.get("payload_files", {}).items():
                if mime.startswith("image/"):
                    expected.add(filename)
                    coordinates[(cell["number"], output["number"], mime)] = filename
        for name, bundle in cell.get("attachments", {}).items():
            for mime, filename in bundle.items():
                if mime.startswith("image/"):
                    expected.add(filename)
                    coordinates[(cell["number"], name, mime)] = filename
    declared = set()
    for item in review.get("reviewed_images", []):
        if isinstance(item, str):
            declared.add(item)
        elif isinstance(item, dict):
            key = (item.get("cell"), item.get("output", item.get("attachment")), item.get("mime"))
            declared.add(coordinates.get(key, "coordenada-inexistente:" + repr(key)))
    return declared, expected


def metadata_pages(root: Path, entry: dict) -> list[dict]:
    """Páginas registradas em metadados/<slug>.json; lista vazia quando o metadado é ilegível."""
    if entry.get("type") != ".pdf":
        return []
    try:
        metadata = read_json(root / "metadados" / f"{entry['slug']}.json", {})
    except (OSError, ValueError):
        return []
    pages = metadata.get("pages", []) if isinstance(metadata, dict) else []
    return [page for page in pages if isinstance(page, dict)]


def pdf_pages(root: Path, entry: dict) -> list[dict]:
    """Páginas de uma extração registrada; entradas sem saídas não têm páginas atuais."""
    return metadata_pages(root, entry) if entry.get("output_hashes") else []


def page_notes(review: dict) -> dict:
    notes = review.get("pages", {})
    return notes if isinstance(notes, dict) else {}


def ocr_handled(note) -> bool:
    note = note if isinstance(note, dict) else {}
    return bool(str(note.get("transcription_md") or "").strip() or note.get("issues"))


def review_gaps(root: Path, entry: dict, review: dict) -> list[str]:
    """Páginas que exigem registro específico além de reviewed_pages.

    Uma candidata a OCR exige transcription_md ou issues. Uma página com imagem incorporada
    não extraída exige issues. Nenhum OCR é executado.
    """
    if entry.get("type") != ".pdf":
        return []
    notes = page_notes(review)
    gaps = []
    for page in metadata_pages(root, entry):
        note = notes.get(str(page.get("number")), {})
        if page.get("ocr_candidate") and not ocr_handled(note):
            gaps.append(f"Página candidata a OCR sem transcription_md ou issues: {entry['source_relative']} p{page['number']}")
        if page.get("image_failures") and not (isinstance(note, dict) and note.get("issues")):
            gaps.append(f"Página com imagem incorporada não extraída sem issues: {entry['source_relative']} p{page['number']}")
    return gaps


def review_complete(root: Path, entry: dict, review: dict) -> bool:
    if not review or not is_extracted(entry):
        return False
    if entry["type"] == ".pdf":
        return (set(review.get("reviewed_pages", [])) == set(range(1, entry["stats"]["pages"] + 1))
                and not review_gaps(root, entry, review))
    if entry["type"] == ".ipynb":
        images, expected = reviewed_images(root, entry, review)
        return (set(review.get("reviewed_cells", [])) == set(range(1, entry["stats"]["cells"] + 1))
                and images == expected)
    return set(review.get("reviewed_units", [])) == set(range(1, entry["stats"].get("units", 1) + 1))


def topic_errors(topics, source_type: str, limit: int | None = None) -> list[str]:
    """Validate topic locations, including text adapters' legacy cell anchors."""
    key = "pages" if source_type == ".pdf" else "cells"
    if not isinstance(topics, list):
        return ["topics deve ser uma lista JSON."]
    errors = []
    for number, topic in enumerate(topics, 1):
        label = f"Tópico {number}"
        if not isinstance(topic, dict) or set(topic) != {"topic", key}:
            errors.append(f"{label}: usar exatamente topic e {key}; unidades/outras chaves não são aceitas.")
            continue
        if not isinstance(topic["topic"], str) or not topic["topic"].strip():
            errors.append(f"{label}: título topic deve ser uma string não vazia.")
        references = topic[key]
        if (not isinstance(references, list) or not references
                or any(type(n) is not int or n < 1 or (limit is not None and n > limit) for n in references)):
            errors.append(f"{label}: {key} deve ter inteiros válidos não vazios, numerados de 1" +
                          (f" a {limit}." if limit is not None else "."))
    return errors


def refresh_dependencies(metadata: dict, source: Path) -> tuple[bool, bool]:
    changed = False
    links_changed = False
    for dep in metadata.get("dependencies", []):
        path = dep.get("path", dep.get("reference"))
        if not path:
            continue
        resolved = (source.parent / path).resolve()
        present = resolved.exists()
        if dep.get("exists") != present or dep.get("resolved_path", str(resolved)) != str(resolved):
            dep.update(exists=present, resolved_path=str(resolved))
            changed = True
            links_changed = links_changed or "markdown_link" in dep.get("kinds", [])
    return changed, links_changed


def render_document(root: Path, source: Path, entry: dict, metadata: dict, review: dict) -> str:
    title = review.get("title", source.stem)
    lines = [f"# {entry['id']} — {title}", "", f"[Voltar ao índice](../index.md)", "",
             f"Fonte: [{source.name}](<{relative_url(source, root / 'documentos')}>).", "",
             f"SHA-256 da fonte: `{entry['source_sha256']}`.", "",
             review.get("description", "Extração do conteúdo presente no arquivo original."), ""]
    if source.suffix.lower() == ".pdf":
        reviewed = set(review.get("reviewed_pages", []))
        candidates = [p["number"] for p in metadata["pages"] if p.get("ocr_candidate")]
        coverage = f"Cobertura: {len(metadata['pages'])} páginas físicas; {len(reviewed)} conferidas visualmente"
        if candidates:
            coverage += f"; {len(candidates)} candidatas a OCR, sem OCR aplicado"
        lines += [coverage + ".", "",
                  "O bloco de texto preserva a camada textual e sua disposição. Complementos identificados "
                  "abaixo recuperam conteúdo visual. A imagem de cada página preserva gráficos, fórmulas, "
                  "cores, ordem de leitura e símbolos da fonte; prevalece sobre caracteres distorcidos no bloco.", "",
                  "## Sumário por página", ""]
        for page in metadata["pages"]:
            n = page["number"]
            title_page = review.get("pages", {}).get(str(n), {}).get("title", "")
            if not title_page:
                title_page = next((s.strip() for s in page["text"].splitlines() if s.strip()), "Conteúdo visual")
            lines.append(f"- [Página {n} — {title_page}](#pagina-{n:03d})")
        for page in metadata["pages"]:
            n = page["number"]
            note = review.get("pages", {}).get(str(n), {})
            lines += ["", f'<a id="pagina-{n:03d}"></a>', "", f"## Página física {n}", ""]
            if note.get("title"):
                lines += [f"**{note['title']}**", ""]
            if page["text"].strip():
                lines += ["### Texto da camada textual", "", fence(page["text"]), ""]
            else:
                lines += ["> **Candidata a OCR:** a camada textual não tem caracteres extraíveis. Nenhum OCR foi "
                          "aplicado; a imagem da página é a evidência. A revisão registra a transcrição visual "
                          "ou uma nota de fidelidade.", ""]
            if note.get("transcription_md"):
                lines += ["### Complemento de extração visual", "", note["transcription_md"], ""]
            if note.get("visual_note"):
                lines += ["**Conteúdo visual:** " + note["visual_note"], ""]
            for issue in note.get("issues", []):
                lines += ["> **Nota de fidelidade:** " + issue, ""]
            if n not in reviewed:
                lines += ["> **Revisão pendente:** imagem preservada; esta versão ainda não foi conferida visualmente.", ""]
            url = f"../assets/{entry['slug']}/{page['image']}"
            lines += [f"![Página física {n} da fonte {source.name}](<{quote(url, safe='/.-_')}>)", ""]
            if page.get("embedded_images") or page.get("image_failures"):
                lines += ["### Imagens incorporadas", "",
                          "Recursos raster extraídos do PDF, sem redimensionamento. Elementos vetoriais e a composição "
                          "visual continuam disponíveis na página completa.", ""]
                for image in page.get("embedded_images", []):
                    url = f"../assets/{entry['slug']}/{image['file']}"
                    lines.append(f"- [Imagem incorporada — {image['name']}](<{quote(url, safe='/.-_')}>) "
                                 f"· {image['width']} × {image['height']} px · página {n}.")
                for failure in page.get("image_failures", []):
                    lines.append(f"- Imagem incorporada {failure['index']} não extraída ({failure['status']}): "
                                 f"{failure['reason']} A página completa preserva a aparência.")
                lines.append("")
    else:
        stats = metadata["stats"]
        lines += [f"Cobertura: {stats.get('cells', len(metadata['units']))} células/unidades; "
                  f"{stats.get('outputs', 0)} saídas salvas; {stats.get('images', 0)} imagens salvas.", "",
                  "Conteúdo e resultados existentes na fonte. Nenhuma célula foi executada nesta extração.", ""]
        for issue in review.get("issues", []):
            lines += ["> **Nota da fonte:** " + issue, ""]
        deps = metadata.get("dependencies", [])
        if deps:
            lines += ["## Dependências referenciadas", "", "| Referência | Presença junto à fonte |", "| --- | --- |"]
            for dep in deps:
                label = dep.get("reference", dep.get("path", str(dep)))
                lines.append(f"| `{label}` | {'Presente' if dep.get('exists') else 'Ausente'} |")
            lines.append("")
        lines += ["## Sumário por célula/unidade", ""]
        for unit in metadata["units"]:
            lines.append(f"- [{unit['title']}](#celula-{unit['number']:03d})")
        for unit in metadata["units"]:
            lines += ["", f'<a id="celula-{unit["number"]:03d}"></a>', "",
                      f"## {unit['title']}", "", unit["markdown"], ""]
    return "\n".join(lines).rstrip() + "\n"


def extract_one(root: Path, source: Path, entry: dict) -> dict:
    assets = root / "assets" / entry["slug"]
    meta_path = root / "metadados" / f"{entry['slug']}.json"
    suffix = source.suffix.lower()
    try:
        metadata = read_json(meta_path, {}) if suffix == ".pdf" else {}
    except (json.JSONDecodeError, UnicodeDecodeError):
        metadata = {}
    if not isinstance(metadata, dict):
        metadata = {}
    # Os renders iniciais podem ser reutilizados antes do primeiro manifesto.
    reusable = (metadata.get("source_sha256") == entry["source_sha256"]
                and metadata.get("format") == "pdf"
                and metadata.get("pdf_extraction_version") == PDF_EXTRACTION_VERSION
                and isinstance(metadata.get("pages"), list)
                and metadata.get("pages")
                and all(isinstance(p, dict) and p.get("image") == f"pagina-{i:03d}.png"
                        and p.get("number") == i and isinstance(p.get("text"), str)
                        and (assets / p["image"]).exists()
                        for i, p in enumerate(metadata["pages"], 1)))
    if suffix == ".pdf":
        if not reusable:
            metadata = extract_pdf(source, assets)
    elif suffix == ".ipynb":
        from notebooks import extract_notebook
        try:
            metadata = extract_notebook(source, assets, f"../assets/{entry['slug']}")
        except UnicodeDecodeError as exc:
            raise SourceFailure(STATUS_NOT_UTF8, utf8_reason(exc)) from exc
        except json.JSONDecodeError as exc:
            raise SourceFailure(STATUS_MALFORMED, f"JSON inválido na linha {exc.lineno}, coluna {exc.colno}: {exc.msg}.") from exc
        except (ValueError, TypeError, AttributeError, KeyError) as exc:
            raise SourceFailure(STATUS_MALFORMED, f"Estrutura de notebook inválida: {type(exc).__name__}: {exc}") from exc
        metadata.pop("files", None)
        metadata.update(source=source.name, source_sha256=entry["source_sha256"], format="ipynb")
    elif suffix in TEXT_SUFFIXES:
        try:
            text = source.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise SourceFailure(STATUS_NOT_UTF8, utf8_reason(exc)) from exc
        metadata = {"source": source.name, "source_sha256": entry["source_sha256"], "format": "text", "text": text,
                    "units": [{"number": 1, "title": "Conteúdo integral", "markdown": fence(text)}],
                    "stats": {"units": 1}, "dependencies": []}
    else:
        raise SourceFailure(STATUS_UNSUPPORTED, unsupported_reason(suffix))
    if sha256(source) != entry["source_sha256"]:
        raise ValueError(f"A fonte mudou durante a leitura: {source.name}; execute novamente.")
    dump(meta_path, metadata)
    return metadata


def unsupported_reason(suffix: str) -> str:
    return (f"Formato {suffix or 'sem extensão'} ainda sem adaptador; a fonte não foi omitida. "
            "Use um adaptador adequado ou registre uma exclusão explícita com --exclude.")


def current_outputs(root: Path, entry: dict, metadata: dict) -> list[Path]:
    """Arquivos produzidos pela extração atual; outros arquivos do slug são saídas obsoletas."""
    slug = entry["slug"]
    assets = root / "assets" / slug
    produced = set()
    if entry["type"] == ".pdf":
        for page in metadata["pages"]:
            produced.add(assets / page["image"])
            produced.update(assets / image["file"] for image in page.get("embedded_images", []))
    elif entry["type"] == ".ipynb":
        produced.add(assets / "notebook-metadata.json")
        saved = read_json(assets / "notebook-metadata.json", {})
        for cell in saved.get("cells", []):
            for output in cell.get("outputs", []):
                produced.update(assets / name for name in output.get("payload_files", {}).values())
            for bundle in cell.get("attachments", {}).values():
                produced.update(assets / name for name in bundle.values())
    paths = [root / "documentos" / f"{slug}.md", root / "metadados" / f"{slug}.json"] + sorted(produced)
    missing = [p.relative_to(root).as_posix() for p in paths if not p.is_file()]
    if missing:
        raise ValueError(f"Saídas esperadas ausentes após extrair {entry['source_relative']}: {missing}")
    return paths


def stale_outputs(root: Path, slug: str, current) -> list[str]:
    """Saídas do slug que existem, mas não pertencem à extração atual. Nunca são apagadas ou movidas."""
    candidates = [root / "documentos" / f"{slug}.md", root / "metadados" / f"{slug}.json"]
    folder = root / "assets" / slug
    if folder.is_dir():
        candidates += [p for p in folder.rglob("*") if p.is_file()]
    current = set(current)
    return sorted(rel for p in candidates if p.is_file()
                  and (rel := p.relative_to(root).as_posix()) not in current)


def failure_record(root: Path, entry: dict, old: dict | None, failure: SourceFailure,
                   digest: str | None, source: Path, is_link: bool, zone) -> dict:
    record = {key: entry[key] for key in ("id", "slug", "source_relative", "type")}
    size = None
    if not is_link:
        try:
            size = source.stat().st_size
        except OSError:
            size = None
    record.update(status=failure.status, reason=failure.reason, source_present=True,
                  source_sha256=digest, source_bytes=size)
    same = (old is not None and old.get("recorded_at")
            and all(old.get(key) == record[key] for key in ("status", "reason", "source_sha256")))
    record["recorded_at"] = old["recorded_at"] if same else datetime.now(zone).isoformat(timespec="seconds")
    record.update(title=Path(entry["source_relative"]).stem or entry["source_relative"],
                  description=failure.reason, stats={}, dependencies=[], topics=[], review={},
                  review_status="Extração não concluída", output_hashes={},
                  stale_outputs=stale_outputs(root, entry["slug"], ()))
    return record


def compose_entry(root: Path, source: Path, rel: str, entry: dict, old: dict | None,
                  digest: str, zone, counts: dict) -> dict | None:
    """Extract or recompose one supported source. Return None when it is unchanged."""
    review, signature = review_for(root, source, digest, entry["slug"], rel)
    previous_ok = old is not None and is_extracted(old)
    same = previous_ok and old.get("source_sha256") == digest
    stats = old.get("stats", {}) if same else {}
    limit = stats.get("pages", stats.get("cells", stats.get("units", 0))) if same else None
    issues = topic_errors(review.get("topics", []), entry["type"], limit)
    if issues:
        raise ValueError(f"Revisão temática inválida de {rel}: " + " ".join(issues))
    integrity_ok = bool(previous_ok and files_ok(root, old))
    meta_path = root / "metadados" / f"{entry['slug']}.json"
    cached = read_json(meta_path, {}) if same and integrity_ok else {}
    cache_current = entry["type"] != ".pdf" or cached.get("pdf_extraction_version") == PDF_EXTRACTION_VERSION
    dependency_changed, links_changed = refresh_dependencies(cached, source) if cached else (False, False)
    if same and integrity_ok and cache_current and old.get("review_signature") == signature and not dependency_changed:
        old["source_present"] = True
        counts["unchanged"] += 1
        return None
    entry.update(source_sha256=digest, source_bytes=source.stat().st_size, source_present=True)
    if same and integrity_ok and cache_current:
        metadata = extract_one(root, source, entry) if links_changed and entry["type"] == ".ipynb" else cached
        if dependency_changed and not links_changed:
            dump(meta_path, metadata)
        kind = "recomposed"
    else:
        recovering = old is not None and old.get("source_sha256") == digest
        if recovering and entry["type"] == ".pdf":
            # Forçar recuperação de renders danificados, mesmo se o cache textual está intacto.
            dump(meta_path, extract_pdf(source, root / "assets" / entry["slug"]))
        kind = "repaired" if recovering else "changed" if old else "new"
        metadata = extract_one(root, source, entry)
        entry["extracted_at"] = datetime.now(zone).isoformat(timespec="seconds")
    entry.update(stats=metadata["stats"], dependencies=metadata.get("dependencies", []),
                 title=review.get("title", source.stem),
                 description=review.get("description", "Conteúdo integral da fonte; classificação detalhada pendente."),
                 topics=review.get("topics", []), review=review, review_signature=signature, status=STATUS_OK)
    for key in ("reason", "recorded_at"):
        entry.pop(key, None)
    limit = entry["stats"].get("pages", entry["stats"].get("cells", entry["stats"].get("units", 0)))
    issues = topic_errors(entry["topics"], entry["type"], limit)
    if issues:
        raise ValueError(f"Revisão temática inválida de {rel}: " + " ".join(issues))
    document = root / "documentos" / f"{entry['slug']}.md"
    write_if_changed(document, render_document(root, source, entry, metadata, review))
    complete = review_complete(root, entry, review)
    if entry["type"] == ".pdf":
        entry["review_status"] = "Conferido visualmente" if complete else "Revisão visual pendente"
    else:
        entry["review_status"] = "Conferido por célula/unidade" if complete else "Revisão pendente"
    outputs = current_outputs(root, entry, metadata)
    entry["output_hashes"] = {p.relative_to(root).as_posix(): sha256(p) for p in outputs}
    entry["stale_outputs"] = stale_outputs(root, entry["slug"], entry["output_hashes"])
    counts[kind] += 1
    return entry


def generate_index(root: Path, entries: list[dict], title: str, order: list[str],
                   exclude: list[str], excluded: list[str]) -> None:
    present = [e for e in entries if e["source_present"]]
    current = [e for e in present if is_extracted(e)]
    failed = [e for e in present if is_failure(e)]
    total_pages = sum(e.get("stats", {}).get("pages", 0) for e in current)
    total_cells = sum(e.get("stats", {}).get("cells", 0) for e in current)
    total_outputs = sum(e.get("stats", {}).get("outputs", 0) for e in current)
    total_images = sum(e.get("stats", {}).get("images", 0) for e in current)
    pdf_images = sum(e.get("stats", {}).get("embedded_images", 0) for e in current)
    navigation = ["[Manifesto e hashes](manifesto.json)", "[Relatório de conferência](conferencia.md)"]
    if (root / "README.md").exists():
        navigation.insert(0, "[Como atualizar e verificar](README.md)")
    lines = [f"# {title} — índice do conteúdo extraído", "",
             "Extração das fontes indicadas no manifesto, organizada para consulta e reutilização. "
             "A conferência e as limitações de cada documento estão registradas abaixo.", "",
             f"**Acervo atual:** {len(current)} documentos; {total_pages} páginas de PDF; {total_cells} células de notebooks; "
             f"{total_outputs} saídas e {total_images} imagens salvas nos notebooks; "
             f"{pdf_images} imagens incorporadas em PDFs.", ""]
    if failed or excluded:
        lines += [f"**Cobertura incompleta:** {len(failed)} fontes sem extração, registradas com estado e motivo; "
                  f"{len(excluded)} fontes excluídas por padrão explícito. Veja "
                  "[Fontes não extraídas e exclusões](#fontes-nao-extraidas-e-exclusoes).", ""]
    lines += [" · ".join(navigation), "",
              "## Catálogo em ordem de consulta", "",
              "Os identificadores são permanentes: documentos novos recebem o próximo número, sem renumerar os existentes. " +
              ("A organização inicial segue a lista de prioridades registrada no manifesto, complementada por ordem natural. "
               if order else "A organização inicial usa os caminhos em ordem natural. ") +
              "Os IDs e a posição de documentos já catalogados são preservados; a ordem serve à consulta.", "",
              "| ID | Documento / extração | Tipo e cobertura | O que contém | Conferência |",
              "| --- | --- | --- | --- | --- |"]
    for e in entries:
        status = e.get("status", STATUS_OK)
        has_document = bool(e.get("output_hashes"))
        units = e.get("stats", {}).get("pages", e.get("stats", {}).get("cells", e.get("stats", {}).get("units", 0)))
        unit_name = "páginas" if e["type"] == ".pdf" else "células" if e["type"] == ".ipynb" else "unidades"
        if not e["source_present"]:
            label = "Fonte ausente"
        elif status == STATUS_EXCLUDED:
            label = "Excluído por padrão"
        elif status != STATUS_OK:
            label = f"Não extraído: {status}"
        else:
            label = e["review_status"]
        name = (f"[{e['title']}](documentos/{e['slug']}.md)" if has_document
                else f"`{e['source_relative'].replace('|', '/')}` (sem extração)")
        coverage = f"{e['type']} · {units} {unit_name}" if has_document else f"{e['type'] or 'sem extensão'} · —"
        lines.append(f"| {e['id']} | {name} | {coverage} | {e.get('description', '').replace('|', '/')} | {label} |")
    if failed or exclude or excluded:
        lines += ["", '<a id="fontes-nao-extraidas-e-exclusoes"></a>', "", "## Fontes não extraídas e exclusões", ""]
        if failed:
            lines += ["Cada fonte abaixo mantém o ID permanente. Corrija a fonte, use um adaptador adequado ou registre "
                      "uma exclusão explícita; a cobertura permanece incompleta enquanto houver registros.", "",
                      "| ID | Fonte | Estado | Motivo |", "| --- | --- | --- | --- |"]
            for e in failed:
                lines.append(f"| {e['id']} | `{e['source_relative'].replace('|', '/')}` | {e['status']} | "
                             f"{e.get('reason', '').replace('|', '/')} |")
            lines.append("")
        if exclude or excluded:
            patterns = ", ".join(f"`{p}`" for p in exclude) or "nenhum"
            lines += [f"Padrões `--exclude` registrados: {patterns}. Fontes excluídas nesta execução: {len(excluded)}; "
                      "a lista completa está em `manifesto.json` (`excluded`).", ""]
        if lines[-1] == "":
            lines.pop()
    lines += ["", "## Sumário temático com localização nas fontes", "",
              "As referências abaixo apontam para páginas físicas ou células numeradas a partir de 1. "
              "São tópicos presentes nas fontes, sem acréscimo de conteúdo externo.", ""]
    for e in entries:
        if not e.get("output_hashes"):
            continue
        lines += [f"### {e['id']} — {e['title']}", ""]
        for topic in e.get("topics", []):
            key = "pages" if "pages" in topic else "cells"
            prefix = "pagina" if key == "pages" else "celula"
            refs = ", ".join(f"[{n}](documentos/{e['slug']}.md#{prefix}-{n:03d})" for n in topic.get(key, []))
            lines.append(f"- **{topic['topic']}** — {'páginas' if key == 'pages' else 'células'} {refs}.")
        if not e.get("topics"):
            lines.append(f"- [Conteúdo integral e sumário interno](documentos/{e['slug']}.md); classificação temática pendente.")
        lines.append("")
    lines += ["## Limites do acervo e cuidados de leitura", "",
              "- Equações e gráficos em imagens foram preservados nas páginas renderizadas e complementados quando necessário. "
              "Divergências internas e símbolos ambíguos aparecem nas notas de fidelidade e no relatório de conferência.", ""]
    lines.append("- Imagens incorporadas ficam vinculadas à página de origem. Diagramas vetoriais e composição "
                 "da página permanecem nos renders; não são necessariamente arquivos de imagem separados.")
    ocr, image_failures = [], []
    for e in current:
        pages = pdf_pages(root, e)
        numbers = [p["number"] for p in pages if p.get("ocr_candidate")]
        if numbers:
            ocr.append(f"{e['id']} p. " + ", ".join(f"[{n}](documentos/{e['slug']}.md#pagina-{n:03d})" for n in numbers))
        failures = [(p["number"], len(p["image_failures"])) for p in pages if p.get("image_failures")]
        if failures:
            image_failures.append(f"{e['id']} " + ", ".join(
                f"[p. {n}](documentos/{e['slug']}.md#pagina-{n:03d}) ({count})" for n, count in failures))
    if ocr:
        lines.append("- Páginas candidatas a OCR, sem caracteres na camada textual; nenhum OCR foi aplicado: "
                     + "; ".join(ocr) + ".")
    if image_failures:
        lines.append("- Imagens incorporadas não extraídas, registradas por página: " + "; ".join(image_failures) + ".")
    stale = sum(len(e.get("stale_outputs", [])) for e in entries)
    if stale:
        lines.append(f"- Saídas obsoletas preservadas e listadas em `stale_outputs` no manifesto: {stale} arquivos. "
                     "Não são apagadas nem movidas automaticamente.")
    missing = sorted({dep.get("path", dep.get("reference", "")) for e in current
                      for dep in e.get("dependencies", []) if not dep.get("exists")})
    if missing:
        lines.append("- Dependências locais ausentes: " + ", ".join(f"`{p}`" for p in missing) + ".")
    empty = [e for e in current if e["type"] == ".ipynb" and e.get("stats", {}).get("outputs", 0) == 0]
    if empty:
        lines.append("- Notebooks sem saídas salvas: " + ", ".join(f"`{e['source_relative']}`" for e in empty) + ".")
    lines += ["- Resultados salvos nos notebooks não foram reproduzidos por execução nesta etapa.", ""]
    write_if_changed(root / "index.md", "\n".join(lines))


def generate_report(root: Path, entries: list[dict]) -> None:
    lines = ["# Conferência das extrações", "",
             "A cobertura estrutural e a revisão do conteúdo são verificações distintas. "
             "Este relatório registra extração e conferência das fontes; análise, organização editorial e criação "
             "de novos materiais dependem de pedido específico.", "",
             "## Evidências e notas por documento", ""]
    for e in entries:
        status = e.get("status", STATUS_OK)
        lines += [f"### {e['id']} — {e['title']}", "", f"Fonte: `{e['source_relative']}`.", ""]
        if not e.get("output_hashes"):
            digest = f" SHA-256: `{e['source_sha256']}`." if e.get("source_sha256") else ""
            lines += [f"Estado: **{status}**.{digest}", "", f"- Motivo: {e.get('reason', '')}"]
            if not e["source_present"]:
                lines.append("- Fonte ausente na última execução; o registro e o ID permanecem.")
            if e.get("stale_outputs"):
                lines.append(f"- Saídas obsoletas preservadas, sem exclusão automática: {len(e['stale_outputs'])} "
                             "arquivos listados em `stale_outputs` no manifesto.")
            lines.append("")
            continue
        state = e["review_status"] if status == STATUS_OK else f"{status}; extração anterior preservada"
        lines += [f"Estado: **{state}**. SHA-256: `{e['source_sha256']}`.", ""]
        if status != STATUS_OK:
            lines.append(f"- Motivo: {e.get('reason', '')}")
        review = e.get("review", {})
        if e["type"] == ".pdf":
            lines += [f"Páginas físicas: {e['stats']['pages']}; conferidas visualmente: {len(review.get('reviewed_pages', []))}.", ""]
            notes = page_notes(review)
            pages = pdf_pages(root, e)
            ocr = [p["number"] for p in pages if p.get("ocr_candidate")]
            if ocr:
                lines.append("- Páginas candidatas a OCR, sem caracteres na camada textual; nenhum OCR foi aplicado: " +
                             ", ".join(f"[{n}](documentos/{e['slug']}.md#pagina-{n:03d}) "
                                       f"({'registrada na revisão' if ocr_handled(notes.get(str(n))) else 'pendente'})"
                                       for n in ocr) + ".")
            for page in pages:
                for failure in page.get("image_failures", []):
                    n = page["number"]
                    lines.append(f"- [Página {n}](documentos/{e['slug']}.md#pagina-{n:03d}): imagem incorporada "
                                 f"{failure['index']} não extraída ({failure['status']}): {failure['reason']}")
        for issue in review.get("issues", []):
            lines.append("- " + issue)
        for number, page in review.get("pages", {}).items():
            for issue in page.get("issues", []):
                lines.append(f"- [Página {number}](documentos/{e['slug']}.md#pagina-{int(number):03d}): {issue}")
        for dep in e.get("dependencies", []):
            if not dep.get("exists"):
                lines.append(f"- Dependência ausente junto à fonte: `{dep.get('reference', dep.get('path', str(dep)))}`.")
        if e.get("stale_outputs"):
            lines.append(f"- Saídas obsoletas preservadas, sem exclusão automática: {len(e['stale_outputs'])} "
                         "arquivos listados em `stale_outputs` no manifesto.")
        if not review:
            lines.append("- Revisão editorial/visual pendente para este hash da fonte.")
        lines.append("")
    write_if_changed(root / "conferencia.md", "\n".join(lines))


def bootstrap(root: Path, source_dir: Path, title: str) -> None:
    """Keep the output independently reproducible, without modifying sources."""
    here = Path(__file__).resolve().parent
    for source in sorted(here.glob("*.py")):
        target = root / "scripts" / source.name
        if source.resolve() != target.resolve():
            write_if_changed(target, source.read_text(encoding="utf-8"))
    requirements = here.parent / "requirements.txt"
    if requirements.exists() and requirements.resolve() != (root / "requirements.txt").resolve():
        write_if_changed(root / "requirements.txt", requirements.read_text(encoding="utf-8"))
    if (root / "README.md").exists():
        return
    source_arg = shlex.quote(Path(os.path.relpath(source_dir, root)).as_posix())
    lines = [f"# {title} — conteúdo extraído", "",
             "[Índice do acervo](index.md) · [Manifesto](manifesto.json) · [Conferência](conferencia.md) · [Validação](validacao.json)", "",
             "## Estrutura", "",
             "- `documentos/`: uma extração integral por fonte, com âncoras físicas e notas de fidelidade.",
             "- `assets/<slug>/`: páginas PNG, imagens incorporadas de PDFs em `imagens/` e todas as representações MIME salvas nos notebooks.",
             "- `metadados/`: texto, cobertura e dependências recuperados por documento.",
             "- `revisoes/<slug>.json`: revisão humana vinculada ao SHA-256 da fonte; não preenchida automaticamente.",
             "- `scripts/` e `requirements.txt`: pipeline local reproduzível.", "",
             "## Atualização e conferência", "",
             "Execute a partir desta pasta com Python 3.11+ e as dependências de `requirements.txt`. PDFs exigem `pdftotext` e `pdftoppm`; use o PATH do processo ou configure CONTENT_EXTRACT_PDFTOTEXT e CONTENT_EXTRACT_PDFTOPPM.", "",
             "```sh", f"python3 -B scripts/extrair.py --source {source_arg} --output .",
             f"python3 -B scripts/validar.py --source {source_arg} --output .",
             "python3 -B scripts/preparar_revisao.py --output .",
             f"python3 -B scripts/validar.py --source {source_arg} --output . --require-reviewed",
             "```", "",
             "SHA-256 detecta documentos novos e alterados; hashes dos artefatos permitem reparar corrupção. IDs são permanentes. "
             "Execuções sem alteração preservam bytes e datas dos arquivos. Fontes ausentes continuam registradas, com a extração preservada.", "",
             "Fontes sem adaptador, ilegíveis, não UTF-8, malformadas, acima de um limite de recurso ou links não seguidos ficam no manifesto com status e motivo; "
             "a cobertura permanece incompleta. `--exclude` registra exclusões explícitas no manifesto. Saídas que deixam de corresponder à fonte "
             "ficam em `stale_outputs`; nada é apagado automaticamente. CONTENT_EXTRACT_TIMEOUT e CONTENT_EXTRACT_MAX_IMAGE_PIXELS ajustam os limites.", "",
             "A validação estrutural não certifica leitura visual. Confira cada página/célula, todas as imagens salvas e as discrepâncias antes de registrar a revisão. "
             "Folhas de contato ajudam a revisar; amplie fórmulas, gráficos e tabelas quando necessário. Nenhum notebook, HTML ou JavaScript é executado; URLs e dados ausentes não são baixados.", ""]
    write_if_changed(root / "README.md", "\n".join(lines))


def run(source_dir: Path, root: Path | None = None, title: str | None = None, timezone: str | None = None,
        order: list[str] | None = None, exclude: list[str] | None = None) -> dict:
    source_dir = source_dir.expanduser().resolve()
    root = (root.expanduser() if root is not None else source_dir.parent / "Extracted").resolve()
    if (not source_dir.is_dir() or root == source_dir or root.is_relative_to(source_dir)
            or source_dir.is_relative_to(root)):
        raise ValueError("Origem ausente ou origem/destino sobrepostos.")
    if (root / "index.md").exists() and not (root / "manifesto.json").exists():
        raise ValueError("Já existe index.md, mas falta manifesto.json. Recupere o manifesto para preservar IDs e hashes; o catálogo não será reiniciado.")
    previous = migrate_manifest(read_json(root / "manifesto.json", {"documents": []}))
    if "source_directory" in previous:
        from urllib.parse import unquote
        if (root / unquote(previous["source_directory"])).resolve() != source_dir:
            raise ValueError("Este manifesto pertence a outra pasta de fontes; use outro destino.")
    title = title or previous.get("title") or source_dir.name
    timezone = timezone or previous.get("timezone") or "UTC"
    zone = ZoneInfo(timezone)
    order = previous.get("order", []) if order is None else order
    if (not isinstance(order, list) or any(not isinstance(p, str) or not p or Path(p).is_absolute()
                                          or ".." in Path(p).parts for p in order)
            or len(order) != len(set(order))):
        raise ValueError("A ordem deve ser uma lista JSON de caminhos relativos únicos, sem '..'.")
    exclude = previous["exclude"] if exclude is None else exclude
    if (not isinstance(exclude, list) or any(not isinstance(p, str) or not p.strip() for p in exclude)
            or len(exclude) != len(set(exclude))):
        raise ValueError("Os padrões --exclude devem ser textos glob não vazios e únicos.")
    priority = {p: i for i, p in enumerate(order)}
    entries = previous["documents"]
    if len({e["id"] for e in entries}) != len(entries):
        raise ValueError("Manifesto inválido ou IDs duplicados; recupere antes de atualizar.")
    existing = {e["source_relative"]: e for e in entries}
    files, links = scan_sources(source_dir)
    inventory = [(p.relative_to(source_dir).as_posix(), p, False) for p in files]
    inventory += [(rel, source_dir / rel, True) for rel in links]
    inventory.sort(key=lambda item: (priority.get(item[0], len(priority)), natural_key(Path(item[0]))))
    for folder in ("assets", "documentos", "metadados", "revisoes"):
        (root / folder).mkdir(parents=True, exist_ok=True)
    bootstrap(root, source_dir, title)
    found, excluded = set(), {}
    counts = {"new": 0, "changed": 0, "unchanged": 0, "recomposed": 0, "repaired": 0}
    for rel, source, is_link in inventory:
        old = existing.get(rel)
        pattern = excluded_by(rel, exclude)
        if pattern is not None:
            # Exclusão explícita: a fonte não é lida; uma extração anterior permanece preservada.
            excluded[rel] = pattern
            if old is not None:
                old.update(status=STATUS_EXCLUDED, source_present=True,
                           reason=f"Corresponde ao padrão --exclude {pattern!r}; a fonte não foi lida nesta execução.")
            continue
        found.add(rel)
        if old is None:
            slug = slugify(str(Path(rel).with_suffix("")))
            if slug in {e["slug"] for e in entries}:
                slug += "-" + hashlib.sha256(rel.encode()).hexdigest()[:8]
            entry = {"id": f"DOC-{max([int(e['id'].split('-')[1]) for e in entries] + [0]) + 1:03d}",
                     "slug": slug, "source_relative": rel, "type": Path(rel).suffix.lower(), "status": STATUS_OK}
            entries.append(entry)
            slot = len(entries) - 1
        else:
            entry = dict(old)
            slot = entries.index(old)
        digest = None
        try:
            if is_link:
                raise SourceFailure(STATUS_LINK, LINK_REASON)
            try:
                digest = sha256(source)
            except OSError as exc:
                raise SourceFailure(STATUS_UNREADABLE, f"Leitura impossível: {exc.strerror or type(exc).__name__}.") from exc
            if entry["type"] not in SUPPORTED:
                raise SourceFailure(STATUS_UNSUPPORTED, unsupported_reason(entry["type"]))
            try:
                composed = compose_entry(root, source, rel, entry, old, digest, zone, counts)
            except OSError as exc:
                if exc.filename is None or os.fspath(exc.filename) != os.fspath(source):
                    raise
                raise SourceFailure(STATUS_UNREADABLE, f"Leitura impossível: {exc.strerror or type(exc).__name__}.") from exc
        except SourceFailure as failure:
            entries[slot] = failure_record(root, entry, old, failure, digest, source, is_link, zone)
            continue
        if composed is not None:
            entries[slot] = composed
    for entry in entries:
        if entry["source_relative"] not in found and entry["source_relative"] not in excluded:
            entry["source_present"] = False
    manifest = {"schema_version": MANIFEST_SCHEMA_VERSION, "source_directory": relative_url(source_dir, root),
                "title": title, "timezone": timezone, "order": order, "exclude": exclude,
                "excluded": sorted(excluded), "policy": POLICY, "documents": entries}
    dump(root / "manifesto.json", manifest)
    generate_index(root, entries, title, order, exclude, sorted(excluded))
    generate_report(root, entries)
    return {**counts, "documents": len(entries), "present": len(found),
            "absent": sum(1 for e in entries if not e["source_present"]),
            "failed": sum(1 for e in entries if e["source_present"] and is_failure(e)),
            "excluded": len(excluded)}


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, help="Destino separado das fontes. Padrão: pasta irmã Extracted/.")
    parser.add_argument("--title", help="Título do acervo; persistido no manifesto.")
    parser.add_argument("--timezone", help="Fuso IANA; persistido no manifesto. Padrão inicial UTC.")
    parser.add_argument("--order", type=Path, help="JSON com lista de caminhos relativos para ordenar a inclusão inicial/nova; IDs históricos permanecem fixos.")
    parser.add_argument("--exclude", action="append", metavar="PADRAO",
                        help="Padrão glob sobre o caminho relativo POSIX ('*' também cobre '/'); repita para vários. "
                             "Substitui a lista persistida no manifesto.")
    parser.add_argument("--clear-exclude", action="store_true", help="Remove os padrões --exclude persistidos.")
    args = parser.parse_args()
    if args.clear_exclude and args.exclude:
        parser.error("Use --exclude ou --clear-exclude, não ambos.")
    try:
        print(json.dumps(run(args.source, args.output, args.title, args.timezone,
                             read_json(args.order) if args.order else None,
                             [] if args.clear_exclude else args.exclude), ensure_ascii=False))
    except Exception as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        sys.exit(1)
