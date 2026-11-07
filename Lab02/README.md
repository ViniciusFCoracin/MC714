# MC714 — Trabalho 2
# Eleição pelo algoritmo do valentão e detector de falhas por heartbeat

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

python -m pytest -v tests/
python experiments/run_experiments.py --nodes 3 5 7 9 --reps 10 --out results
python experiments/plot_results.py --in results   

docker compose up --build -d    # sobe os 5 nós em contêineres
docker compose logs -f          # acompanha os eventos de todos os nós
docker kill node5               # crash-stop do líder atual (nó 5)
docker start node5              # retoma o nó 5
docker compose down -v          # derruba e remove tudo
```
