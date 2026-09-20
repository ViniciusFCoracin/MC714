import pandas as pd
import matplotlib.pyplot as plt

from analytical import mm1_metrics, fluid_approximation_N

AGG_CSV = "resultados/resultados_agregados.csv"
NT_CSV = "resultados/instabilidade_N_t.csv"

POLICY_LABELS = {
    "random": "Aleatória",
    "round_robin": "Round Robin",
    "shortest_queue": "Fila Mais Curta",
}
POLICY_MARKERS = {
    "random": "o",
    "round_robin": "s",
    "shortest_queue": "^",
}

MU = 1.0


def _lambda_range(df):
    return sorted(df["lambda"].unique())


def plot_metric_vs_lambda(df, metric_mean_col, metric_ci_col, metric_key_analitico,
                           ylabel, title, filename):
    """
    Função genérica: plota, para cada política, os pontos simulados
    (média + IC95%) de uma métrica em função de lambda, sobrepondo a
    curva analítica (válida exatamente para a política aleatória e,
    no caso de X e U, para as três, por conservação de trabalho).
    """
    lambdas = _lambda_range(df)

    fig, ax = plt.subplots(figsize=(6, 4.5))

    # curva analítica (linha contínua)
    lambdas_analitico = [l for l in lambdas if l < 3 * MU]  # só pontos estáveis
    valores_analiticos = [mm1_metrics(l, mu=MU)[metric_key_analitico] for l in lambdas_analitico]
    ax.plot(lambdas_analitico, valores_analiticos, "k-", linewidth=1.5,
            label="Analítico (M/M/1, política aleatória)")

    # pontos simulados de cada política
    for policy in ["random", "round_robin", "shortest_queue"]:
        sub = df[df["policy"] == policy].sort_values("lambda")
        ax.errorbar(
            sub["lambda"], sub[metric_mean_col], yerr=sub[metric_ci_col],
            fmt=POLICY_MARKERS[policy], capsize=3, markersize=6,
            label=f"Simulado ({POLICY_LABELS[policy]})",
        )

    ax.set_xlabel(r"$\lambda$ (requisições por unidade de tempo)")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.legend(fontsize=8)
    ax.grid(True, linestyle="--", alpha=0.5)
    fig.tight_layout()
    fig.savefig(f"resultados/{filename}", dpi=200)
    plt.close(fig)
    print(f"[OK] {filename}")


def plot_utilization(df, filename="utilization_vs_lambda.png"):
    """Item (c): U não depende da política -> plota U médio (média de U1,U2,U3)
    de cada política e compara com o valor analítico rho."""
    lambdas = _lambda_range(df)
    df = df.copy()
    df["U_mean"] = df[["U1_mean", "U2_mean", "U3_mean"]].mean(axis=1)
    # combina o IC das 3 utilizações (aproximação: média dos IC's)
    df["U_ci"] = df[["U1_ci95", "U2_ci95", "U3_ci95"]].mean(axis=1)

    fig, ax = plt.subplots(figsize=(6, 4.5))

    lambdas_analitico = [l for l in lambdas if l < 3 * MU]
    rho_analitico = [mm1_metrics(l, mu=MU)["U"] for l in lambdas_analitico]
    ax.plot(lambdas_analitico, rho_analitico, "k-", linewidth=1.5,
            label=r"Analítico ($\rho = \lambda/(3\mu)$)")

    for policy in ["random", "round_robin", "shortest_queue"]:
        sub = df[df["policy"] == policy].sort_values("lambda")
        ax.errorbar(
            sub["lambda"], sub["U_mean"], yerr=sub["U_ci"],
            fmt=POLICY_MARKERS[policy], capsize=3, markersize=6,
            label=f"Simulado ({POLICY_LABELS[policy]})",
        )

    ax.set_xlabel(r"$\lambda$ (requisições por unidade de tempo)")
    ax.set_ylabel(r"Utilização média dos servidores $U_i$")
    ax.set_title("Utilização vs. $\\lambda$ (independe da política)")
    ax.legend(fontsize=8)
    ax.grid(True, linestyle="--", alpha=0.5)
    fig.tight_layout()
    fig.savefig(f"resultados/{filename}", dpi=200)
    plt.close(fig)
    print(f"[OK] {filename}")


def plot_little_law_check(df, filename="little_law_check.png"):
    """Item (e): E[N] simulado vs X*E[R] simulado -> pontos devem cair em y=x."""
    fig, ax = plt.subplots(figsize=(5, 5))

    df = df.copy()
    df["X_times_ER"] = df["X_mean"] * df["E[R]_mean"]

    max_val = max(df["E[N]_mean"].max(), df["X_times_ER"].max()) * 1.1
    ax.plot([0, max_val], [0, max_val], "k--", linewidth=1, label="$y = x$ (Lei de Little)")

    for policy in ["random", "round_robin", "shortest_queue"]:
        sub = df[df["policy"] == policy]
        ax.scatter(sub["X_times_ER"], sub["E[N]_mean"],
                   marker=POLICY_MARKERS[policy], s=60,
                   label=POLICY_LABELS[policy])

    ax.set_xlabel(r"$X \cdot E[R]$ (simulado)")
    ax.set_ylabel(r"$E[N]$ (simulado)")
    ax.set_title("Verificação da Lei de Little")
    ax.legend(fontsize=8)
    ax.grid(True, linestyle="--", alpha=0.5)
    ax.set_aspect("equal")
    fig.tight_layout()
    fig.savefig(f"resultados/{filename}", dpi=200)
    plt.close(fig)
    print(f"[OK] {filename}")


def plot_instability(nt_csv=NT_CSV, lam=3.3, mu=MU, n_servers=3,
                      filename="instability_Nt.png"):
    """Item (f): N(t) simulado x aproximação fluida, para lambda instável."""
    df = pd.read_csv(nt_csv)

    fig, ax = plt.subplots(figsize=(6, 4.5))
    ax.plot(df["t"], df["N_simulado"], label="$N(t)$ simulado", linewidth=1)

    N0 = df["N_simulado"].iloc[0]
    t_vals = df["t"]
    fluid_vals = [fluid_approximation_N(t, N0, lam, mu, n_servers) for t in t_vals]
    ax.plot(t_vals, fluid_vals, "k--",
            label=r"Aproximação fluida: $N(0) + (\lambda - 3\mu)t$")

    ax.set_xlabel("t (unidades de tempo)")
    ax.set_ylabel("N(t) (total no sistema)")
    ax.set_title(f"Caso instável: $\\lambda = {lam}$ (> $3\\mu = {n_servers*mu}$)")
    ax.legend(fontsize=8)
    ax.grid(True, linestyle="--", alpha=0.5)
    fig.tight_layout()
    fig.savefig(f"resultados/{filename}", dpi=200)
    plt.close(fig)
    print(f"[OK] {filename}")


def main():
    df = pd.read_csv(AGG_CSV)

    plot_metric_vs_lambda(
        df, metric_mean_col="E[R]_mean", metric_ci_col="E[R]_ci95",
        metric_key_analitico="E[R]",
        ylabel="E[R] (tempo médio de resposta)",
        title="Tempo médio de resposta vs. $\\lambda$",
        filename="ER_vs_lambda.png",
    )

    plot_metric_vs_lambda(
        df, metric_mean_col="E[N]_mean", metric_ci_col="E[N]_ci95",
        metric_key_analitico="E[N]_total",
        ylabel="E[N] (nº médio de requisições no sistema)",
        title="Número médio no sistema vs. $\\lambda$",
        filename="EN_vs_lambda.png",
    )

    plot_utilization(df)
    plot_little_law_check(df)

    try:
        plot_instability()
    except FileNotFoundError:
        print(f"[aviso] {NT_CSV} não encontrado; rode "
              f"experiments.run_instability_experiment() antes.")


if __name__ == "__main__":
    main()
