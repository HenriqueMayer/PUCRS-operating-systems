# DOC-001 — Trabalho Prático — SimES: Simulador de E/S e de Arquivos (SISOP 2026/II)

[Voltar ao índice](../index.md)

Fonte: [SisOp_2026_II_Trabalho_SimES.pdf](<../../Enunciado/SisOp_2026_II_Trabalho_SimES.pdf>).

SHA-256 da fonte: `dd7e77a8ce53bfaad678860b6cd225e867054d24a921eea7cdf7b86b8cab7ebf`.

Enunciado do Trabalho 2 de Sistemas Operacionais (Prof. Filipo Novo Mór, PUCRS 2026/II), com 6 páginas. Define o simulador SimES em Python (dispositivo, subsistema de E/S e sistema de arquivos), o escopo mínimo por tamanho de grupo, o núcleo N1–N4, os módulos M1–M6, a integração ponta a ponta, o bônus de armazenamento flash, os experimentos X1–X13 e o método obrigatório, o cronograma sugerido, as regras de entrega (repositório público do grupo e relatório em PDF no Moodle até 26/11/2026, 23h59), os critérios de avaliação e as referências de pesquisa.

Cobertura: 6 páginas físicas; 6 conferidas visualmente.

O bloco de texto preserva a camada textual e sua disposição. Complementos identificados abaixo recuperam conteúdo visual. A imagem de cada página preserva gráficos, fórmulas, cores, ordem de leitura e símbolos da fonte; prevalece sobre caracteres distorcidos no bloco.

## Sumário por página

- [Página 1 — Capa, 1. Objetivo e 2. O simulador](#pagina-001)
- [Página 2 — 3. Escopo mínimo e 4. Núcleo](#pagina-002)
- [Página 3 — 5. Módulos e 6. Experimentos e método](#pagina-003)
- [Página 4 — Método obrigatório, 7. Cronograma sugerido e 8. Entrega](#pagina-004)
- [Página 5 — Avisos de dados sensíveis e formato, 9. Avaliação e 10. Pesquisa](#pagina-005)
- [Página 6 — 10. Pesquisa (continuação)](#pagina-006)

<a id="pagina-001"></a>

## Página física 1

**Capa, 1. Objetivo e 2. O simulador**

### Texto da camada textual

```text
PUCRS · ESCOLA POLITÉCNICA
SISTEMAS OPERACIONAIS · 2026/II
PROF. FILIPO NOVO MÓR · FILIPOMOR.COM




TRABALHO PRÁTICO


SIMES: SIMULADOR DE E/S E DE ARQUIVOS
Implementar, medir e analisar a gestão de entrada e saída e a gestão de arquivos

  GRUPOS                                ENTREGA                    ENVIO                      REFERÊNCIA
  1 a 4 integrantes                     26/11/2026, 23h59          Relatório no Moodle        Silberschatz, caps. 10 a
                                                                   (todos)                    13



1. Objetivo
Neste trabalho, o grupo completa um simulador do caminho de uma requisição de E/S: do sistema de
arquivos, passando pelo subsistema de E/S do kernel, até o disco. Com ele, o grupo roda experimentos
padronizados, mede indicadores de desempenho e escreve um relatório que explica os resultados com base
no livro e os relaciona com o que Windows, Linux e macOS fazem de fato.
Parte do conteúdo vai além do que vimos em aula e exige pesquisa: os algoritmos de escalonamento de
disco (Silberschatz, seção 10.4) e os métodos de alocação de arquivos (seções 12.4 e 12.5).
O código, os resultados e os gráficos ficam num repositório público do grupo. A entrega no Moodle é
apenas o relatório final, que cita esse repositório (seção 8).


2. O simulador
O código está no repositório da disciplina, na pasta Trabalho_IO_2026II. Ele usa só a biblioteca padrão do
Python 3.8+ e roda em Windows, Linux e macOS sem precisar de administrador. A infraestrutura já vem
pronta; o grupo implementa as partes que são conteúdo da disciplina, marcadas com TODO no código.

 Camada                   O que simula                        Já vem pronto              O grupo implementa
 1 · Dispositivo          Disco rígido com 5.000              Tudo (parâmetros fixos)    Bônus: armazenamento flash
                          cilindros; custo de cada acesso =
                          busca + rotação + transferência
 2 · Subsistema de        Fila de requisições,                Simulador por eventos,     Escalonadores, polling,
 E/S                      escalonamento, custo de CPU,        FCFS, medição              interrupção, DMA, cache,
                          cache, buffering                                               buffering

 3 · Sistema de           Diretórios, operações, FCB,         Estruturas, alocação       Operações, resolução de
 arquivos                 tabelas de arquivos abertos,        contígua, acesso aos       caminhos, links, proteção,
                          alocação                            blocos, simulador          travas, outros alocadores

Também vêm prontos: as cargas de trabalho padronizadas, os experimentos X1 a X13, os gráficos, os testes
automáticos e o validador da entrega. Todos os grupos usam os mesmos parâmetros e cargas, o que torna os
resultados comparáveis. Não alterem parametros.py, as cargas nem experimentos.py.




PROF. FILIPO NOVO MÓR · FILIPOMOR.COM                                                                           PÁGINA 1 DE 6
```

**Conteúdo visual:** Cabeçalho institucional com fotografia circular do professor (imagem incorporada de 600 × 600 px), quatro caixas de identificação (grupos, entrega, envio, referência) e tabela de três camadas do simulador. O texto da camada textual representa todas as caixas e a tabela; negritos não aparecem no texto bruto.

![Página física 1 da fonte SisOp_2026_II_Trabalho_SimES.pdf](<../assets/sisop-2026-ii-trabalho-simes/pagina-001.png>)

### Imagens incorporadas

Recursos raster extraídos do PDF, sem redimensionamento. Elementos vetoriais e a composição visual continuam disponíveis na página completa.

- [Imagem incorporada — Im1.png](<../assets/sisop-2026-ii-trabalho-simes/imagens/pagina-001-imagem-001.png>) · 600 × 600 px · página 1.


<a id="pagina-002"></a>

## Página física 2

**3. Escopo mínimo e 4. Núcleo**

### Texto da camada textual

```text
SISTEMAS OPERACIONAIS · 2026/II                                                                          TRABALHO PRÁTICO · SIMES




3. Escopo mínimo
Todo trabalho tem o núcleo (seção 4). Conforme o tamanho do grupo, somam-se módulos à escolha (seção
5):

 Integrantes              Exigência mínima
 1                        Núcleo

 2                        Núcleo + 1 módulo
 3                        Núcleo + 2 módulos: pelo menos um de E/S (M1 a M3) e um de arquivos (M4 a M6)
 4                        Núcleo + 3 módulos, com os dois tópicos cobertos, + integração ponta a ponta

Módulos além do mínimo não são obrigatórios. Para contar como diferencial, precisam ter implementação,
experimento e análise completos.


4. Núcleo (todos)
N1 · DISPOSITIVO
Fornecido. Leiam simes/parametros.py e simes/disco.py para entender o modelo de custo: ele é a base de
todas as análises.

N2 · SUBSISTEMA DE E/S
 ▪ Escalonadores SSTF e SCAN (simes/es/escalonadores.py). O FCFS já vem pronto como exemplo, e os
   testes conferem os resultados com o exemplo do livro (fila 98, 183, 37, 122, 14, 124, 65, 67, cabeça no
   cilindro 53).
 ▪ Custo de CPU por polling e por interrupção (simes/es/cpu.py), conforme as fórmulas do arquivo.
N3 · SISTEMA DE ARQUIVOS
 ▪ Em simes/arquivos/sistema.py: resolução de caminhos e as operações mkdir, create, open, read, write,
   seek, close e unlink.
 ▪ Tabela de arquivos abertos por processo (posição e modo) e global (com contador de aberturas),
   acesso sequencial e direto, e o unlink de um arquivo aberto, cujos blocos só são liberados no último
   close.
 ▪ Sigam à risca as regras de custo do início do arquivo (quantas leituras e escritas cada operação faz). Os
   testes as conferem.
N4 · EXPERIMENTOS E RELATÓRIO
Rodar os experimentos X1 a X5, analisá-los e escrever o relatório no modelo RELATORIO.md (seções 6 e 8).




PROF. FILIPO NOVO MÓR · FILIPOMOR.COM                                                                               PÁGINA 2 DE 6
```

**Conteúdo visual:** Tabela de exigência mínima por integrantes e subtítulos N1–N4 em versalete. Os marcadores de lista são a imagem incorporada de 160 × 160 px (quadrado preto), extraída em imagens/; ela não tem conteúdo informativo.

![Página física 2 da fonte SisOp_2026_II_Trabalho_SimES.pdf](<../assets/sisop-2026-ii-trabalho-simes/pagina-002.png>)

### Imagens incorporadas

Recursos raster extraídos do PDF, sem redimensionamento. Elementos vetoriais e a composição visual continuam disponíveis na página completa.

- [Imagem incorporada — Im2.png](<../assets/sisop-2026-ii-trabalho-simes/imagens/pagina-002-imagem-001.png>) · 160 × 160 px · página 2.


<a id="pagina-003"></a>

## Página física 3

**5. Módulos e 6. Experimentos e método**

### Texto da camada textual

```text
SISTEMAS OPERACIONAIS · 2026/II                                                                                TRABALHO PRÁTICO · SIMES




5. Módulos
 Módulo                                 O que implementar                                           Exp.       Pesquisa
 M1 · Cache de blocos                   Cache LRU e FIFO; write-through × write-back; perda de      X6         13.4.3, 12.6
                                        dados numa queda de energia

 M2 · Escalonamento                     C-SCAN, LOOK, C-LOOK e DEADLINE (prazos contra              X7         10.4
 avançado                               inanição, inspirado no mq-deadline do Linux)

 M3 · DMA e buffering                   Custo de CPU com DMA; buffer simples, duplo e circular      X8         13.2.3, 13.4.2
                                        entre produtor e dispositivo
 M4 · Links e                           Hard links, links simbólicos, ponteiros pendentes, laços    X9         cap. 11 (diretórios
 compartilhamento                       de links e detecção de ciclos na travessia                             em grafo)
 M5 · Proteção e travas                 Usuários, bits rwx, ACL; travas consultivas ×               X10        11.6, 11.1
                                        mandatórias

 M6 · Alocação em disco                 Alocação encadeada, FAT e indexada (com índice de 2         X11        12.4, 12.5
                                        níveis), comparadas à contígua

As regras exatas de cada módulo estão nos comentários do arquivo correspondente. Os testes automáticos
de cada módulo ficam desativados até ele ser implementado.

INTEGRAÇÃO PONTA A PONTA (OBRIGATÓRIA PARA GRUPOS DE 4)
Converter o histórico de acessos ao disco de uma carga do sistema de arquivos em requisições de E/S
(simes/integracao.py), que então passam pela cache e pelo escalonador (experimento X12). Assim, o grupo
mede como a organização dos arquivos no disco afeta o desempenho das camadas de baixo.

BÔNUS: ARMAZENAMENTO FLASH (ATÉ +0,5 NA NOTA)
Implementar o DiscoFlash (SSD ou celular): gravação por página, apagamento por bloco, camada de
tradução e coleta de lixo, medindo a amplificação de escrita (experimento X13). A nota final é limitada a 10.


6. Experimentos e método
python3 executar.py experimentos roda todos os experimentos implementados e grava os indicadores em
resultados/*.csv; python3 graficos.py gera os gráficos padrão.

 Exp.           Compara                                                      Indicadores principais
 X1             FCFS, SSTF e SCAN nas cargas sequencial, aleatória,          deslocamento do braço, resposta média e no
                concentrada e em rajadas                                     percentil 95, maior espera, vazão
 X2             Polling × interrupção, num disco rígido e num                % de CPU gasta com E/S
                dispositivo rápido

 X3             Acesso sequencial (compilador) × direto (banco de            acessos e tempo por operação
                dados)
 X4             Abrir um arquivo a 1, 2, …, 10 diretórios de                 acessos e tempo por open
                profundidade

 X5             Vários processos abrindo os mesmos arquivos                  tamanho das tabelas global e por processo,
                                                                             contador de aberturas

 X6–X11         Um experimento por módulo (seção 5)                          acertos da cache, inanição, CPU, ciclos, negações,
                                                                             fragmentação…
 X12            Integração: cargas de arquivos → cache →                     resposta, deslocamento, acertos
                escalonador
 X13            Bônus: flash × disco rígido                                  tempo, amplificação de escrita, apagamentos



PROF. FILIPO NOVO MÓR · FILIPOMOR.COM                                                                                       PÁGINA 3 DE 6
```

**Conteúdo visual:** Tabela de módulos M1–M6 com experimento e seções de pesquisa; blocos de integração e bônus; tabela de experimentos X1–X13. O texto da camada textual representa as tabelas completas.

![Página física 3 da fonte SisOp_2026_II_Trabalho_SimES.pdf](<../assets/sisop-2026-ii-trabalho-simes/pagina-003.png>)


<a id="pagina-004"></a>

## Página física 4

**Método obrigatório, 7. Cronograma sugerido e 8. Entrega**

### Texto da camada textual

```text
SISTEMAS OPERACIONAIS · 2026/II                                                                           TRABALHO PRÁTICO · SIMES




Método obrigatório em cada experimento do escopo:
 1. Hipótese antes de rodar. Escrevam o resultado esperado e o porquê, com base no livro. A nota não
    depende de acertar a hipótese, e sim de explicar bem o resultado.
 2. Análise com fundamento. Expliquem os números com os conceitos do Silberschatz e com o modelo do
    simulador (parâmetros e regras de custo).
 3. Relação com sistemas reais. Relacionem os resultados com Windows, Linux e macOS. Exemplos: os
    escalonadores de E/S do Linux (mq-deadline, BFQ, none), o cache de páginas e a gravação periódica, a
    FAT dos pendrives, as estruturas do ext4, do NTFS e do APFS, as travas mandatórias do Windows.
 4. Limitações. Digam o que o modelo simplifica e como isso pode ter afetado as conclusões.
Experimentos extras (outros parâmetros ou cargas) são bem-vindos, mas em configuração separada e
declarados no relatório. Os resultados oficiais são os gerados por experimentos.py.


7. Cronograma sugerido
 Período                    Atividade
 10 a 13/11                 Ler o código e as regras; rodar os testes; implementar o N2 (SSTF, SCAN, polling, interrupção);
                            hipóteses e execução de X1 e X2
 14 a 17/11                 Implementar o N3 (sistema de arquivos) até os testes do núcleo passarem; hipóteses e execução
                            de X3 a X5

 18 a 21/11                 Módulos escolhidos (e integração, nos grupos de 4); hipóteses e experimentos dos módulos
 22 a 26/11                 Análise, relatório, validação e envio do relatório por todos os integrantes

Registrem a hipótese de cada experimento antes de rodá-lo, mesmo que o relatório seja escrito no fim.


8. Entrega
A entrega é somente o relatório final, enviado no Moodle por todos os integrantes até 26/11/2026,
23h59. O código, os resultados e os gráficos ficam no repositório público do grupo, citado no relatório.
 1. Criem um repositório público novo, só para este trabalho (por exemplo, no GitHub), e copiem para ele o
    conteúdo da pasta Trabalho_IO_2026II. O README da pasta mostra os comandos.
 2. Rodem python3 executar.py experimentos e python3 graficos.py, e façam commit também de
    resultados/ e graficos/, que o relatório cita como evidência. Sem o matplotlib, façam os mesmos
    gráficos numa planilha, a partir dos CSVs, e salvem-nos em graficos/.
 3. Preencham grupo.json (nomes, link do repositório, módulos escolhidos, integração, bônus) e
    RELATORIO.md. No topo do relatório, o nome completo de todos os integrantes e o link do
    repositório são obrigatórios.
 4. Rodem python3 ferramentas/validar_entrega.py até não haver erros, deem git push e confiram que o
    repositório abre numa janela anônima do navegador.
 5. Exportem o relatório para PDF (por exemplo, abrindo o RELATORIO.md no GitHub e usando Imprimir →
    Salvar como PDF). Cada integrante envia esse PDF no Moodle.
O professor considera o repositório no estado em que estava no prazo de entrega; commits posteriores
podem ser desconsiderados. Sem o repositório público acessível, a implementação e os experimentos não
podem ser avaliados.




PROF. FILIPO NOVO MÓR · FILIPOMOR.COM                                                                                PÁGINA 4 DE 6
```

**Conteúdo visual:** Lista numerada do método, tabela de cronograma, nota em itálico sobre registro de hipóteses e lista numerada de passos de entrega.

![Página física 4 da fonte SisOp_2026_II_Trabalho_SimES.pdf](<../assets/sisop-2026-ii-trabalho-simes/pagina-004.png>)


<a id="pagina-005"></a>

## Página física 5

**Avisos de dados sensíveis e formato, 9. Avaliação e 10. Pesquisa**

### Texto da camada textual

```text
SISTEMAS OPERACIONAIS · 2026/II                                                                        TRABALHO PRÁTICO · SIMES




   DADOS SENSÍVEIS: O REPOSITÓRIO É PÚBLICO
   Não incluam matrícula, e-mail, telefone, CPF ou outros dados pessoais, nem senhas, tokens, chaves de
   API ou arquivos .env. Os nomes dos integrantes aparecem no relatório e no grupo.json, e nada além
   disso.
   O validador procura alguns desses padrões, mas a responsabilidade é do grupo. Um dado sensível que
   entrou num commit continua no histórico do git mesmo depois de apagado: troquem a senha ou o token
   imediatamente e, se for o caso, recriem o repositório.


   REGRAS DO FORMATO
   Não alterem os nomes de arquivos, as colunas dos CSVs nem os títulos e campos do relatório.
   Em cada experimento do relatório, os campos são Hipótese, Fundamentação, Configuração,
   Resultados, Evidências, Análise e Veredito. O veredito é um destes três: CONFIRMADA,
   PARCIALMENTE CONFIRMADA ou REFUTADA.
   Em Evidências, citem os arquivos de resultados/ e graficos/ do repositório que sustentam a análise.
   Trabalho que não passa no validador pode ter partes desconsideradas.



9. Avaliação
Nota de 0 a 10. O trabalho que entrega o básico recebe 7: escopo mínimo completo, testes do núcleo e dos
módulos escolhidos passando, experimentos exigidos executados, hipóteses registradas e análises corretas,
com fundamento no livro. Notas acima de 7 premiam a qualidade da análise: explicações que vão além da
descrição dos números, uso das regras do modelo, relação consistente com sistemas reais, boa pesquisa e
discussão das limitações.

 Critério                               Peso   O que se espera para a nota máxima
 Implementação                          30%    testes passando; código correto, legível e coerente com as regras do
                                               modelo; decisões explicadas na seção 2 do relatório

 Experimentos e indicadores             25%    todos os experimentos exigidos executados; tabelas e gráficos legíveis,
                                               com unidades; evidências citadas

 Análise e fundamentação                30%    hipóteses prévias; resultados explicados com o Silberschatz e com o
                                               modelo; divergências explicadas; relação com Windows, Linux e macOS;
                                               pesquisa citada

 Relatório                              15%    modelo seguido; nomes de todos os integrantes e link do repositório; texto
                                               claro; limitações e conclusões; declaração de autoria e de uso de IA

Bônus: até +0,5 pelo armazenamento flash, com nota final limitada a 10.
Uso de IA: permitido, desde que declarado na seção 8 do relatório, com a ferramenta, a finalidade e os
arquivos ou seções em que foi usada.
Arguição: o professor pode pedir a qualquer integrante que explique ou modifique parte do código ou da
análise, e a nota pode ser individualizada a partir disso.


10. Por onde começar a pesquisa
 ▪ Silberschatz, Galvin & Gagne, Operating System Concepts, 9ª ed.: seção 10.4 (escalonamento de disco);
   cap. 11 (interface do sistema de arquivos); seções 12.4 a 12.6 (alocação, espaço livre, desempenho);
   seções 13.2 a 13.4 (hardware de E/S e subsistema de E/S do kernel).
 ▪ Documentação do kernel Linux sobre escalonadores de E/S: mq-deadline e BFQ.


PROF. FILIPO NOVO MÓR · FILIPOMOR.COM                                                                             PÁGINA 5 DE 6
```

**Conteúdo visual:** Caixa laranja de dados sensíveis e caixa verde de regras do formato; tabela de critérios com pesos 30/25/30/15 %. Os marcadores de lista são a imagem incorporada de 160 × 160 px (quadrado preto), extraída em imagens/; ela não tem conteúdo informativo.

> **Nota de fidelidade:** 'mq-deadline' e 'BFQ' aparecem como hiperligações; os endereços de destino não estão na camada textual e não foram consultados nesta extração.

![Página física 5 da fonte SisOp_2026_II_Trabalho_SimES.pdf](<../assets/sisop-2026-ii-trabalho-simes/pagina-005.png>)

### Imagens incorporadas

Recursos raster extraídos do PDF, sem redimensionamento. Elementos vetoriais e a composição visual continuam disponíveis na página completa.

- [Imagem incorporada — Im2.png](<../assets/sisop-2026-ii-trabalho-simes/imagens/pagina-005-imagem-001.png>) · 160 × 160 px · página 5.


<a id="pagina-006"></a>

## Página física 6

**10. Pesquisa (continuação)**

### Texto da camada textual

```text
SISTEMAS OPERACIONAIS · 2026/II                                                           TRABALHO PRÁTICO · SIMES




 ▪ Documentação do Python: collections.OrderedDict (útil na cache LRU).
 ▪ O roteiro e os scripts da atividade prática em aula (Pratica_Arquivos_ES) e da aula de E/S (Gestao_IO):
   várias medições reais ajudam a discutir as limitações do modelo.




PROF. FILIPO NOVO MÓR · FILIPOMOR.COM                                                                PÁGINA 6 DE 6
```

**Conteúdo visual:** Dois itens de lista; o restante da página está em branco. Os marcadores de lista são a imagem incorporada de 160 × 160 px (quadrado preto), extraída em imagens/; ela não tem conteúdo informativo.

> **Nota de fidelidade:** 'collections.OrderedDict' aparece como hiperligação; o endereço de destino não está na camada textual e não foi consultado.

![Página física 6 da fonte SisOp_2026_II_Trabalho_SimES.pdf](<../assets/sisop-2026-ii-trabalho-simes/pagina-006.png>)

### Imagens incorporadas

Recursos raster extraídos do PDF, sem redimensionamento. Elementos vetoriais e a composição visual continuam disponíveis na página completa.

- [Imagem incorporada — Im2.png](<../assets/sisop-2026-ii-trabalho-simes/imagens/pagina-006-imagem-001.png>) · 160 × 160 px · página 6.
