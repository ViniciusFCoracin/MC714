"""
plot_results.py -- gráficos a partir de results/raw.csv e results/summary.csv.

    python experiments/plot_results.py --in results

Gera: convergence_vs_n.png (média ± desvio, p50 e p95) e election_msgs_vs_n.png
(com referência quadrática N(N-1), pior caso do Bully).
"""
import argparse
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

ap = argparse.ArgumentParser()
ap.add_argument("--in", dest="inp", default="results")
a = ap.parse_args()
d = Path(a.inp)
s = pd.read_csv(d / "summary.csv")

fig, ax = plt.subplots(figsize=(5, 3.6))
ax.errorbar(s.n, s.convergence_mean, yerr=s.convergence_std, fmt="o-", capsize=3, label="média ± desvio")
ax.plot(s.n, s.convergence_p50, "s--", label="p50")
ax.plot(s.n, s.convergence_p95, "^--", label="p95")
ax.plot(s.n, s.detect_all_mean, "k:", label="detecção (último nó)")
ax.set_xlabel("número de nós N")
ax.set_ylabel("tempo (s)")
ax.set_title("Recuperação após crash do líder")
ax.grid(True, ls="--", alpha=.5)
ax.legend(fontsize=8)
fig.tight_layout()
fig.savefig(d / "convergence_vs_n.png", dpi=200)

fig, ax = plt.subplots(figsize=(5, 3.6))
ax.errorbar(s.n, s.election_msgs_mean, yerr=s.election_msgs_std, fmt="o-", capsize=3, label="medido")
ax.plot(s.n, s.n * (s.n - 1), "k--", label="N(N-1) (referência)")
ax.set_xlabel("número de nós N")
ax.set_ylabel("mensagens ELECTION+ANSWER+COORDINATOR")
ax.set_title("Custo da eleição")
ax.grid(True, ls="--", alpha=.5)
ax.legend(fontsize=8)
fig.tight_layout()
fig.savefig(d / "election_msgs_vs_n.png", dpi=200)
print("gráficos salvos em", d)
