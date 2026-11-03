# MC714 — Trabalho 2: Bully (eleição) + detector de falhas por heartbeat

Dois algoritmos complementares, conforme o enunciado:
**(grupo 1) Eleição de líder — Valentão (Bully)** e
**(grupo 2) Detecção de falhas — heartbeat**, integrados: o detector dispara
a eleição quando suspeita do líder e a eleição ignora pares suspeitos.

## Estrutura

```
bully/
  config.py      parâmetros (variáveis de ambiente)
  transport.py   TCP + JSON, timeouts explícitos, injeção de perda/atraso/partição
  detector.py    detector de falhas por heartbeat (timeout adaptativo opcional)
  node.py        algoritmo Bully integrado ao detector
  main.py        entrada de um nó (um processo/contêiner por nó)
  ctl.py         comando de controle (partição em nós em execução)
tests/
  test_bully.py  testes automatizados (normal, crash, recuperação, perda, partição)
  log_checks.py  verificação das propriedades a partir dos logs .jsonl
experiments/
  run_experiments.py  experimento automatizado (variando N) + resumo p50/p95
  plot_results.py     gráficos
Dockerfile, compose.yaml, Makefile, requirements.txt
```

## Como executar

```bash
pip install -r requirements.txt

make test           # ou: python -m pytest -v tests/
make experiments    # ou: python experiments/run_experiments.py --nodes 3 5 7 9 --reps 10 --out results
make plots

# Ambiente de referência (Docker Compose v2) -- NÃO testado no ambiente de desenvolvimento do template
make up             # docker compose up --build -d
make crash-leader   # docker kill node5  (crash-stop do líder)
make logs           # acompanha eleição e recuperação (cenário do vídeo)
make down
```

Reiniciar o líder morto (recuperação): `docker start node5` — ele sobe sem estado
e retoma a liderança (propriedade do Bully: maior id vence).

Partição em contêineres: `python -m bully.ctl <host> <porta> --block 4 5`
(o nó passa a ignorar 4 e 5); sem `--block` remove os bloqueios.

## Modelo do sistema (rascunho — revisar e justificar no relatório)

| Item | Hipótese adotada |
|---|---|
| Modelo temporal | **Parcialmente síncrono**: limites de atraso existem mas são desconhecidos/instáveis; timeouts fixos podem gerar falsas suspeitas, e o timeout adaptativo (`HB_TIMEOUT_INCREMENT`) busca acurácia eventual (◊P) |
| Canais | Ponto a ponto sobre TCP (uma conexão curta por mensagem), sem duplicação; perda e atraso **injetados** (`LOSS`, `DELAY_MS`); com atraso a ordem não é garantida |
| Falhas | **Crash-stop** (SIGKILL); reinício = nova incarnação **sem estado persistente** (crash-recovery simples); partições de rede injetadas; **sem falhas bizantinas** |
| Relógios | Nenhuma sincronização é usada pelo algoritmo (só intervalos locais monotônicos); os timestamps dos logs são do relógio da máquina — válidos para medir tempos porque todos os nós rodam no mesmo host |
| Persistência | Nenhuma |

**Propriedades** (verificadas em `tests/` e `tests/log_checks.py`):
S1 acordo (em quiescência todos os vivos têm o mesmo líder) · S2 validade
(o líder é o maior id vivo) · L1 terminação (após crash do líder, todos os vivos
adotam novo líder em tempo limitado) · FD1 completude (crashado é suspeito por
todos os vivos) · FD2 acurácia (sem falhas/perdas, ninguém vivo é suspeito).
Com **partição**, S1/S2 valem só *dentro de cada lado*; após a cura, o conflito é
resolvido pelos heartbeats (`leader_conflict` em `node.py`).

**Complexidade esperada:** heartbeats all-to-all = O(N²) por período; eleição = O(N²)
mensagens no pior caso (o experimento mede isso). O detector de falhas torna o
tempo de recuperação ≈ `HB_TIMEOUT` + custo da eleição.

## Experimentos (já automatizados)

* Parâmetro variado: **N ∈ {3,5,7,9}** (≥ 3 níveis); 10 repetições com sementes
  `1000..1009`; cenário: crash do líder (SIGKILL) após estado estacionário.
* Métricas: tempo de detecção, tempo de convergência (média, desvio, **p50, p95**)
  e nº de mensagens de eleição. Hardware/SO/versões ficam em `results/env.json`.
* Ablação disponível: `--no-fd-in-election` (Bully clássico sem usar o detector).
* Outros eixos fáceis de adicionar: `--loss 0 0.1 0.2`, `--delay-ms`, `--hb-timeout`.

Observação do smoke test: a convergência às vezes é ~`election_timeout` mais lenta
(nó pergunta a um maior que ainda não suspeitou da queda) — bom ponto de discussão.

## O que falta (TODO da dupla)

- [ ] Rodar o experimento completo **na máquina de referência** e registrar `env.json`
- [ ] Mais níveis/cenários: perda de mensagens, partição+cura, falhas combinadas (bônus)
- [ ] Testar `compose.yaml` em Docker Compose v2 (não testado aqui)
- [ ] Relatório IEEE 2 colunas, ≤ 6 páginas (+ nome/RA, link do GitLab, link do vídeo na 1ª página)
- [ ] Vídeo (~5 min, **dois integrantes**): cenário normal → crash do líder → reeleição/recuperação
- [ ] Citar código reutilizado (se houver) e a tag de entrega no repositório
- [ ] Discutir limites: contêineres no mesmo host não são domínios de falha independentes
- [ ] (Bônus) terceiro algoritmo / integração / execução na nuvem do IC
