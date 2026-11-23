# Conferência das extrações

A cobertura estrutural e a revisão do conteúdo são verificações distintas. Este relatório registra extração e conferência das fontes; análise, organização editorial e criação de novos materiais dependem de pedido específico.

## Evidências e notas por documento

### DOC-001 — Trabalho Prático — SimES: Simulador de E/S e de Arquivos (SISOP 2026/II)

Fonte: `SisOp_2026_II_Trabalho_SimES.pdf`.

Estado: **Conferido visualmente**. SHA-256: `dd7e77a8ce53bfaad678860b6cd225e867054d24a921eea7cdf7b86b8cab7ebf`.

Páginas físicas: 6; conferidas visualmente: 6.

- pypdf emitiu avisos 'Ignoring wrong pointing object' (tabela xref do PDF); a extração de texto e imagens foi concluída e as páginas renderizadas conferem com o texto.
- [Página 5](documentos/sisop-2026-ii-trabalho-simes.md#pagina-005): 'mq-deadline' e 'BFQ' aparecem como hiperligações; os endereços de destino não estão na camada textual e não foram consultados nesta extração.
- [Página 6](documentos/sisop-2026-ii-trabalho-simes.md#pagina-006): 'collections.OrderedDict' aparece como hiperligação; o endereço de destino não está na camada textual e não foi consultado.
