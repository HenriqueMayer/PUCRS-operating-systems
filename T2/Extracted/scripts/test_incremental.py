"""Regressões do fluxo em cópias temporárias; nunca modifica o acervo."""
import base64
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

from PIL import Image
import pypdf
from pypdf import PdfReader, PdfWriter
from extrair import run, sha256
from preparar_revisao import prepare
from validar import validate


def snapshot(root):
    return {p.relative_to(root).as_posix(): (sha256(p), p.stat().st_mtime_ns)
            for p in root.rglob("*") if p.is_file()}


class Incremental(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="content-extract-incremental-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.source = self.base / "Sources"
        self.output = self.base / "Extracted"
        self.source.mkdir()

    def manifest(self):
        return json.loads((self.output / "manifesto.json").read_text(encoding="utf-8"))["documents"]

    def png(self):
        buffer = io.BytesIO()
        Image.new("RGB", (16, 12), "#aacf99").save(buffer, "PNG")
        return buffer.getvalue()

    def pdf(self, path):
        writer = PdfWriter()
        writer.add_blank_page(width=150, height=100)
        writer.add_blank_page(width=150, height=100)
        with path.open("wb") as target:
            writer.write(target)

    def pdf_with_images(self, path, inline=False):
        """Text, vector table, shared JPEG, nested form and a blank page."""
        from pypdf.generic import (ArrayObject, DictionaryObject, NameObject,
                                   NumberObject, StreamObject)
        image = io.BytesIO()
        Image.new("RGB", (24, 16), "#315a7a").save(image, "JPEG")
        data = image.getvalue()
        writer = PdfWriter()
        raster = StreamObject()
        raster.set_data(data)
        raster.update({NameObject('/Type'): NameObject('/XObject'), NameObject('/Subtype'): NameObject('/Image'),
                       NameObject('/Width'): NumberObject(24), NameObject('/Height'): NumberObject(16),
                       NameObject('/ColorSpace'): NameObject('/DeviceRGB'), NameObject('/BitsPerComponent'): NumberObject(8),
                       NameObject('/Filter'): NameObject('/DCTDecode')})
        raster_ref = writer._add_object(raster)
        font = writer._add_object(DictionaryObject({NameObject('/Type'): NameObject('/Font'),
               NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')}))
        form = StreamObject()
        form.set_data(b'q 45 0 0 30 0 0 cm /Im1 Do Q')
        form.update({NameObject('/Type'): NameObject('/XObject'), NameObject('/Subtype'): NameObject('/Form'),
                     NameObject('/BBox'): ArrayObject([NumberObject(n) for n in (0, 0, 45, 30)]),
                     NameObject('/Resources'): DictionaryObject({NameObject('/XObject'): DictionaryObject({NameObject('/Im1'): raster_ref})})})
        form_ref = writer._add_object(form)
        for nested in (False, True):
            page = writer.add_blank_page(width=180, height=160)
            page[NameObject('/Resources')] = DictionaryObject({
                NameObject('/Font'): DictionaryObject({NameObject('/F1'): font}),
                NameObject('/XObject'): DictionaryObject({NameObject('/Fm1' if nested else '/Im1'): form_ref if nested else raster_ref})})
            content = StreamObject()
            content.set_data(b'BT /F1 10 Tf 10 140 Td (Report) Tj 0 -20 Td (Region   Total) Tj 0 -15 Td (South    42) Tj ET '
                             b'10 100 m 160 100 l S 10 115 m 160 115 l S 80 85 m 80 130 l S ' +
                             (b'q 1 0 0 1 10 15 cm /Fm1 Do Q' if nested else b'q 45 0 0 30 10 15 cm /Im1 Do Q') +
                             (b' q 10 0 0 10 90 15 cm BI /W 1 /H 1 /CS /RGB /BPC 8 /F /AHx ID FF0000> EI Q'
                              if inline and nested else b''))
            page[NameObject('/Contents')] = writer._add_object(content)
        writer.add_blank_page(width=180, height=160)
        with path.open('wb') as target:
            writer.write(target)
        return data

    def pdf_document(self, path, pages, size=(180, 160)):
        """Synthetic PDF; each page spec may hold text and a JPEG of (width, height) pixels."""
        from pypdf.generic import DictionaryObject, NameObject, NumberObject, StreamObject
        writer = PdfWriter()
        font = writer._add_object(DictionaryObject({NameObject('/Type'): NameObject('/Font'),
               NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')}))
        for spec in pages:
            page = writer.add_blank_page(width=size[0], height=size[1])
            resources = {NameObject('/Font'): DictionaryObject({NameObject('/F1'): font})}
            content = b''
            if spec.get('text'):
                content += b'BT /F1 10 Tf 10 %d Td (' % (size[1] - 20) + spec['text'].encode('latin-1') + b') Tj ET '
            if spec.get('image'):
                width, height = spec['image']
                buffer = io.BytesIO()
                Image.new('RGB', (width, height), '#315a7a').save(buffer, 'JPEG')
                raster = StreamObject()
                raster.set_data(buffer.getvalue())
                raster.update({NameObject('/Type'): NameObject('/XObject'), NameObject('/Subtype'): NameObject('/Image'),
                               NameObject('/Width'): NumberObject(width), NameObject('/Height'): NumberObject(height),
                               NameObject('/ColorSpace'): NameObject('/DeviceRGB'),
                               NameObject('/BitsPerComponent'): NumberObject(8), NameObject('/Filter'): NameObject('/DCTDecode')})
                resources[NameObject('/XObject')] = DictionaryObject({NameObject('/Im1'): writer._add_object(raster)})
                content += b'q 60 0 0 40 10 15 cm /Im1 Do Q'
            page[NameObject('/Resources')] = DictionaryObject(resources)
            stream = StreamObject()
            stream.set_data(content)
            page[NameObject('/Contents')] = writer._add_object(stream)
        with path.open('wb') as target:
            writer.write(target)

    def test_default_destination_and_portable_cli(self):
        (self.source / "report.txt").write_text("Report for a presentation.\n", encoding="utf-8", newline="\n")
        completed = subprocess.run([sys.executable, '-B', str(Path(__file__).with_name('extrair.py')),
                                    '--source', str(self.source)], capture_output=True, encoding="utf-8", check=True)
        self.assertEqual(json.loads(completed.stdout)['new'], 1)
        manifest = json.loads((self.output / 'manifesto.json').read_text(encoding="utf-8"))
        self.assertEqual(manifest['title'], 'Sources')
        completed = subprocess.run([sys.executable, '-B', str(self.output / 'scripts/validar.py'),
                                    '--source', str(self.source)], capture_output=True, encoding="utf-8", check=True)
        self.assertEqual(json.loads(completed.stdout)['status'], 'passed')
        before = snapshot(self.output)
        completed = subprocess.run([sys.executable, '-B', str(self.output / 'scripts/extrair.py'),
                                    '--source', str(self.source)], capture_output=True, encoding="utf-8", check=True)
        self.assertEqual(json.loads(completed.stdout)['unchanged'], 1)
        self.assertEqual(before, snapshot(self.output))
        self.assertEqual(run(self.source, self.base / 'Custom', 'Business reports')['new'], 1)

    def test_pdf_embedded_images_and_repair(self):
        source = self.source / 'report.pdf'
        jpeg = self.pdf_with_images(source)
        original = snapshot(self.source)
        run(self.source)
        entry = self.manifest()[0]
        metadata = json.loads((self.output / 'metadados/report.json').read_text(encoding="utf-8"))
        self.assertEqual(metadata['stats'], {'pages': 3, 'page_images': 3, 'embedded_images': 2,
                                             'image_failures': 0, 'ocr_candidates': 1})
        self.assertIn('South', metadata['pages'][0]['text'])
        self.assertIn('42', metadata['pages'][0]['text'])
        paths = []
        for number, page in enumerate(metadata['pages'][:2], 1):
            image = page['embedded_images'][0]
            path = self.output / 'assets/report' / image['file']
            paths.append(path)
            self.assertEqual(path.read_bytes(), jpeg)
            self.assertEqual((image['width'], image['height']), (24, 16))
            self.assertIn(image['file'], (self.output / 'documentos/report.md').read_text(encoding="utf-8"))
            self.assertIn(path.relative_to(self.output).as_posix(), entry['output_hashes'])
        self.assertIsInstance(metadata['pages'][1]['embedded_images'][0]['resource'], list)
        result = validate(self.output, self.source)
        self.assertEqual(result['status'], 'passed', result['failures'])
        self.assertEqual(result['counts']['embedded_pdf_images'], 2)
        summary = prepare(self.output, self.base / 'review')
        self.assertEqual(len(summary['documents'][0]['embedded_images']), 2)
        before = snapshot(self.output)
        run(self.source)
        self.assertEqual(before, snapshot(self.output))
        paths[0].write_bytes(b'corrupted')
        self.assertEqual(validate(self.output, self.source)['status'], 'failed')
        self.assertEqual(run(self.source)['repaired'], 1)
        self.assertEqual(paths[0].read_bytes(), jpeg)
        paths[1].unlink()
        self.assertEqual(run(self.source)['repaired'], 1)
        self.assertEqual(validate(self.output, self.source)['status'], 'passed')
        self.assertEqual(original, snapshot(self.source))

    def test_pdf_legacy_cache_upgrade_preserves_identity_and_review(self):
        source = self.source / 'report.pdf'
        self.pdf_with_images(source)
        run(self.source)
        review = {'source_sha256': sha256(source), 'reviewed_pages': [1, 2, 3],
                  'pages': {'3': {'issues': ['Página sem texto e sem conteúdo visível no render.']}},
                  'topics': [{'topic': 'Report', 'pages': [1, 2, 3]}]}
        (self.output / 'revisoes/report.json').write_text(json.dumps(review), encoding="utf-8", newline="\n")
        run(self.source)
        path = self.output / 'metadados/report.json'
        legacy = json.loads(path.read_text(encoding="utf-8"))
        legacy.pop('pdf_extraction_version')
        legacy['stats'].pop('embedded_images')
        for page in legacy['pages']:
            page.pop('embedded_images')
        path.write_text(json.dumps(legacy), encoding="utf-8", newline="\n")
        manifest_path = self.output / 'manifesto.json'
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest['documents'][0]['output_hashes']['metadados/report.json'] = sha256(path)
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8", newline="\n")
        renders = {p.name: (sha256(p), p.stat().st_mtime_ns) for p in (self.output / 'assets/report').glob('pagina-*.png')}
        self.assertEqual(run(self.source)['repaired'], 1)
        entry = self.manifest()[0]
        self.assertEqual(entry['id'], 'DOC-001')
        self.assertEqual(entry['review'], review)
        self.assertEqual(renders, {p.name: (sha256(p), p.stat().st_mtime_ns) for p in (self.output / 'assets/report').glob('pagina-*.png')})
        self.assertEqual(validate(self.output, self.source, True)['status'], 'passed')

    def test_pdf_asset_omission_is_detected_from_source(self):
        self.pdf_with_images(self.source / 'report.pdf')
        run(self.source)
        path = self.output / 'metadados/report.json'
        metadata = json.loads(path.read_text(encoding="utf-8"))
        metadata['pages'][0]['embedded_images'] = []
        metadata['stats']['embedded_images'] = 1
        path.write_text(json.dumps(metadata), encoding="utf-8", newline="\n")
        manifest_path = self.output / 'manifesto.json'
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest['documents'][0]['output_hashes']['metadados/report.json'] = sha256(path)
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8", newline="\n")
        result = validate(self.output, self.source)
        self.assertEqual(result['status'], 'failed')
        self.assertTrue(any('Imagens incorporadas incompletas' in s for s in result['failures']))

    def test_pdf_inline_resource_is_not_repeated_in_form_traversal(self):
        self.pdf_with_images(self.source / 'inline.pdf', inline=True)
        run(self.source)
        metadata = json.loads((self.output / 'metadados/inline.json').read_text(encoding="utf-8"))
        self.assertEqual(metadata['stats']['embedded_images'], 3)
        second = metadata['pages'][1]['embedded_images']
        self.assertEqual(len(second), 2)
        self.assertEqual(len([i for i in second if i['resource'] == '~0~']), 1)
        result = validate(self.output, self.source)
        self.assertEqual(result['status'], 'passed', result['failures'])
        self.assertEqual(result['counts']['embedded_pdf_images'], 3)

    def test_new_changed_noop_and_missing(self):
        first = self.source / "primeiro.md"
        first.write_text("# Primeiro\nConteúdo inicial.\n", encoding="utf-8", newline="\n")
        self.assertEqual(run(self.source, self.output)["new"], 1)
        before = snapshot(self.output)
        first.touch()
        self.assertEqual(run(self.source, self.output)["unchanged"], 1)
        self.assertEqual(before, snapshot(self.output))
        (self.source / "novo.md").write_text("Novo conteúdo", encoding="utf-8", newline="\n")
        self.assertEqual(run(self.source, self.output)["new"], 1)
        ids = {e["source_relative"]: e["id"] for e in self.manifest()}
        first.write_text("Primeiro alterado", encoding="utf-8", newline="\n")
        self.assertEqual(run(self.source, self.output)["changed"], 1)
        self.assertEqual(ids, {e["source_relative"]: e["id"] for e in self.manifest()})
        first.unlink()
        self.assertEqual(run(self.source, self.output)["absent"], 1)
        self.assertTrue((self.output / "documentos/primeiro.md").exists())
        self.assertEqual(validate(self.output, self.source)["status"], "passed")
        first.write_text("Primeiro alterado", encoding="utf-8", newline="\n")
        self.assertEqual(run(self.source, self.output)["unchanged"], 2)
        self.assertEqual(ids, {e["source_relative"]: e["id"] for e in self.manifest()})

    def test_review_and_corrupted_metadata(self):
        source = self.source / "notas.md"
        source.write_text("Notas integrais.", encoding="utf-8", newline="\n")
        run(self.source, self.output)
        review = self.output / "revisoes/notas.json"
        review.write_text(json.dumps({"source_sha256": sha256(source), "title": "Título revisado"}), encoding="utf-8", newline="\n")
        self.assertEqual(run(self.source, self.output)["recomposed"], 1)
        self.assertIn("Título revisado", (self.output / "documentos/notas.md").read_text(encoding="utf-8"))
        original = (self.output / "documentos/notas.md").read_bytes()
        (self.output / "documentos/notas.md").write_text("corrompido", encoding="utf-8", newline="\n")
        self.assertEqual(run(self.source, self.output)["repaired"], 1)
        self.assertEqual(original, (self.output / "documentos/notas.md").read_bytes())
        (self.output / "metadados/notas.json").write_text("{", encoding="utf-8", newline="\n")
        self.assertEqual(run(self.source, self.output)["repaired"], 1)
        (self.output / "documentos/notas.md").write_bytes(b"\xff\xfe")
        self.assertEqual(run(self.source, self.output)["repaired"], 1)
        self.assertEqual(validate(self.output, self.source)["status"], "passed")

    def test_existing_index_requires_its_manifest(self):
        (self.source / "notas.md").write_text("Notas", encoding="utf-8", newline="\n")
        run(self.source, self.output)
        (self.output / "manifesto.json").unlink()
        before = snapshot(self.output)
        with self.assertRaisesRegex(ValueError, "falta manifesto"):
            run(self.source, self.output)
        self.assertEqual(before, snapshot(self.output))

    def test_dependencies_links_and_asset_repair(self):
        png = self.png()
        notebook = {"nbformat": 4, "nbformat_minor": 5, "metadata": {}, "cells": [
            {"cell_type": "markdown", "metadata": {}, "source": "[Dados](novo.csv)"},
            {"cell_type": "code", "metadata": {}, "execution_count": 1, "source": "print('salvo')",
             "outputs": [{"output_type": "display_data", "metadata": {},
                          "data": {"image/png": base64.b64encode(png).decode(), "text/plain": "Figura salva"}}]},
        ]}
        (self.source / "exemplo.ipynb").write_text(json.dumps(notebook), encoding="utf-8", newline="\n")
        run(self.source, self.output)
        assets_before = snapshot(self.output / "assets/exemplo")
        self.assertFalse(self.manifest()[0]["dependencies"][0]["exists"])
        (self.source / "novo.csv").write_text("x,y\n1,2\n", encoding="utf-8", newline="\n")
        result = run(self.source, self.output)
        self.assertEqual((result["new"], result["recomposed"]), (1, 1))
        self.assertTrue(self.manifest()[0]["dependencies"][0]["exists"])
        self.assertIn("../../Sources/novo.csv", (self.output / "documentos/exemplo.md").read_text(encoding="utf-8"))
        self.assertEqual(assets_before, snapshot(self.output / "assets/exemplo"))
        asset = next((self.output / "assets/exemplo").glob("*.png"))
        asset.write_bytes(b"corrompido")
        self.assertEqual(run(self.source, self.output)["repaired"], 1)
        self.assertEqual(asset.read_bytes(), png)
        text_asset = next((self.output / "assets/exemplo").glob("*text-plain.txt"))
        text_asset.write_bytes(b"\xff\xfe")
        self.assertEqual(run(self.source, self.output)["repaired"], 1)
        self.assertEqual(validate(self.output, self.source)["status"], "passed")
        (self.source / "novo.csv").unlink()
        self.assertEqual(run(self.source, self.output)["recomposed"], 1)
        self.assertFalse(self.manifest()[0]["dependencies"][0]["exists"])

    def test_pdf_changed_invalidates_review_and_recovers_bad_cache(self):
        source = self.source / "simulado.pdf"
        self.pdf(source)
        run(self.source, self.output)
        review = self.output / "revisoes/simulado.json"
        review.write_text(json.dumps({"source_sha256": sha256(source), "reviewed_pages": [1, 2]}), encoding="utf-8", newline="\n")
        self.assertEqual(run(self.source, self.output)["recomposed"], 1)
        before = snapshot(self.output)
        self.assertEqual(run(self.source, self.output)["unchanged"], 1)
        self.assertEqual(before, snapshot(self.output))
        writer = PdfWriter()
        writer.clone_document_from_reader(PdfReader(source))
        writer.add_metadata({"/Title": "Cópia temporária modificada"})
        buf = io.BytesIO()
        writer.write(buf)
        source.write_bytes(buf.getvalue())
        (self.output / "metadados/simulado.json").write_text("[]", encoding="utf-8", newline="\n")
        self.assertEqual(run(self.source, self.output)["changed"], 1)
        entry = self.manifest()[0]
        self.assertEqual(entry["id"], "DOC-001")
        self.assertEqual(entry["review"], {})
        self.assertEqual(entry["review_status"], "Revisão visual pendente")
        self.assertEqual(validate(self.output, self.source)["status"], "passed")

    def test_subdirectories_collisions_and_review_binding(self):
        (self.source / "Grupo 1").mkdir()
        (self.source / "grupo-1").mkdir()
        for folder in ("Grupo 1", "grupo-1"):
            (self.source / folder / "Aula.md").write_text(folder, encoding="utf-8", newline="\n")
        run(self.source, self.output)
        entries = self.manifest()
        self.assertEqual(len({e["slug"] for e in entries}), 2)
        self.assertEqual(len({e["id"] for e in entries}), 2)
        first = entries[0]
        review = {"source_sha256": first["source_sha256"], "source_relative": first["source_relative"],
                  "title": "Título localizado", "reviewed_units": [1], "topics": [{"topic": "Leitura", "cells": [1]}]}
        (self.output / "revisoes" / f"{first['slug']}.json").write_text(json.dumps(review), encoding="utf-8", newline="\n")
        self.assertEqual(run(self.source, self.output)["recomposed"], 1)
        second = self.manifest()[1]
        self.assertEqual(second["review"], {})
        wrong = {**review, "source_relative": second["source_relative"]}
        (self.output / "revisoes" / f"{first['slug']}.json").write_text(json.dumps(wrong), encoding="utf-8", newline="\n")
        run(self.source, self.output)
        self.assertEqual(self.manifest()[0]["review"], {})

    def test_unicode_source_links_are_portable_and_idempotent(self):
        folder = self.source / "Análises & receitas"
        folder.mkdir()
        (folder / "Recepção.md").write_text("Preço e descrição.\n", encoding="utf-8", newline="\n")
        run(self.source, self.output)
        entry = self.manifest()[0]
        body = (self.output / "documentos" / f"{entry['slug']}.md").read_text(encoding="utf-8")
        self.assertIn("An%C3%A1lises%20%26%20receitas/Recep%C3%A7%C3%A3o.md", body)
        self.assertNotIn("%5C", body)
        self.assertIn("Preço e descrição.", body)
        self.assertEqual(validate(self.output, self.source)["status"], "passed")
        before = snapshot(self.output)
        run(self.source, self.output)
        self.assertEqual(before, snapshot(self.output))

    def test_manifest_config_overlap_and_unsupported(self):
        (self.source / "nota.md").write_text("Anotações", encoding="utf-8", newline="\n")
        for target in (self.source, self.source / "Index", self.base):
            with self.assertRaisesRegex(ValueError, "sobrepostos"):
                run(self.source, target)
        (self.source / "sem-adaptador.docx").write_bytes(b"arbitrary")
        self.assertEqual(run(self.source, self.output)["failed"], 1)
        entry = next(e for e in self.manifest() if e["source_relative"] == "sem-adaptador.docx")
        self.assertEqual((entry["status"], entry["source_sha256"]),
                         ("formato sem adaptador", sha256(self.source / "sem-adaptador.docx")))
        self.assertIn("sem adaptador", entry["reason"])
        self.assertFalse((self.output / "documentos" / f"{entry['slug']}.md").exists())
        result = validate(self.output, self.source)
        self.assertEqual((result["structural_status"], result["coverage_status"]), ("passed", "incomplete"))
        (self.source / "sem-adaptador.docx").unlink()
        run(self.source, self.output, "Relatórios profissionais", "UTC")
        before = snapshot(self.output)
        run(self.source, self.output)
        self.assertEqual(before, snapshot(self.output))
        manifest = json.loads((self.output / "manifesto.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["title"], "Relatórios profissionais")
        self.assertEqual(manifest["timezone"], "UTC")
        self.assertIn("Relatórios profissionais", (self.output / "index.md").read_text(encoding="utf-8"))

    def test_symbolic_links_outside_source_are_recorded_not_followed(self):
        (self.source / "nota.md").write_text("Anotações", encoding="utf-8", newline="\n")
        outside = self.base / "privado.txt"
        outside.write_text("conteúdo externo secreto", encoding="utf-8", newline="\n")
        external_dir = self.base / "Externa"
        external_dir.mkdir()
        (external_dir / "oculto.txt").write_text("conteúdo externo secreto", encoding="utf-8", newline="\n")
        try:
            (self.source / "link.txt").symlink_to(outside)
        except (OSError, NotImplementedError):
            self.skipTest("Links simbólicos indisponíveis neste sistema")
        (self.source / "pasta").symlink_to(external_dir, target_is_directory=True)
        (self.source / "quebrado.txt").symlink_to(self.base / "ausente.txt")
        result = run(self.source, self.output)
        self.assertEqual((result["new"], result["failed"]), (1, 3))
        entries = {e["source_relative"]: e for e in self.manifest()}
        for name in ("link.txt", "pasta", "quebrado.txt"):
            self.assertEqual(entries[name]["status"], "link não seguido")
            self.assertIsNone(entries[name]["source_sha256"])
            self.assertEqual(entries[name]["output_hashes"], {})
            self.assertFalse((self.output / "assets" / entries[name]["slug"]).exists())
        for path in self.output.rglob("*"):
            if path.is_file() and path.suffix in {".md", ".json"}:
                self.assertNotIn("externo secreto", path.read_text(encoding="utf-8"))
        result = validate(self.output, self.source)
        self.assertEqual((result["structural_status"], result["coverage_status"]), ("passed", "incomplete"))
        self.assertTrue(any("link.txt" in gap for gap in result["coverage_gaps"]))
        self.assertEqual(validate(self.output, self.source, True)["status"], "failed")
        before = snapshot(self.output)
        run(self.source, self.output)
        self.assertEqual(before, snapshot(self.output))
        ids = {name: entries[name]["id"] for name in entries}
        for name in ("link.txt", "pasta", "quebrado.txt"):
            (self.source / name).unlink()
        (self.source / "sub").mkdir()
        (self.source / "sub" / "a.txt").write_text("Texto interno", encoding="utf-8", newline="\n")
        (self.source / "atalho").symlink_to(self.source / "sub", target_is_directory=True)
        self.assertEqual(run(self.source, self.output)["new"], 1)
        self.assertEqual({e["source_relative"] for e in self.manifest() if e["source_present"]}, {"nota.md", "sub/a.txt"})
        self.assertEqual(validate(self.output, self.source)["status"], "passed")
        (self.source / "link.txt").symlink_to(outside)
        result = validate(self.output, self.source)
        self.assertEqual(result["status"], "failed")
        self.assertTrue(any("link.txt" in failure for failure in result["failures"]))
        run(self.source, self.output)
        relinked = next(e for e in self.manifest() if e["source_relative"] == "link.txt")
        self.assertEqual((relinked["id"], relinked["status"], relinked["source_present"]),
                         (ids["link.txt"], "link não seguido", True))

    def test_full_review_gate_and_templates_are_non_mutating(self):
        source = self.source / "texto.md"
        source.write_text("# Texto\nFonte integral.\n", encoding="utf-8", newline="\n")
        run(self.source, self.output)
        result = validate(self.output, self.source, require_reviewed=True)
        self.assertEqual(result["structural_status"], "passed")
        self.assertEqual(result["status"], "failed")
        review = {"source_sha256": sha256(source), "source_relative": "texto.md", "reviewed_units": [1],
                  "title": "Texto", "description": "Fonte integral.", "topics": [{"topic": "Texto", "cells": [1]}]}
        (self.output / "revisoes/texto.json").write_text(json.dumps(review), encoding="utf-8", newline="\n")
        run(self.source, self.output)
        self.assertEqual(validate(self.output, self.source, True)["status"], "passed")
        before = snapshot(self.output)
        summary = prepare(self.output, self.base / "revisao")
        self.assertEqual(before, snapshot(self.output))
        self.assertEqual(json.loads(Path(summary["documents"][0]["template"]).read_text(encoding="utf-8"))["reviewed_units"], [])
        self.assertEqual(prepare(self.output, self.base / "pendentes", only_pending=True)["documents"], [])
        with self.assertRaisesRegex(ValueError, "pasta de fontes"):
            prepare(self.output, self.source / "pranchas")

    def test_explicit_initial_order_and_persisted_config(self):
        for name in ("Aula2.md", "Aula10.md"):
            (self.source / name).write_text(name, encoding="utf-8", newline="\n")
        order = ["Aula10.md", "Aula2.md"]
        run(self.source, self.output, title="Acervo", timezone="UTC", order=order)
        entries = self.manifest()
        self.assertEqual([e["source_relative"] for e in entries], order)
        before = snapshot(self.output)
        run(self.source, self.output)
        self.assertEqual(before, snapshot(self.output))
        manifest = json.loads((self.output / "manifesto.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["order"], order)
        self.assertEqual(manifest["title"], "Acervo")
        (self.source / "Novo.md").write_text("Novo", encoding="utf-8", newline="\n")
        run(self.source, self.output, order=["Novo.md", "Aula2.md", "Aula10.md"])
        updated = self.manifest()
        self.assertEqual([(e["id"], e["source_relative"]) for e in updated[:2]],
                         [(e["id"], e["source_relative"]) for e in entries])
        self.assertEqual(updated[2]["source_relative"], "Novo.md")

    def test_invalid_topic_schemas_fail_without_review_gate(self):
        source = self.source / "texto.md"
        source.write_text("Texto integral", encoding="utf-8", newline="\n")
        self.pdf(self.source / "aula.pdf")
        run(self.source, self.output)
        for filename, invalid in [
            ("texto.md", {"topic": "Texto", "units": [1]}),
            ("texto.md", {"topic": "Texto", "cells": []}),
            ("texto.md", {"topic": "Texto", "cells": [2]}),
            ("texto.md", {"topic": "Texto", "cells": [True]}),
            ("texto.md", {"topic": "", "cells": [1]}),
            ("aula.pdf", {"topic": "Página", "cells": [1]}),
            ("aula.pdf", {"topic": "Página", "pages": [0]}),
        ]:
            with self.subTest(filename=filename, invalid=invalid):
                manifest_path = self.output / "manifesto.json"
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                entry = next(e for e in manifest["documents"] if e["source_relative"] == filename)
                review = {"source_sha256": entry["source_sha256"], "topics": [invalid]}
                review_path = self.output / "revisoes" / f"{entry['slug']}.json"
                review_path.write_text(json.dumps(review), encoding="utf-8", newline="\n")
                before = snapshot(self.output)
                with self.assertRaisesRegex(ValueError, "Revisão temática inválida"):
                    run(self.source, self.output)
                self.assertEqual(before, snapshot(self.output))
                entry["topics"] = [invalid]
                manifest_path.write_text(json.dumps(manifest), encoding="utf-8", newline="\n")
                result = validate(self.output, self.source)
                self.assertEqual(result["status"], "failed")
                self.assertTrue(any("Localização temática inválida" in issue for issue in result["failures"]))
                entry["topics"] = []
                manifest_path.write_text(json.dumps(manifest), encoding="utf-8", newline="\n")
                review_path.unlink()

    def test_notebook_all_mime_and_attachments_without_execution(self):
        image = base64.b64encode(self.png()).decode()
        source = self.source / "completo.ipynb"
        source.write_text(json.dumps({"nbformat": 4, "nbformat_minor": 5, "metadata": {"language_info": {"name": "python"}}, "cells": [
            {"cell_type": "markdown", "metadata": {}, "source": "# Figura\n![anexo](attachment:fig.png)",
             "attachments": {"fig.png": {"image/png": image, "text/plain": "Alternativa salva"}}},
            {"cell_type": "code", "metadata": {}, "source": "raise RuntimeError('NÃO EXECUTAR')\n```", "execution_count": 7,
             "outputs": [{"output_type": "display_data", "metadata": {}, "data": {"image/png": image, "text/plain": ["uma\n", "saída"],
                  "text/html": "<script>raise('não executar')</script>", "application/json": [1, {"a": 2}],
                  "application/javascript": "alert('não executar')"}},
                 {"output_type": "stream", "name": "stderr", "text": ["aviso\n", "salvo\n"]},
                 {"output_type": "error", "ename": "RuntimeError", "evalue": "Erro salvo", "traceback": ["linha 1", "linha 2"]}]},
            {"cell_type": "raw", "metadata": {"format": "text"}, "source": "Fonte bruta\n"},
            {"cell_type": "markdown", "metadata": {}, "source": ""}]}), encoding="utf-8", newline="\n")
        run(self.source, self.output)
        entry = self.manifest()[0]
        self.assertEqual((entry["stats"]["cells"], entry["stats"]["outputs"], entry["stats"]["images"]), (4, 3, 2))
        self.assertEqual(validate(self.output, self.source)["status"], "passed")
        filenames = sorted(p.name for p in (self.output / "assets/completo").glob("*.png"))
        review = {"source_sha256": sha256(source), "reviewed_cells": [1, 2, 3, 4], "reviewed_images": filenames[:1],
                  "topics": [{"topic": "Exemplo", "cells": [1, 2, 3, 4]}]}
        (self.output / "revisoes/completo.json").write_text(json.dumps(review), encoding="utf-8", newline="\n")
        run(self.source, self.output)
        self.assertEqual(validate(self.output, self.source, True)["status"], "failed")
        review["reviewed_images"] = filenames
        (self.output / "revisoes/completo.json").write_text(json.dumps(review), encoding="utf-8", newline="\n")
        run(self.source, self.output)
        self.assertEqual(validate(self.output, self.source, True)["status"], "passed")
        before = snapshot(self.output)
        summary = prepare(self.output, self.base / "figuras")
        self.assertTrue(summary["documents"][0]["contact_sheets"])
        self.assertEqual(before, snapshot(self.output))

    def test_mixed_folder_records_failures_and_continues(self):
        (self.source / "nota.md").write_text("# Nota\nTexto.\n", encoding="utf-8", newline="\n")
        (self.source / "proposta.docx").write_bytes(b"PK arbitrary")
        (self.source / "dados.csv").write_bytes("nome;valor\nJosé;1\n".encode("latin-1"))
        (self.source / "quebrado.ipynb").write_text("{\"cells\": [", encoding="utf-8", newline="\n")
        (self.source / "lista.ipynb").write_text("[]", encoding="utf-8", newline="\n")
        self.pdf_document(self.source / "relatorio.pdf", [{"text": "Resumo"}])
        original = snapshot(self.source)
        result = run(self.source, self.output)
        self.assertEqual((result["new"], result["failed"], result["excluded"]), (2, 4, 0))
        entries = {e["source_relative"]: e for e in self.manifest()}
        self.assertEqual({rel: e["status"] for rel, e in entries.items()},
                         {"dados.csv": "não UTF-8", "lista.ipynb": "malformado", "nota.md": "extraído",
                          "proposta.docx": "formato sem adaptador", "quebrado.ipynb": "malformado",
                          "relatorio.pdf": "extraído"})
        self.assertEqual(sorted(e["id"] for e in entries.values()), [f"DOC-{n:03d}" for n in range(1, 7)])
        self.assertIn("linha 1", entries["quebrado.ipynb"]["reason"])
        index = (self.output / "index.md").read_text(encoding="utf-8")
        report = (self.output / "conferencia.md").read_text(encoding="utf-8")
        for rel in ("dados.csv", "lista.ipynb", "proposta.docx", "quebrado.ipynb"):
            self.assertIn(entries[rel]["id"], index)
            self.assertIn(entries[rel]["reason"], report)
        self.assertIn("Fontes não extraídas e exclusões", index)
        result = validate(self.output, self.source)
        self.assertEqual((result["status"], result["coverage_status"], len(result["coverage_gaps"])),
                         ("passed", "incomplete", 4))
        self.assertEqual(result["counts"]["failed_sources"], 4)
        gated = validate(self.output, self.source, True)
        self.assertEqual((gated["structural_status"], gated["status"]), ("passed", "failed"))
        self.assertTrue(any(f.startswith("Cobertura incompleta") for f in gated["failures"]))
        before = snapshot(self.output)
        run(self.source, self.output)
        self.assertEqual(before, snapshot(self.output))
        result = run(self.source, self.output, exclude=["*.docx", "*.ipynb"])
        self.assertEqual((result["failed"], result["excluded"]), (1, 3))
        manifest = json.loads((self.output / "manifesto.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["exclude"], ["*.docx", "*.ipynb"])
        self.assertEqual(manifest["excluded"], ["lista.ipynb", "proposta.docx", "quebrado.ipynb"])
        self.assertEqual(next(e for e in manifest["documents"] if e["source_relative"] == "proposta.docx")["status"], "excluído")
        self.assertEqual(run(self.source, self.output)["excluded"], 3)
        self.assertEqual(validate(self.output, self.source)["structural_status"], "passed")
        result = run(self.source, self.output, exclude=[])
        self.assertEqual((result["failed"], result["excluded"]), (4, 0))
        self.assertEqual({e["source_relative"]: e["id"] for e in self.manifest()},
                         {rel: e["id"] for rel, e in entries.items()})
        self.assertEqual(original, snapshot(self.source))

    def test_non_utf8_csv_is_recorded_without_conversion(self):
        source = self.source / "dados.csv"
        latin = "cidade;valor\nSão Paulo;3\n".encode("latin-1")
        source.write_bytes(latin)
        (self.source / "nota.txt").write_text("Texto", encoding="utf-8", newline="\n")
        self.assertEqual(run(self.source, self.output)["failed"], 1)
        entry = next(e for e in self.manifest() if e["source_relative"] == "dados.csv")
        self.assertEqual((entry["status"], entry["source_sha256"], entry["source_bytes"]),
                         ("não UTF-8", sha256(source), len(latin)))
        self.assertIn("0xe3", entry["reason"])
        self.assertFalse((self.output / "documentos" / f"{entry['slug']}.md").exists())
        self.assertEqual(source.read_bytes(), latin)
        source.write_text("cidade;valor\nSão Paulo;3\n", encoding="utf-8", newline="\n")
        result = run(self.source, self.output)
        fixed = next(e for e in self.manifest() if e["source_relative"] == "dados.csv")
        self.assertEqual((result["changed"], result["failed"], fixed["id"], fixed["status"]),
                         (1, 0, entry["id"], "extraído"))
        self.assertNotIn("reason", fixed)
        self.assertEqual(validate(self.output, self.source)["coverage_status"], "complete")

    def test_shrinking_pdf_lists_stale_outputs_without_deleting(self):
        source = self.source / "aula.pdf"
        five = [{"text": f"Pagina {n}"} for n in range(1, 5)] + [{"text": "Pagina 5", "image": (24, 16)}]
        self.pdf_document(source, five)
        run(self.source, self.output)
        assets = self.output / "assets/aula"
        old = {p.relative_to(self.output).as_posix(): p.stat().st_mtime_ns
               for p in (assets / "pagina-004.png", assets / "pagina-005.png",
                         assets / "imagens/pagina-005-imagem-001.jpg")}
        self.pdf_document(source, five[:3])
        self.assertEqual(run(self.source, self.output)["changed"], 1)
        entry = self.manifest()[0]
        self.assertEqual(entry["stale_outputs"], sorted(old))
        self.assertFalse(set(old) & set(entry["output_hashes"]))
        self.assertEqual(old, {rel: (self.output / rel).stat().st_mtime_ns for rel in old})
        self.assertNotIn('id="pagina-004"', (self.output / "documentos/aula.md").read_text(encoding="utf-8"))
        self.assertIn("stale_outputs", (self.output / "index.md").read_text(encoding="utf-8"))
        result = validate(self.output, self.source)
        self.assertEqual(result["status"], "passed", result["failures"])
        self.assertEqual(result["counts"]["stale_outputs"], 3)
        before = snapshot(self.output)
        run(self.source, self.output)
        self.assertEqual(before, snapshot(self.output))
        (assets / "desconhecido.png").write_bytes(self.png())
        result = validate(self.output, self.source)
        self.assertEqual(result["status"], "failed")
        self.assertTrue(any("desconhecido.png" in f for f in result["failures"]))
        (assets / "desconhecido.png").unlink()
        self.pdf_document(source, five)
        run(self.source, self.output)
        self.assertEqual(self.manifest()[0]["stale_outputs"], [])
        self.assertEqual(validate(self.output, self.source)["status"], "passed")

    def test_image_only_page_is_ocr_candidate_and_gates_review(self):
        source = self.source / "folheto.pdf"
        self.pdf_document(source, [{"text": "Capa do folheto"}, {"image": (24, 16)}])
        run(self.source, self.output)
        metadata = json.loads((self.output / "metadados/folheto.json").read_text(encoding="utf-8"))
        self.assertEqual([p["ocr_candidate"] for p in metadata["pages"]], [False, True])
        self.assertEqual(metadata["stats"]["ocr_candidates"], 1)
        self.assertIn("Candidata a OCR", (self.output / "documentos/folheto.md").read_text(encoding="utf-8"))
        self.assertIn("candidatas a OCR", (self.output / "index.md").read_text(encoding="utf-8"))
        self.assertIn("(pendente)", (self.output / "conferencia.md").read_text(encoding="utf-8"))
        result = validate(self.output, self.source)
        self.assertEqual(result["status"], "passed", result["failures"])
        self.assertEqual([(p["page"], p["priority"]) for p in result["review_priority"]], [(2, "alta")])
        review = {"source_sha256": sha256(source), "reviewed_pages": [1, 2],
                  "topics": [{"topic": "Folheto", "pages": [1, 2]}]}
        (self.output / "revisoes/folheto.json").write_text(json.dumps(review), encoding="utf-8", newline="\n")
        run(self.source, self.output)
        gated = validate(self.output, self.source, True)
        self.assertEqual(gated["status"], "failed")
        self.assertTrue(any("candidata a OCR" in item for item in gated["review_pending"]))
        self.assertEqual(self.manifest()[0]["review_status"], "Revisão visual pendente")
        review["pages"] = {"2": {"transcription_md": "Retângulo azul sem texto legível."}}
        (self.output / "revisoes/folheto.json").write_text(json.dumps(review), encoding="utf-8", newline="\n")
        run(self.source, self.output)
        self.assertEqual(validate(self.output, self.source, True)["status"], "passed")
        self.assertEqual(self.manifest()[0]["review_status"], "Conferido visualmente")
        self.assertIn("(registrada na revisão)", (self.output / "conferencia.md").read_text(encoding="utf-8"))

    def test_decompression_bomb_is_recorded_per_image(self):
        source = self.source / "grande.pdf"
        self.pdf_document(source, [{"text": "Mapa", "image": (3000, 3000)}], size=(200, 100))
        with mock.patch.dict(os.environ, {"CONTENT_EXTRACT_MAX_IMAGE_PIXELS": "4000000"}):
            result = run(self.source, self.output)
            self.assertEqual((result["new"], result["failed"]), (1, 0))
            metadata = json.loads((self.output / "metadados/grande.json").read_text(encoding="utf-8"))
            page = metadata["pages"][0]
            self.assertEqual(page["embedded_images"], [])
            self.assertEqual([(f["index"], f["resource"], f["status"]) for f in page["image_failures"]],
                             [(1, "/Im1", "limite de recurso")])
            self.assertIn("DecompressionBomb", page["image_failures"][0]["reason"])
            self.assertEqual(metadata["limits"]["max_image_pixels"], 4000000)
            self.assertFalse((self.output / "assets/grande/imagens").exists())
            result = validate(self.output, self.source)
            self.assertEqual((result["status"], result["coverage_status"]), ("passed", "incomplete"), result["failures"])
            self.assertEqual(result["counts"]["image_failures"], 1)
            review = {"source_sha256": sha256(source), "reviewed_pages": [1],
                      "topics": [{"topic": "Mapa", "pages": [1]}]}
            (self.output / "revisoes/grande.json").write_text(json.dumps(review), encoding="utf-8", newline="\n")
            run(self.source, self.output)
            self.assertEqual(validate(self.output, self.source, True)["status"], "failed")
            review["pages"] = {"1": {"issues": ["Imagem incorporada acima do limite de pixels; conferida no render."]}}
            (self.output / "revisoes/grande.json").write_text(json.dumps(review), encoding="utf-8", newline="\n")
            run(self.source, self.output)
            self.assertEqual(validate(self.output, self.source, True)["status"], "passed")

    @unittest.skipIf(os.name == "nt", "Executável sintético depende de sh")
    def test_subprocess_timeout_is_recorded_and_retried(self):
        self.pdf_document(self.source / "lento.pdf", [{"text": "Lento"}])
        (self.source / "nota.md").write_text("Nota", encoding="utf-8", newline="\n")
        slow = self.base / "pdftoppm-lento"
        slow.write_text("#!/bin/sh\nexec sleep 5\n", encoding="utf-8", newline="\n")
        slow.chmod(0o755)
        started = time.monotonic()
        with mock.patch.dict(os.environ, {"CONTENT_EXTRACT_PDFTOPPM": str(slow), "CONTENT_EXTRACT_TIMEOUT": "1"}):
            result = run(self.source, self.output)
        self.assertLess(time.monotonic() - started, 4.5)
        self.assertEqual((result["new"], result["failed"]), (1, 1))
        entry = next(e for e in self.manifest() if e["source_relative"] == "lento.pdf")
        self.assertEqual((entry["status"], entry["reason"]), ("limite de recurso", "pdftoppm excedeu o tempo limite de 1 s."))
        self.assertEqual(validate(self.output, self.source)["coverage_status"], "incomplete")
        result = run(self.source, self.output)
        retried = next(e for e in self.manifest() if e["source_relative"] == "lento.pdf")
        self.assertEqual((result["repaired"], retried["id"], retried["status"]), (1, entry["id"], "extraído"))
        self.assertEqual(validate(self.output, self.source)["coverage_status"], "complete")

    def test_manifest_v1_migration_preserves_ids_and_slugs(self):
        (self.source / "nota.md").write_text("Nota", encoding="utf-8", newline="\n")
        self.pdf_document(self.source / "aula.pdf", [{"text": "Aula"}])
        run(self.source, self.output)
        path = self.output / "manifesto.json"
        manifest = json.loads(path.read_text(encoding="utf-8"))
        identity = [(e["id"], e["slug"], e["source_relative"]) for e in manifest["documents"]]
        manifest["schema_version"] = 1
        for key in ("exclude", "excluded"):
            manifest.pop(key)
        for entry in manifest["documents"]:
            entry.pop("status")
            entry.pop("stale_outputs")
        path.write_text(json.dumps(manifest), encoding="utf-8", newline="\n")
        self.assertEqual(validate(self.output, self.source)["status"], "passed")
        self.assertEqual(run(self.source, self.output)["unchanged"], 2)
        migrated = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(migrated["schema_version"], 2)
        self.assertEqual([(e["id"], e["slug"], e["source_relative"]) for e in migrated["documents"]], identity)
        self.assertEqual({e["status"] for e in migrated["documents"]}, {"extraído"})
        before = snapshot(self.output)
        run(self.source, self.output)
        self.assertEqual(before, snapshot(self.output))
        migrated["schema_version"] = 3
        path.write_text(json.dumps(migrated), encoding="utf-8", newline="\n")
        with self.assertRaisesRegex(ValueError, "não é suportado"):
            run(self.source, self.output)

    def test_text_priority_and_tool_versions_are_recorded(self):
        self.pdf_with_images(self.source / "report.pdf")
        run(self.source, self.output)
        metadata = json.loads((self.output / "metadados/report.json").read_text(encoding="utf-8"))
        self.assertEqual((metadata["tools"]["pypdf"], metadata["tools"]["Pillow"]),
                         (pypdf.__version__, Image.__version__))
        self.assertTrue(metadata["tools"]["pdftotext"].startswith("pdftotext version"))
        self.assertTrue(metadata["tools"]["pdftoppm"].startswith("pdftoppm version"))
        result = validate(self.output, self.source)
        self.assertEqual(result["status"], "passed", result["failures"])
        self.assertEqual(result["tools"]["pdftotext"], metadata["tools"]["pdftotext"])
        pages = {p["page"]: p for p in result["review_priority"]}
        self.assertEqual(pages[3]["priority"], "alta")
        self.assertNotIn(1, pages)

    def test_large_file_hash_is_chunked_and_exact(self):
        import pdf_adapter
        path = self.base / "grande.bin"
        data = bytes(range(256)) * (pdf_adapter.HASH_CHUNK_BYTES // 256 * 2 + 7)
        path.write_bytes(data)
        self.assertGreater(len(data), 2 * pdf_adapter.HASH_CHUNK_BYTES)
        self.assertEqual(sha256(path), hashlib.sha256(data).hexdigest())


if __name__ == "__main__":
    unittest.main(verbosity=2)
