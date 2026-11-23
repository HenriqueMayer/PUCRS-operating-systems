# T2 — SimES: simulador de E/S e de arquivos

Segundo trabalho de Sistemas Operacionais (98700-04, turma 330, 2026/II, Prof. Filipo Novo Mór). Este arquivo resume os requisitos do enunciado. A implementação do grupo está em [`T2/`](../README.md), neste repositório. [Voltar ao índice do repositório](../../README.md).

O enunciado é a referência. Este resumo não o substitui.

| Item | Local |
| --- | --- |
| Enunciado original (PDF, 6 páginas) | [Enunciado/SisOp_2026_II_Trabalho_SimES.pdf](SisOp_2026_II_Trabalho_SimES.pdf) |
| Extração completa (texto por página, imagens das páginas, revisão) | [Extracted/index.md](../Extracted/index.md) → [documento](../Extracted/documentos/sisop-2026-ii-trabalho-simes.md) |
| Código base (repositório público do professor) | `https://github.com/ProfessorFilipo/Aulas_SisOp/tree/main/Trabalho_IO_2026II` — a implementação do grupo em `T2/` parte dele |

## Evidências das fontes (2026-11-12)

- Moodle, curso 95197, seção "Trabalho 02 - Entrega em 26/11/2026". O recurso `cmid` 3938718 forneceu o PDF: 715.874 bytes, SHA-256 `dd7e77a8ce53bfaad678860b6cd225e867054d24a921eea7cdf7b86b8cab7ebf`, modificado em 2026-11-10 19:21 (-03:00).
- Tarefa do Moodle "Trabalho 02: entrega" (`cmid` 3938684, `assignid` 227039): envios abertos em 2026-11-10 00:00, prazo em 2026-11-26 23:59 (-03:00), sem data-limite de corte. Envio individual, uma tentativa, somente arquivos `.pdf`, até 20 arquivos de 250 MiB. Texto do Moodle: "Faça aqui a entrega do relatório final do Trabalho 2."
- Mapa do código base lido pela API do GitHub no commit `648e5cc3e3` (2026-11-10 22:08 UTC). A pasta pode mudar depois; confira de novo antes de copiá-la.

## Entrega

- Somente o relatório final vai para o Moodle, em PDF. **Cada integrante** o envia até 26/11/2026, 23h59.
- Código, `resultados/` e `graficos/` vão para um **repositório público novo do grupo**. Copie para ele a pasta `Trabalho_IO_2026II` do professor. O professor avalia o repositório no estado em que estava no prazo.
- O grupo usa este repositório, pasta `T2/`, em vez de um repositório novo só para o T2. O `grupo.json` e o `RELATORIO.md` apontam para ele desde 2026-11-23.
- Preencha `grupo.json` (nomes, link do repositório, módulos, integração, bônus) e `RELATORIO.md`. O topo do relatório deve mostrar o nome completo de todos os integrantes e o link do repositório.
- Execute `python3 ferramentas/validar_entrega.py` até não haver erros. Depois faça o push e abra o repositório numa janela anônima do navegador para confirmar o acesso.
- Não coloque matrícula, e-mail, telefone, CPF, senhas, tokens, chaves de API ou arquivos `.env` no repositório público. Os nomes aparecem somente no relatório e no `grupo.json`.
- Não altere `parametros.py`, as cargas (`cargas/`) nem `experimentos.py`. Não altere nomes de arquivos, colunas dos CSVs nem títulos e campos do relatório.
- O uso de IA é permitido se a seção 8 do relatório declarar a ferramenta, a finalidade e os arquivos ou seções afetados.

## Escopo para um grupo de 2 integrantes

Dois integrantes devem entregar o **núcleo + 1 módulo** à escolha (enunciado, seção 3). Módulos extras só contam com implementação, experimento e análise completos. A integração ponta a ponta é obrigatória somente para grupos de 4. O bônus de armazenamento flash é opcional para qualquer grupo (até +0,5; nota final limitada a 10).

### Núcleo (todos os grupos)

| Parte | Trabalho | Arquivo base | Experimentos |
| --- | --- | --- | --- |
| N1 Dispositivo | Fornecido. Leia o modelo de custo (busca + rotação + transferência, 5.000 cilindros). | `simes/parametros.py`, `simes/disco.py` | — |
| N2 Subsistema de E/S | SSTF e SCAN (FCFS fornecido; os testes usam a fila do livro 98, 183, 37, 122, 14, 124, 65, 67 com a cabeça em 53). Custo de CPU do polling e da interrupção. | `simes/es/escalonadores.py`, `simes/es/cpu.py` | X1, X2 |
| N3 Sistema de arquivos | Resolução de caminhos; `mkdir`, `create`, `open`, `read`, `write`, `seek`, `close`, `unlink`; tabelas de arquivos abertos por processo e global; o `unlink` de um arquivo aberto libera os blocos só no último `close`. Siga exatamente as regras de custo do início do arquivo; os testes as conferem. | `simes/arquivos/sistema.py` | X3, X4, X5 |
| N4 Experimentos e relatório | Executar e analisar X1–X5 no `RELATORIO.md`. | `RELATORIO.md` | X1–X5 |

### Opções de módulo (escolher um)

| Módulo | Implementar | Arquivo base (quantidade de TODOs) | Exp. | Silberschatz |
| --- | --- | --- | --- | --- |
| M1 Cache de blocos | LRU e FIFO; write-through × write-back; perda de dados numa queda de energia | `simes/es/cache.py` (2) | X6 | 13.4.3, 12.6 |
| M2 Escalonamento avançado | C-SCAN, LOOK, C-LOOK, DEADLINE (contra inanição, inspirado no mq-deadline do Linux) | `simes/es/escalonadores.py` (4 de 6) | X7 | 10.4 |
| M3 DMA e buffering | Custo de CPU com DMA; buffers simples, duplo e circular | `simes/es/cpu.py`, `simes/es/buffering.py` | X8 | 13.2.3, 13.4.2 |
| M4 Links | Hard links, links simbólicos, ponteiros pendentes, laços de links, detecção de ciclos | `simes/arquivos/sistema.py` (`link`, `symlink`, `percorrer`) | X9 | cap. 11 |
| M5 Proteção e travas | Usuários, bits rwx, ACL; travas consultivas × mandatórias | `simes/arquivos/sistema.py` (`usuario`, `chmod`, `setacl`, `lock`, `unlock`) | X10 | 11.6, 11.1 |
| M6 Alocação em disco | Alocação encadeada, FAT e indexada (índice de 2 níveis), comparadas à contígua | `simes/arquivos/alocacao.py` (10) | X11 | 12.4, 12.5 |

As regras exatas de cada módulo estão nos comentários do seu arquivo. Os testes de módulo em `testes/test_modulos.py` são pulados até o módulo ser implementado.

## Método obrigatório em cada experimento

1. Escreva a hipótese e o motivo, com base no livro, **antes** de executar o experimento. A nota depende da explicação, não de acertar a hipótese.
2. Explique os números com os conceitos do Silberschatz e com o modelo do simulador (parâmetros e regras de custo).
3. Relacione os resultados com Windows, Linux e macOS (exemplos do enunciado: mq-deadline, BFQ, none; cache de páginas e gravação periódica; FAT em pendrives; estruturas do ext4, NTFS e APFS; travas mandatórias do Windows).
4. Declare as limitações do modelo.

Cada experimento do relatório tem os campos Hipótese, Fundamentação, Configuração, Resultados, Evidências, Análise e Veredito (CONFIRMADA, PARCIALMENTE CONFIRMADA ou REFUTADA). Em Evidências, cite arquivos de `resultados/` e `graficos/`. Os resultados oficiais são os que o `experimentos.py` produz; configurações extras devem ficar separadas e ser declaradas.

## Cronograma sugerido (enunciado, seção 7)

| Período | Atividade |
| --- | --- |
| 10–13/11 | Ler o código e as regras; executar os testes; implementar o N2; hipóteses e execução de X1 e X2 |
| 14–17/11 | Implementar o N3 até os testes do núcleo passarem; hipóteses e execução de X3–X5 |
| 18–21/11 | Módulo escolhido; hipótese e experimento correspondentes |
| 22–26/11 | Análise, relatório, validação e envio por todos os integrantes |

## Avaliação

A entrega básica completa (escopo mínimo, testes do núcleo e do módulo passando, experimentos exigidos, hipóteses registradas, análises corretas) recebe 7. Notas maiores premiam a qualidade da análise.

| Critério | Peso |
| --- | --- |
| Implementação | 30% |
| Experimentos e indicadores | 25% |
| Análise e fundamentação | 30% |
| Relatório | 15% |

O professor pode pedir a qualquer integrante que explique ou modifique o código ou a análise; a nota pode ser individualizada.

## Mapa do repositório base

Arquivos em `Trabalho_IO_2026II/` no commit `648e5cc3e3` (44 arquivos). Python 3.8+, somente a biblioteca padrão; `matplotlib` é opcional para os gráficos.

| Caminho | Conteúdo |
| --- | --- |
| `README.md`, `RELATORIO.md`, `grupo.json` | Instruções, modelo do relatório (seções 0–8, experimentos X1–X13), dados do grupo |
| `executar.py` | Linha de comando: `testes`, `es`, `arquivos`, `buffering`, `experimentos` |
| `experimentos.py`, `graficos.py`, `gerar_cargas.py` | Experimentos oficiais, gráficos padrão, gerador de cargas — não altere o primeiro |
| `cargas/` | 12 cargas padronizadas (`es_*` para E/S, `fs_*` para sistema de arquivos) — não altere |
| `ferramentas/validar_entrega.py` | Validador da entrega |
| `testes/` | `test_fornecido.py`, `test_nucleo.py`, `test_modulos.py` |
| `simes/parametros.py`, `simes/disco.py` | Parâmetros fixos; modelo do disco; `DiscoFlash` (bônus) |
| `simes/es/` | `escalonadores.py`, `cpu.py`, `cache.py`, `buffering.py`, `requisicao.py`, `simulador.py` |
| `simes/arquivos/` | `sistema.py`, `alocacao.py`, `estruturas.py`, `camada_bloco.py`, `simulador.py` |
| `simes/integracao.py` | Integração ponta a ponta (grupos de 4) |

Marcadores `NotImplementedError("TODO …")` por arquivo: `arquivos/sistema.py` 21 (N3: `resolver` e 8 operações; M4: 3; M5: 5), `arquivos/alocacao.py` 10 (M6), `es/escalonadores.py` 6 (N2: SSTF, SCAN; M2: 4), `es/cpu.py` 4 (N2: polling, interrupção; M3: DMA), `es/cache.py` 2 (M1), `es/buffering.py` 1 (M3), `integracao.py` 1. As contagens vêm de uma busca textual em 2026-11-12, sem execução do código.

## Por onde começar a pesquisa (enunciado, seção 10)

- Silberschatz, Galvin & Gagne, *Operating System Concepts*, 9ª ed.: 10.4; cap. 11; 12.4–12.6; 13.2–13.4.
- Documentação do kernel Linux sobre os escalonadores de E/S mq-deadline e BFQ.
- Documentação do Python: `collections.OrderedDict` (cache LRU).
- Material de aula: atividade prática `Pratica_Arquivos_ES` e scripts da aula de E/S `Gestao_IO`.

## Registro

| Data | Registro |
| --- | --- |
| 2026-11-12 | Enunciado baixado do Moodle e extraído com `content-extract` (6/6 páginas revisadas, validação aprovada). Incluídos o resumo dos requisitos e o mapa do código base. `/T2/` incluído no `.gitignore`. |
| 2026-11-12 | `/T2/` retirado do `.gitignore` por decisão do usuário: a pasta, incluindo o PDF do professor, passou a fazer parte da árvore de trabalho a versionar. Sem commit. |
| 2026-11-12 | README traduzido para pt-BR. |
| 2026-11-23 | Implementação do grupo (Eduardo Santos, commits `58f1199`, `4f0712b` e `3fbd1e8`) integrada em `T2/`. Este resumo foi movido de `T2/README.md` para `T2/Enunciado/README.md`, porque `T2/README.md` passou a ser o README do código. Links ajustados ao novo local. Corrigida a afirmação de que a implementação ficava em outro repositório. |
