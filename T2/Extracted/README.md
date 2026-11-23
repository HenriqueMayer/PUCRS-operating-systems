# Trabalho 2 — SimES: enunciado (SISOP 2026/II) — conteúdo extraído

[Índice do acervo](index.md) · [Manifesto](manifesto.json) · [Conferência](conferencia.md) · [Validação](validacao.json)

## Estrutura

- `documentos/`: uma extração integral por fonte, com âncoras físicas e notas de fidelidade.
- `assets/<slug>/`: páginas PNG, imagens incorporadas de PDFs em `imagens/` e todas as representações MIME salvas nos notebooks.
- `metadados/`: texto, cobertura e dependências recuperados por documento.
- `revisoes/<slug>.json`: revisão humana vinculada ao SHA-256 da fonte; não preenchida automaticamente.
- `scripts/` e `requirements.txt`: pipeline local reproduzível.

## Atualização e conferência

Execute a partir desta pasta com Python 3.11+ e as dependências de `requirements.txt`. PDFs exigem `pdftotext` e `pdftoppm`; use o PATH do processo ou configure CONTENT_EXTRACT_PDFTOTEXT e CONTENT_EXTRACT_PDFTOPPM.

```sh
python3 -B scripts/extrair.py --source ../Enunciado --output .
python3 -B scripts/validar.py --source ../Enunciado --output .
python3 -B scripts/preparar_revisao.py --output .
python3 -B scripts/validar.py --source ../Enunciado --output . --require-reviewed
```

SHA-256 detecta documentos novos e alterados; hashes dos artefatos permitem reparar corrupção. IDs são permanentes. Execuções sem alteração preservam bytes e datas dos arquivos. Fontes ausentes continuam registradas, com a extração preservada.

Fontes sem adaptador, ilegíveis, não UTF-8, malformadas, acima de um limite de recurso ou links não seguidos ficam no manifesto com status e motivo; a cobertura permanece incompleta. `--exclude` registra exclusões explícitas no manifesto. Saídas que deixam de corresponder à fonte ficam em `stale_outputs`; nada é apagado automaticamente. CONTENT_EXTRACT_TIMEOUT e CONTENT_EXTRACT_MAX_IMAGE_PIXELS ajustam os limites.

A validação estrutural não certifica leitura visual. Confira cada página/célula, todas as imagens salvas e as discrepâncias antes de registrar a revisão. Folhas de contato ajudam a revisar; amplie fórmulas, gráficos e tabelas quando necessário. Nenhum notebook, HTML ou JavaScript é executado; URLs e dados ausentes não são baixados.

## Registro de entrega

| Data | Registro |
| --- | --- |
| 2026-11-12 | Extração inicial de `../Enunciado/SisOp_2026_II_Trabalho_SimES.pdf` (DOC-001, 6 páginas, 4 imagens incorporadas). Ferramentas: Python 3.12.13 em ambiente virtual temporário, pypdf 6.21.4, Pillow 13.0.0, pdftotext 25.03.0 e pdftoppm do Poppler no PATH do sistema. O pypdf emitiu avisos "Ignoring wrong pointing object" sobre a tabela de referências cruzadas do PDF; o texto e as imagens das páginas conferem. As 6 páginas foram revisadas visualmente. `validar.py --require-reviewed` foi aprovado com cobertura completa. Os destinos das hiperligações das páginas 5 e 6 não estão na camada textual e não foram visitados. |
