# Sistemas Operacionais — PUCRS 2026/II

Trabalhos da disciplina de Sistemas Operacionais (98700-04, turma 330, Prof. Filipo Novo Mór). Cada trabalho tem sua própria pasta.

| Pasta | Trabalho | Conteúdo |
| --- | --- | --- |
| [T1/](T1/README.md) | Contagem de objetos em matrizes binárias | Implementações sequencial e paralela em C89/C90 (`fork`, pipes, Union-Find), testes e resultados de desempenho e validação. |
| [T2/](T2/README.md) | SimES: simulador de E/S e de arquivos | Implementação do grupo em Python (módulo M3, conforme `grupo.json`), cargas, testes, experimentos e `RELATORIO.md`. O enunciado e o [resumo dos requisitos](T2/Enunciado/README.md) estão em `T2/Enunciado/`; a extração do enunciado está em `T2/Extracted/`. |

## Início rápido

```sh
make -C T1
make -C T1 test
```

Os executáveis do T1 usam caminhos relativos a `T1/`; consulte o [README do T1](T1/README.md).

```sh
cd T2
python3 executar.py testes
```

Os comandos do T2 usam caminhos relativos a `T2/`; consulte o [README do T2](T2/README.md).

## Registro

| Data | Registro |
| --- | --- |
| 2026-11-12 | T1 (`Makefile`, `README.md`, `src/`, `tests/`, `results/`) movido da raiz para `T1/`. Incluída a pasta `T2/` com o enunciado, sua extração e o resumo dos requisitos. A raiz passou a ser este índice. |
| 2026-11-23 | Implementação do T2 enviada por Eduardo Santos integrada em `T2/`. O resumo dos requisitos foi movido para `T2/Enunciado/README.md`. A implementação fica neste repositório, não em um repositório separado. |
