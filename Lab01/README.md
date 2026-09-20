# Balanceador de Carga para um Sistema Distribuído — MC714 Trabalho 1

## Estrutura do código

```
simulation.py: núcleo da simulação (Server, Dispatcher, Metrics, políticas)
analytical.py: modelo analítico M/M/1 (política aleatória) + aproximação fluida
experiments.py: roda os 15 experimentos (3 políticas x 5 lambdas x 10 réplicas)
                + experimento de instabilidade com lambda = 3.3
plots.py: gera os gráficos (E[R], E[N], utilização, Lei de Little,
         N(t) instável) a partir dos CSVs de experiments.py
```

## Como executar

1. Crie um ambiente virtual:
   ```bash
   python3 -m venv venv
   source venv/bin/activate        # Linux/Mac
   venv\Scripts\activate           # Windows
   ```

2. Instale as dependências:
   ```bash
   pip install -r requirements.txt
   ```

3. Rode a bateria completa de experimentos:
   ```bash
   python3 experiments.py
   ```

   Isso gera:
   - `resultados_brutos.csv` — uma linha por réplica
   - `resultados_agregados.csv` — média e IC 95% de X, E[R], E[N], U1, U2, U3
     por (política, lambda)
   - `instabilidade_N_t.csv` — série temporal de N(t) para o caso instável (λ = 3.3)

4. Para rodar só uma réplica isolada:
   ```bash
   python3 simulation.py
   ```

5. Para ver a tabela do modelo analítico isoladamente:
   ```bash
   python3 analytical.py
   ```

6. Depois de rodar `experiments.py`, gere os gráficos:
   ```bash
   python3 plots.py
   ```
   Isso gera, na pasta resultados:
   - `ER_vs_lambda.png` — E[R] analítico x simulado (3 políticas), com IC 95%
   - `EN_vs_lambda.png` — mesma comparação para E[N]
   - `utilization_vs_lambda.png` — confirma que U não depende da política
   - `little_law_check.png` — confirma a Lei de Little
   - `instability_Nt.png` — simula para λ=3.3


## Observações de design

- A simulação usa **SimPy**.
- `E[N]` é calculado por integração no tempo de N(t) (área sob a curva
  dividida pela duração), conforme recomendado no enunciado — e não pela
  média sobre as chegadas.
- O período de warm-up (500 u.t.) é descartado: requisições que chegam
  antes do fim do warm-up não entram nas estatísticas de tempo de resposta,
  e a integração de N(t)/utilização considera apenas o intervalo
  `[warmup, sim_time]`.
- Cada réplica usa uma seed diferente (`BASE_SEED + índice da réplica`) para
  garantir reprodutibilidade e independência entre réplicas.
