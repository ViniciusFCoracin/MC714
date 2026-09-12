# Balanceador de Carga para um Sistema Distribuído — MC714 Trabalho 1

## Estrutura do código

```
simulation.py    -> núcleo da simulação (Server, Dispatcher, Metrics, políticas)
analytical.py    -> modelo analítico M/M/1 (política aleatória) + aproximação fluida
experiments.py   -> roda os 15 experimentos (3 políticas x 5 lambdas x 10 réplicas)
                     + experimento de instabilidade com lambda = 3.3
requirements.txt -> dependências Python
```

## Como executar

1. Crie um ambiente virtual (opcional, mas recomendado):
   ```bash
   python3 -m venv venv
   source venv/bin/activate        # Linux/Mac
   venv\Scripts\activate           # Windows
   ```

2. Instale as dependências:
   ```bash
   pip install -r requirements.txt
   ```

3. Rode a bateria completa de experimentos (leva alguns minutos, pois são
   15 configurações x 10 réplicas de 5000 unidades de tempo):
   ```bash
   python3 experiments.py
   ```

   Isso gera:
   - `resultados_brutos.csv` — uma linha por réplica (útil para conferência/depuração)
   - `resultados_agregados.csv` — média e IC 95% de X, E[R], E[N], U1, U2, U3
     por (política, lambda)
   - `instabilidade_N_t.csv` — série temporal de N(t) para o caso instável (λ = 3.3)

4. Para rodar só uma réplica isolada (ex.: para debug ou para o cheque de
   sanidade sugerido no enunciado — λ pequeno deve dar E[R] ≈ 1):
   ```bash
   python3 simulation.py
   ```

5. Para ver a tabela do modelo analítico isoladamente:
   ```bash
   python3 analytical.py
   ```

## O que falta implementar / ajustar (TODO da dupla)

- [ ] Script de geração dos gráficos (E[R] analítico x simulado, com barras de
      erro de 95%) a partir de `resultados_agregados.csv` — sugestão: usar
      matplotlib/pandas.
- [ ] Verificação explícita da Lei de Little (E[N] = X · E[R]) a partir dos
      CSVs gerados (item e).
- [ ] Comparação/quantificação do ganho percentual de cada política em
      relação à aleatória (item d) — pode ser feito em um notebook/script
      separado a partir de `resultados_agregados.csv`.
- [ ] Gráfico de N(t) simulado x aproximação fluida para λ = 3.3 (item f),
      usando `instabilidade_N_t.csv` e `analytical.fluid_approximation_N`.
- [ ] (Opcional, ponto extra) Buffer finito M/M/1/K ou servidores
      heterogêneos — ainda não implementado neste template.
- [ ] Descrição da divisão de trabalho entre os integrantes da dupla.
- [ ] Relatório em IEEE (2 colunas), até 4 páginas.

## Observações de design

- A simulação usa **SimPy**, permitido pelo enunciado.
- `E[N]` é calculado por integração no tempo de N(t) (área sob a curva
  dividida pela duração), conforme recomendado no enunciado — e não pela
  média sobre as chegadas.
- O período de warm-up (500 u.t.) é descartado: requisições que chegam
  antes do fim do warm-up não entram nas estatísticas de tempo de resposta,
  e a integração de N(t)/utilização considera apenas o intervalo
  `[warmup, sim_time]`.
- Cada réplica usa uma seed diferente (`BASE_SEED + índice da réplica`) para
  garantir reprodutibilidade e independência entre réplicas.
