#!/usr/bin/env python3
"""Prepara folhas de contato e modelos vazios; nunca certifica a revisão."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile
from urllib.parse import unquote

from PIL import Image
from extrair import dump, is_extracted, read_json, review_complete, reviewed_images
from pdf_adapter import contact_sheets, image_formats, resource_limits


def prepare(root: Path, destination: Path | None = None, document: str | None = None,
            only_pending: bool = False) -> dict:
    root = root.resolve()
    destination = (destination.resolve() if destination else
                   Path(tempfile.mkdtemp(prefix="content-extract-revisao-")))
    if destination == root or destination.is_relative_to(root):
        raise ValueError("As pranchas temporárias devem ficar fora da extração.")
    manifest = read_json(root / "manifesto.json")
    source = (root / unquote(manifest["source_directory"])).resolve()
    if destination == source or destination.is_relative_to(source):
        raise ValueError("As pranchas temporárias devem ficar fora da pasta de fontes.")
    entries = manifest["documents"]
    if document and document not in {e["slug"] for e in entries}:
        raise ValueError(f"Slug inexistente: {document}")
    result = {"destination": str(destination), "documents": [],
              "notice": "Os modelos têm cobertura vazia. Ver imagens não registra nem certifica revisão; leia, confira e preencha a revisão humana."}
    for entry in entries:
        if not entry["source_present"] or not is_extracted(entry) or (document and entry["slug"] != document):
            continue
        if only_pending and review_complete(root, entry, entry.get("review", {})) and entry.get("topics"):
            continue
        slug = entry["slug"]
        folder = destination / slug
        folder.mkdir(parents=True, exist_ok=True)
        metadata = read_json(root / "metadados" / f"{slug}.json")
        model = {"source_relative": entry["source_relative"], "source_sha256": entry["source_sha256"],
                 "title": entry["title"], "description": entry["description"], "topics": [],
                 "issues": [], "review_method": "", "reviewed_at": ""}
        item = {"id": entry["id"], "slug": slug, "source_relative": entry["source_relative"],
                "source_sha256": entry["source_sha256"], "contact_sheets": [], "images": [],
                "review_file": str(root / "revisoes" / f"{slug}.json"),
                "template": str(folder / "review-template.json")}
        if entry["type"] == ".pdf":
            contact_sheets(metadata, root / "assets" / slug, folder)
            model.update(reviewed_pages=[], pages={str(p["number"]): {"title": "", "transcription_md": "", "visual_note": "", "issues": []}
                                                   for p in metadata["pages"]})
            item["images"] = [{"page": p["number"], "path": str(root / "assets" / slug / p["image"])}
                              for p in metadata["pages"]]
            item["embedded_images"] = [{"page": page["number"], "path": str(root / "assets" / slug / image["file"])}
                                       for page in metadata["pages"] for image in page.get("embedded_images", [])]
            item["ocr_candidates"] = [p["number"] for p in metadata["pages"] if p.get("ocr_candidate")]
            item["image_failures"] = [{"page": page["number"], **failure} for page in metadata["pages"]
                                      for failure in page.get("image_failures", [])]
            if item["ocr_candidates"] or item["image_failures"]:
                item["notice"] = ("Candidatas a OCR exigem transcription_md ou issues na página; páginas com imagem "
                                  "não extraída exigem issues. Nenhum OCR é aplicado.")
        elif entry["type"] == ".ipynb":
            _, image_names = reviewed_images(root, entry, {})
            model.update(reviewed_cells=[], reviewed_images=[])
            raster, other = [], []
            for name in sorted(image_names):
                path = root / "assets" / slug / name
                item["images"].append({"filename": name, "path": str(path)})
                try:
                    with resource_limits(), Image.open(path, formats=image_formats(path)) as img:
                        img.verify()
                    raster.append({"number": len(raster) + 1, "image": name, "label": name})
                except Exception:
                    other.append(name)
            if raster:
                contact_sheets({"source": entry["source_relative"], "pages": raster}, root / "assets" / slug, folder)
            if other:
                item["images_without_contact_sheet"] = other
                item["notice"] = "Imagens sem prancha exigem visualização/renderização apropriada. A lista images preserva seus caminhos."
        else:
            model.update(reviewed_units=[])
        dump(folder / "review-template.json", model)
        item["contact_sheets"] = [str(p) for p in sorted(folder.glob("contato-*.jpg"))]
        result["documents"].append(item)
    dump(destination / "roteiro.json", result)
    return result


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--destination", type=Path, help="Diretório temporário fora da extração; padrão /tmp.")
    parser.add_argument("--document", help="Apenas o slug indicado.")
    parser.add_argument("--only-pending", action="store_true")
    args = parser.parse_args()
    print(json.dumps(prepare(args.output, args.destination, args.document, args.only_pending), ensure_ascii=False))
