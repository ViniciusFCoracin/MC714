def mm1_metrics(lam, mu=1.0, n_servers=3):
    """
    Retorna um dicionário com as métricas analíticas para o sistema
    completo, assumindo divisão igualitária lambda_i = lambda / n_servers
    """
    lam_i = lam / n_servers
    rho = lam_i / mu

    stable = rho < 1.0

    if not stable:
        return {
            "lambda": lam,
            "rho": rho,
            "stable": False,
            "U": None,
            "E[Ni]": None,
            "E[TQ]": None,
            "E[R]": None,
            "E[N]_total": None,
            "X": None,
        }

    E_Ni = rho / (1 - rho)
    E_TQ = rho / (mu * (1 - rho))
    E_R = 1.0 / (mu - lam_i)
    E_N_total = n_servers * E_Ni
    X = lam  # todas as requisições que chegam são atendidas (sistema estável)

    return {
        "lambda": lam,
        "rho": rho,
        "stable": True,
        "U": rho,
        "E[Ni]": E_Ni,
        "E[TQ]": E_TQ,
        "E[R]": E_R,
        "E[N]_total": E_N_total,
        "X": X,
    }


def fluid_approximation_N(t, N0, lam, mu=1.0, n_servers=3):
    """
    Item (f): aproximação fluida para o caso instável (lambda > n_servers*mu):
        N(t) ~= N(0) + (lambda - n_servers*mu) * t
    Aqui N(t) refere-se ao total agregado no sistema (soma das 3 filas).
    """
    return N0 + (lam - n_servers * mu) * t


if __name__ == "__main__":
    for lam in [0.6, 1.2, 1.8, 2.4, 2.7]:
        m = mm1_metrics(lam)
        print(f"lambda={lam:>4}  rho={m['rho']:.3f}  U={m['U']:.3f}  "
              f"E[R]={m['E[R]']:.4f}  E[N]={m['E[N]_total']:.4f}")

    # lambda = 3.3 é instável
    print(mm1_metrics(3.3))
