import csv
import math
import statistics

from scipy import stats

from simulation import run_single_replication, Metrics, Server, Dispatcher, arrival_process
import simpy
from analytical import mm1_metrics

LAMBDAS = [0.6, 1.2, 1.8, 2.4, 2.7]
POLICIES = ["random", "round_robin", "shortest_queue"]
N_REPLICAS = 10
SIM_TIME = 5000.0
WARMUP = 500.0
MU = 1.0
BASE_SEED = 1000  # seed base; cada réplica usa BASE_SEED + índice


def confidence_interval_95(values):
    """Retorna (média, meia-largura do IC 95%) usando distribuição t de Student."""
    n = len(values)
    mean = statistics.mean(values)
    if n < 2:
        return mean, 0.0
    std = statistics.stdev(values)
    t_crit = stats.t.ppf(0.975, df=n - 1)
    half_width = t_crit * std / math.sqrt(n)
    return mean, half_width


def run_all_experiments():
    raw_rows = []
    agg_rows = []

    for policy in POLICIES:
        for lam in LAMBDAS:
            metric_names = ["X", "E[R]", "E[N]", "U1", "U2", "U3"]
            samples = {m: [] for m in metric_names}

            for rep in range(N_REPLICAS):
                seed = BASE_SEED + rep
                result = run_single_replication(
                    policy=policy, lam=lam, mu=MU,
                    sim_time=SIM_TIME, warmup=WARMUP, seed=seed,
                )
                raw_rows.append(result)
                for m in metric_names:
                    samples[m].append(result[m])

            agg_row = {"policy": policy, "lambda": lam, "n_replicas": N_REPLICAS}
            for m in metric_names:
                mean, half_width = confidence_interval_95(samples[m])
                agg_row[f"{m}_mean"] = mean
                agg_row[f"{m}_ci95"] = half_width

            agg_rows.append(agg_row)
            print(f"[OK] policy={policy:15s} lambda={lam}  "
                  f"E[R]={agg_row['E[R]_mean']:.4f} +- {agg_row['E[R]_ci95']:.4f}")

    # salva os CSVs
    with open("resultados/resultados_brutos.csv", "w", newline="") as f:
        fieldnames = list(raw_rows[0].keys())
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(raw_rows)

    with open("resultados/resultados_agregados.csv", "w", newline="") as f:
        fieldnames = list(agg_rows[0].keys())
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(agg_rows)

    print("\nArquivos gerados: resultados_brutos.csv, resultados_agregados.csv")
    return raw_rows, agg_rows


def run_instability_experiment(lam=3.3, mu=MU, sim_time=1000.0, seed=42,
                                policy="random", sample_dt=1.0):
    """
    Item (f): roda uma réplica com lambda instável e registra N(t) (soma das
    3 filas) amostrado a cada `sample_dt` unidades de tempo, para comparar
    com a aproximação fluida N(t) ~= N(0) + (lambda - 3*mu) * t.
    Aqui usamos sim_time menor pois o sistema diverge rapidamente.
    """
    import random as random_module

    rng = random_module.Random(seed)
    env = simpy.Environment()
    metrics = Metrics(n_servers=3, warmup=0.0, sim_time=sim_time)
    servers = [Server(env, i, mu, metrics, rng) for i in range(3)]
    dispatcher = Dispatcher(servers, policy, rng)

    env.process(arrival_process(env, dispatcher, lam, metrics, rng, sim_time))

    samples = []

    def sampler(env, servers, samples, dt):
        while True:
            n_total = sum(s.queue_length() for s in servers)
            samples.append((env.now, n_total))
            yield env.timeout(dt)

    env.process(sampler(env, servers, samples, sample_dt))
    env.run(until=sim_time)

    with open("resultados/instabilidade_N_t.csv", "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["t", "N_simulado"])
        writer.writerows(samples)

    print(f"[OK] Experimento de instabilidade (lambda={lam}) salvo em instabilidade_N_t.csv")
    return samples


def print_analytical_table():
    print("\nTabela analítica (M/M/1, política aleatória) - itens (a)-(b):")
    print(f"{'lambda':>8} {'rho':>8} {'U':>8} {'E[R]':>10} {'E[N]':>10}")
    for lam in LAMBDAS:
        m = mm1_metrics(lam, mu=MU)
        print(f"{lam:8.2f} {m['rho']:8.3f} {m['U']:8.3f} {m['E[R]']:10.4f} {m['E[N]_total']:10.4f}")


if __name__ == "__main__":
    print_analytical_table()
    print()
    run_all_experiments()
    print()
    run_instability_experiment()
