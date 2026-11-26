# Sistemas Operacionais — PUCRS 2026/II

Material e trabalhos da disciplina de Sistemas Operacionais (98700-04, turma 330, Prof. Filipo Novo Mór, curso Moodle `95197`).

## Estrutura

| Pasta | Conteúdo |
| --- | --- |
| [Material/](Material/README.md) | Material do Moodle: originais em `Material/Fontes/Moodle/`, extração em `Material/Extracted/`. |
| `Trabalho/` | Um trabalho por pasta (tabela abaixo). |

| Pasta | Trabalho | Conteúdo |
| --- | --- | --- |
| [Trabalho/T1/](Trabalho/T1/README.md) | Contagem de objetos em matrizes binárias | Implementações sequencial e paralela em C89/C90 (`fork`, pipes, Union-Find), testes e resultados de desempenho e validação. |
| [Trabalho/T2/](Trabalho/T2/README.md) | SimES: simulador de E/S e de arquivos | Implementação do grupo em Python (módulo M3, conforme `grupo.json`), cargas, testes, experimentos, `resultados/`, `graficos/` e `RELATORIO.md`. O enunciado e o [resumo dos requisitos](Trabalho/T2/Enunciado/README.md) estão em `Trabalho/T2/Enunciado/`; a extração do enunciado está em `Trabalho/T2/Extracted/`. |

## Git e Google Drive

O Git guarda os PDFs originais em `Material/Fontes/` e os trabalhos. A extração, os originais em outros formatos e os registros de download ficam só nesta máquina; copie-os para o Google Drive. Ver [.gitignore](.gitignore).

## Início rápido

```sh
make -C Trabalho/T1
make -C Trabalho/T1 test
```

Os executáveis do T1 usam caminhos relativos a `Trabalho/T1/`; consulte o [README do T1](Trabalho/T1/README.md).

```sh
cd Trabalho/T2
python3 executar.py testes
```

Os comandos do T2 usam caminhos relativos a `Trabalho/T2/`; consulte o [README do T2](Trabalho/T2/README.md).

## Registro

Os registros anteriores a 2026-11-24 citam o layout antigo, com `T1/` e `T2/` na raiz.

| Data | Registro |
| --- | --- |
| 2026-11-12 | T1 (`Makefile`, `README.md`, `src/`, `tests/`, `results/`) movido da raiz para `T1/`. Incluída a pasta `T2/` com o enunciado, sua extração e o resumo dos requisitos. A raiz passou a ser este índice. |
| 2026-11-23 | Implementação do T2 enviada por Eduardo Santos integrada em `T2/`. O resumo dos requisitos foi movido para `T2/Enunciado/README.md`. A implementação fica neste repositório, não em um repositório separado. |
| 2026-11-24 | Reorganização em `Material/` e `Trabalho/`: `T1/` e `T2/` movidos para `Trabalho/`; regras do `.gitignore` atualizadas para os novos caminhos. Baixados os 47 arquivos do Moodle para `Material/Fontes/Moodle/` e extraídos. Nada foi commitado. |
| 2026-11-25 | T2: experimentos X1–X5 e X8 executados localmente (`Trabalho/T2/resultados/` e `Trabalho/T2/graficos/`) e `RELATORIO.md` preenchido. O link do repositório em `grupo.json` e no relatório passou a apontar para `Trabalho/T2`. Validador da entrega: 0 erros e 0 avisos. Nada foi commitado. |
