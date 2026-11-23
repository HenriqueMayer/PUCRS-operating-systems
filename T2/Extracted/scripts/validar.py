#!/usr/bin/env python3
"""Verifica cobertura, hashes, conteúdo de células/saídas e referências locais.

Falhas registradas por fonte tornam a cobertura incompleta, sem falha estrutural. A comparação
entre pdftotext e pypdf define prioridade de revisão; não é falha nem prova de fidelidade.
"""
from __future__ import annotations

import argparse
import base64
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit

from PIL import Image
from pypdf import PdfReader
from extrair import (dump, excluded_by, is_extracted, migrate_manifest, review_complete, review_for,
                     review_gaps, reviewed_images, scan_sources, sha256, topic_errors)
from pdf_adapter import (PDF_EXTRACTION_VERSION, STATUS_EXCLUDED, STATUS_LINK,
                         embedded_filename, image_formats, limit_errors, pdf_image_items, pdf_text,
                         resource_key, resource_limits, tool_versions)

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".tif", ".tiff", ".jp2"}


def multiline(value):
    return "".join(value) if isinstance(value, list) else value


def outside_fences(text: str) -> str:
    lines, fence = [], None
    for line in text.splitlines():
        match = re.match(r"^\s*(`{3,}|~{3,})", line)
        if match:
            token = match.group(1)
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence):
                fence = None
            continue
        if fence is None:
            lines.append(line)
    return "\n".join(lines)


def text_priority(primary: str, secondary: str | None) -> tuple[str, str, float | None]:
    """Compare pdftotext and pypdf word multisets. The result orders review; it is not a failure."""
    a, b = primary.split(), (secondary or "").split()
    if secondary is None:
        return "alta", "pypdf não extraiu texto desta página", None
    if not a and not b:
        return "alta", "candidata a OCR: nenhuma das extrações recuperou caracteres", None
    if not a or not b:
        return "alta", "texto recuperado por apenas uma das extrações", 0.0
    agreement = sum((Counter(a) & Counter(b)).values()) / max(len(a), len(b))
    if agreement < 0.8:
        return "alta", "baixa concordância de palavras entre pdftotext e pypdf", agreement
    if agreement < 0.95:
        return "média", "concordância parcial de palavras entre pdftotext e pypdf", agreement
    return "baixa", "concordância alta de palavras", agreement


def verify_image(path: Path) -> None:
    with resource_limits():
        with Image.open(path, formats=image_formats(path)) as img:
            img.verify()


def validate(root: Path, source_dir: Path, require_reviewed: bool = False) -> dict:
    root, source_dir = root.resolve(), source_dir.resolve()
    failures, notes, review_pending, source_gaps, image_gaps, priority = [], [], [], [], [], []
    counts = dict(documents=0, pdf_pages=0, visually_reviewed_pages=0, notebook_cells=0,
                  saved_outputs=0, saved_images=0, embedded_pdf_images=0, verified_assets=0, local_links=0,
                  failed_sources=0, image_failures=0, ocr_candidates=0, excluded_sources=0, stale_outputs=0)
    manifest = migrate_manifest(json.loads((root / "manifesto.json").read_text(encoding="utf-8")))
    documents = manifest["documents"]
    ids = [e["id"] for e in documents]
    if len(ids) != len(set(ids)):
        failures.append("Identificadores duplicados")
    for field in ("slug", "source_relative"):
        values = [e[field] for e in documents]
        if len(values) != len(set(values)):
            failures.append(f"Campo duplicado no manifesto: {field}")
    source_files, rejected_links = scan_sources(source_dir)
    rejected = set(rejected_links)
    inventory = {p.relative_to(source_dir).as_posix() for p in source_files} | rejected
    excluded_now = sorted(rel for rel in inventory if excluded_by(rel, manifest["exclude"]) is not None)
    counts["excluded_sources"] = len(excluded_now)
    if excluded_now != sorted(manifest["excluded"]):
        failures.append("Exclusões divergentes do manifesto; execute extrair.py: "
                        f"{sorted(set(excluded_now) ^ set(manifest['excluded']))}")
    considered = inventory - set(excluded_now)
    registered = {e["source_relative"] for e in documents
                  if e["source_present"] and e.get("status") != STATUS_EXCLUDED}
    if considered != registered:
        failures.append(f"Cobertura de fontes divergente: {sorted(considered ^ registered)}")
    declared_absent = set()
    absent_originals = {(source_dir / e["source_relative"]).resolve()
                        for e in documents if not e["source_present"]}
    known_outputs = {rel for e in documents for rel in e.get("output_hashes", {})}
    stale_listed = {rel for e in documents for rel in e.get("stale_outputs", [])}
    pdftotext_version = None
    for e in documents:
        status = e.get("status")
        for dep in e.get("dependencies", []):
            if not dep.get("exists"):
                declared_absent.add(dep.get("path", dep.get("reference", "")))
        rel_source = e["source_relative"]
        source = source_dir / rel_source
        document = root / "documentos" / f"{e['slug']}.md"
        metadata_path = root / "metadados" / f"{e['slug']}.json"
        for rel, digest in e.get("output_hashes", {}).items():
            path = root / rel
            if not path.is_file() or sha256(path) != digest:
                failures.append(f"Saída ausente/alterada: {rel}")
            else:
                counts["verified_assets"] += 1
                if path.suffix.lower() in IMAGE_SUFFIXES:
                    try:
                        verify_image(path)
                    except limit_errors() as exc:
                        failures.append(f"Imagem acima do limite de pixels: {rel}: {exc}")
                    except Exception as exc:
                        failures.append(f"Imagem indecodificável: {rel}: {exc}")
        for rel in e.get("stale_outputs", []):
            if (root / rel).is_file():
                counts["stale_outputs"] += 1
            else:
                notes.append(f"Saída obsoleta listada já não existe; a próxima atualização remove o registro: {rel}")
        if not e["source_present"]:
            notes.append(f"Fonte ausente, extração preservada: {rel_source}")
            continue
        if status == STATUS_EXCLUDED:
            notes.append(f"Fonte excluída por padrão explícito: {rel_source}")
            continue
        if not is_extracted(e):
            counts["failed_sources"] += 1
            source_gaps.append(f"{e['id']} {rel_source}: {status} — {e.get('reason', '')}")
            if status == STATUS_LINK:
                if rel_source not in rejected:
                    failures.append(f"Registro de link desatualizado; execute extrair.py: {rel_source}")
            elif rel_source in rejected:
                failures.append(f"A fonte virou link não seguido; execute extrair.py: {rel_source}")
            else:
                try:
                    current = sha256(source)
                except OSError:
                    current = None
                if current != e.get("source_sha256"):
                    failures.append(f"Fonte alterada desde o registro de falha; execute extrair.py: {rel_source}")
            continue
        if rel_source in rejected:
            failures.append(f"A fonte extraída virou link não seguido; execute extrair.py: {rel_source}")
            continue
        counts["documents"] += 1
        if sha256(source) != e["source_sha256"]:
            failures.append(f"Hash da fonte mudou: {source.name}")
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            body = document.read_text(encoding="utf-8")
        except (OSError, ValueError) as exc:
            failures.append(f"Artefato ilegível: {rel_source}: {exc}")
            continue
        if not isinstance(metadata, dict):
            failures.append(f"Metadado não é um objeto JSON: {rel_source}")
            continue
        if metadata["source_sha256"] != e["source_sha256"]:
            failures.append(f"Metadado de outra versão: {source.name}")
        review = e.get("review", {})
        _, signature = review_for(root, source, e["source_sha256"], e["slug"], rel_source)
        if signature != e.get("review_signature"):
            failures.append(f"A revisão mudou desde a composição; execute extrair.py novamente: {rel_source}")
        if review and review.get("source_sha256") != e["source_sha256"]:
            failures.append(f"Revisão de outra versão: {source.name}")
        if review and review.get("source_relative", rel_source) != rel_source:
            failures.append(f"Revisão de outro caminho: {source.name}")
        if not review_complete(root, e, review):
            review_pending.append(f"Revisão humana incompleta: {rel_source}")
        review_pending.extend(review_gaps(root, e, review))
        if not e.get("topics"):
            review_pending.append(f"Classificação temática pendente: {rel_source}")
        if e["type"] == ".pdf":
            if pdftotext_version is None:
                pdftotext_version = tool_versions("pdftotext")["pdftotext"]
            extracted_with = metadata.get("tools", {}).get("pdftotext")
            pages = metadata["pages"]
            if metadata.get("pdf_extraction_version") != PDF_EXTRACTION_VERSION:
                failures.append(f"Cache PDF de versão anterior ({metadata.get('pdf_extraction_version')}); execute extrair.py: {source.name}")
            reviewed = set(review.get("reviewed_pages", []))
            counts["visually_reviewed_pages"] += len(reviewed)
            try:
                with resource_limits():
                    reader = PdfReader(source)
                    n = len(reader.pages)
                text = pdf_text(source)
            except Exception as exc:  # SourceFailure, limites do pypdf/Pillow ou PDF ilegível nesta conferência.
                failures.append(f"Conferência do PDF interrompida por limite ou erro: {source.name}: {exc}")
                continue
            counts["pdf_pages"] += n
            if len(pages) != n or [p["number"] for p in pages] != list(range(1, n + 1)):
                failures.append(f"Páginas incompletas: {source.name}")
            if not reviewed.issubset(set(range(1, n + 1))):
                failures.append(f"Revisão tem página inexistente: {source.name}")
            if reviewed != set(range(1, n + 1)):
                notes.append(f"Revisão visual pendente: {source.name}")
            parts = text.split("\f")
            if parts and not parts[-1].strip():
                parts.pop()
            if len(parts) != n:
                failures.append(f"Contagem textual PDF divergente: {source.name}")
            for page, original in zip(pages, parts):
                number = page["number"]
                if page["text"] != original.rstrip() or page["text"].strip() not in body:
                    versions = (f" (extração: {extracted_with}; conferência: {pdftotext_version})"
                                if extracted_with and extracted_with != pdftotext_version else "")
                    failures.append(f"Texto PDF divergente: {source.name} p{number}{versions}")
                if f'id="pagina-{number:03d}"' not in body:
                    failures.append(f"Âncora de página ausente: {source.name} p{number}")
                if page.get("ocr_candidate") != (not original.strip()):
                    failures.append(f"Marcação ocr_candidate divergente: {source.name} p{number}")
                if page.get("ocr_candidate"):
                    counts["ocr_candidates"] += 1
                try:
                    with resource_limits():
                        page_object = reader.pages[number - 1]
                        items = pdf_image_items(page_object)
                        try:
                            secondary = page_object.extract_text() or ""
                        except Exception:
                            secondary = None
                except Exception as exc:
                    failures.append(f"Falha ao conferir imagens incorporadas: {source.name} p{number}: {exc}")
                    continue
                level, reason, agreement = text_priority(original, secondary)
                if level != "baixa":
                    priority.append({"document": e["id"], "source_relative": rel_source, "page": number,
                                     "priority": level, "reason": reason,
                                     "word_agreement": None if agreement is None else round(agreement, 3)})
                ok_items = [(i, r, img) for i, (r, img, err) in enumerate(items, 1) if err is None]
                failed_items = [(i, r, err) for i, (r, img, err) in enumerate(items, 1) if err is not None]
                recorded = page.get("embedded_images", [])
                recorded_failures = page.get("image_failures", [])
                counts["embedded_pdf_images"] += len(ok_items)
                if len(recorded) != len(ok_items) or len(recorded_failures) != len(failed_items):
                    failures.append(f"Imagens incorporadas incompletas: {source.name} p{number}")
                for (index, resource, image), saved in zip(ok_items, recorded):
                    filename = embedded_filename(number, index, image)
                    path = root / "assets" / e["slug"] / filename
                    rel = path.relative_to(root).as_posix()
                    if (saved.get("file") != filename or saved.get("resource") != resource_key(resource)
                            or saved.get("name") != image.name or saved.get("width") != image.image.width
                            or saved.get("height") != image.image.height
                            or saved.get("sha256") != hashlib.sha256(image.data).hexdigest()
                            or rel not in e["output_hashes"] or not path.is_file() or path.read_bytes() != image.data):
                        failures.append(f"Imagem incorporada divergente: {source.name} p{number} imagem {index}")
                for (index, resource, (status_image, reason_image)), saved in zip(failed_items, recorded_failures):
                    if (saved.get("index") != index or saved.get("resource") != resource_key(resource)
                            or saved.get("status") != status_image):
                        failures.append(f"Falha de imagem registrada diverge da fonte: {source.name} p{number} imagem {index}")
                    else:
                        counts["image_failures"] += 1
                        image_gaps.append(f"{e['id']} {rel_source} p{number} imagem {index}: {status_image} — {reason_image}")
            stats = metadata.get("stats", {})
            if stats.get("embedded_images") != sum(len(p.get("embedded_images", [])) for p in pages):
                failures.append(f"Contagem de imagens incorporadas divergente: {source.name}")
            if stats.get("ocr_candidates") != sum(1 for p in pages if p.get("ocr_candidate")):
                failures.append(f"Contagem de candidatas a OCR divergente: {source.name}")
        elif e["type"] == ".ipynb":
            notebook = json.loads(source.read_text(encoding="utf-8"))
            cells = notebook["cells"]
            units = metadata["units"]
            saved = json.loads((root / "assets" / e["slug"] / "notebook-metadata.json").read_text(encoding="utf-8"))
            declared_images, expected_images = reviewed_images(root, e, review)
            if not declared_images.issubset(expected_images):
                failures.append(f"Revisão cita imagens inexistentes: {source.name}")
            if not set(review.get("reviewed_cells", [])).issubset(set(range(1, len(cells) + 1))):
                failures.append(f"Revisão cita células inexistentes: {source.name}")
            counts["notebook_cells"] += len(cells)
            if len(units) != len(cells) or len(saved["cells"]) != len(cells):
                failures.append(f"Cobertura de células divergente: {source.name}")
            for number, (cell, unit, record) in enumerate(zip(cells, units, saved["cells"]), 1):
                raw = multiline(cell.get("source", ""))
                digest = hashlib.sha256(raw.encode()).hexdigest()
                if unit["number"] != number or unit["source_sha256"] != digest or record["source_sha256"] != digest:
                    failures.append(f"Fonte da célula divergente: {source.name} c{number}")
                if cell["cell_type"] == "code" and raw.rstrip() not in unit["markdown"]:
                    failures.append(f"Código incompleto: {source.name} c{number}")
                if f'id="celula-{number:03d}"' not in body:
                    failures.append(f"Âncora de célula ausente: {source.name} c{number}")
                for name, bundle in cell.get("attachments", {}).items():
                    payloads = record.get("attachments", {}).get(name, {})
                    if set(payloads) != set(bundle):
                        failures.append(f"Anexo incompleto: {source.name} c{number} {name}")
                    for mime, value in bundle.items():
                        if mime not in payloads:
                            continue
                        path = root / "assets" / e["slug"] / payloads[mime]
                        if mime.startswith("image/"):
                            counts["saved_images"] += 1
                        if mime in {"image/png", "image/jpeg", "image/gif", "image/webp", "application/pdf"}:
                            if path.read_bytes() != base64.b64decode(multiline(value)):
                                failures.append(f"Bytes de anexo divergentes: {source.name} c{number} {mime}")
                        elif mime.endswith("json") and not isinstance(value, str):
                            if json.loads(path.read_text(encoding="utf-8")) != value:
                                failures.append(f"JSON de anexo divergente: {source.name} c{number}")
                        elif path.read_text(encoding="utf-8") != multiline(value):
                            failures.append(f"Texto de anexo divergente: {source.name} c{number} {mime}")
                outputs = cell.get("outputs", [])
                counts["saved_outputs"] += len(outputs)
                if len(record["outputs"]) != len(outputs):
                    failures.append(f"Saídas incompletas: {source.name} c{number}")
                for output, out_record in zip(outputs, record["outputs"]):
                    payloads = out_record["payload_files"]
                    if not set(output.get("data", {})).issubset(payloads):
                        failures.append(f"Representações MIME incompletas: {source.name} c{number}")
                    for mime, value in output.get("data", {}).items():
                        if mime not in payloads:
                            continue
                        path = root / "assets" / e["slug"] / payloads[mime]
                        if mime.startswith("image/"):
                            counts["saved_images"] += 1
                        if mime in {"image/png", "image/jpeg", "image/gif", "image/webp", "application/pdf"}:
                            if path.read_bytes() != base64.b64decode(multiline(value)):
                                failures.append(f"Bytes MIME divergentes: {source.name} c{number} {mime}")
                        elif mime.endswith("json") and not isinstance(value, str):
                            if json.loads(path.read_text(encoding="utf-8")) != value:
                                failures.append(f"JSON MIME divergente: {source.name} c{number}")
                        elif path.read_text(encoding="utf-8") != multiline(value):
                            failures.append(f"Texto MIME divergente: {source.name} c{number} {mime}")
                    if "text" in output:
                        if (root / "assets" / e["slug"] / payloads["stream"]).read_text(encoding="utf-8") != multiline(output["text"]):
                            failures.append(f"Stream divergente: {source.name} c{number}")
                    if "traceback" in output:
                        traceback = "\n".join(output["traceback"]) if isinstance(output["traceback"], list) else multiline(output["traceback"])
                        if (root / "assets" / e["slug"] / payloads["traceback"]).read_text(encoding="utf-8") != traceback:
                            failures.append(f"Traceback divergente: {source.name} c{number}")
        elif metadata.get("format") == "text":
            raw = source.read_text(encoding="utf-8")
            if metadata.get("text", raw) != raw or raw.rstrip() not in metadata["units"][0]["markdown"]:
                failures.append(f"Texto integral divergente: {source.name}")
            if 'id="celula-001"' not in body:
                failures.append(f"Âncora de unidade ausente: {source.name}")
            if not set(review.get("reviewed_units", [])).issubset({1}):
                failures.append(f"Revisão cita unidade inexistente: {source.name}")
        limit = e["stats"].get("pages", e["stats"].get("cells", e["stats"].get("units", 0)))
        for issue in topic_errors(e.get("topics", []), e["type"], limit):
            failures.append(f"Localização temática inválida: {e['id']}: {issue}")
    assets = root / "assets"
    if assets.is_dir():
        for path in sorted(p for p in assets.rglob("*") if p.is_file()):
            rel = path.relative_to(root).as_posix()
            if rel not in known_outputs and rel not in stale_listed:
                failures.append(f"Arquivo em assets sem registro como saída atual ou obsoleta: {rel}")
    if counts["stale_outputs"]:
        notes.append(f"Saídas obsoletas preservadas e listadas em stale_outputs: {counts['stale_outputs']}")
    for md in sorted(root.rglob("*.md")):
        relative_md = md.relative_to(root)
        if "assets" in relative_md.parts or relative_md.as_posix() in stale_listed:
            continue
        clean = outside_fences(md.read_text(encoding="utf-8"))
        for match in re.finditer(r"\]\((<[^>]+>|[^\s)]+)(?:\s+[^)]*)?\)", clean):
            target = match.group(1).strip("<>")
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc:
                continue
            path = (md.parent / unquote(parsed.path)).resolve() if parsed.path else md
            counts["local_links"] += 1
            if not path.exists():
                # Este relatório será salvo pelo próprio comando após a validação.
                if path == root / "validacao.json":
                    continue
                if path in absent_originals:
                    notes.append(f"Referência a original removido, extração preservada: {target}")
                    continue
                if unquote(parsed.path) in declared_absent or path.name in {Path(p).name for p in declared_absent}:
                    notes.append(f"Link da fonte para dependência ausente: {md.name}: {target}")
                else:
                    failures.append(f"Link local ausente: {md.relative_to(root)}: {target}")
            elif parsed.fragment and path.suffix == ".md":
                fragment = unquote(parsed.fragment)
                if f'id="{fragment}"' not in path.read_text(encoding="utf-8"):
                    failures.append(f"Âncora inexistente: {md.relative_to(root)}: {target}")
    structural_status = "passed" if not failures else "failed"
    coverage_gaps = source_gaps + image_gaps
    if require_reviewed:
        failures += review_pending + [f"Cobertura incompleta: {gap}" for gap in source_gaps]
    tools = tool_versions()
    if pdftotext_version is not None:
        tools["pdftotext"] = pdftotext_version
    return {"status": "passed" if not failures else "failed", "structural_status": structural_status,
            "coverage_status": "complete" if not coverage_gaps else "incomplete", "coverage_gaps": coverage_gaps,
            "review_status": "complete" if not review_pending else "pending", "require_reviewed": require_reviewed,
            "review_pending": sorted(set(review_pending)), "review_priority": priority, "counts": counts,
            "failures": failures, "notes": sorted(set(notes)), "tools": tools,
            "method": ("Comparação com originais, hashes, cobertura por página/célula, MIME integral, imagens "
                       "decodificáveis, links e âncoras. O texto PDF armazenado é comparado com nova execução do "
                       "mesmo comando pdftotext; a comparação pdftotext × pypdf só define prioridade de revisão. "
                       "Falhas registradas por fonte ou imagem tornam a cobertura incompleta, sem falha estrutural. "
                       "Legibilidade/conteúdo visual dependem da revisão humana registrada. Sem OCR, execução de "
                       "notebooks ou rede.")}


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Destino da extração. Padrão: pasta irmã Extracted/.")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--require-reviewed", action="store_true", help="Exigir cobertura completa, revisão humana e tópicos completos além da integridade estrutural.")
    args = parser.parse_args()
    output = args.output or args.source.expanduser().resolve().parent / "Extracted"
    result = validate(output.expanduser().resolve(), args.source.expanduser().resolve(), args.require_reviewed)
    dump(output.expanduser() / "validacao.json", result)
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(0 if result["status"] == "passed" else 1)
