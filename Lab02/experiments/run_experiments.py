"""
run_experiments.py
------------------
Experimento automatizado e reproduzível: tempo de recuperação após o crash
do líder, variando o número de nós N.

Para cada (N, repetição):
  1. sobe N processos `python -m bully.main` (um por nó lógico, em localhost)
  2. espera todos concordarem em líder = N (maior id)
  3. janela de estado estacionário (mede tráfego de fundo)
  4. mata o líder com SIGKILL (crash-stop) em t0
  5. espera todos os vivos concordarem em líder = N-1
  6. extrai métricas dos logs .jsonl (mesmas funções usadas nos testes)

Métricas:
  detect_first / detect_all  tempo até o 1º / último nó vivo suspeitar do líder
  convergence                tempo até todos os vivos adotarem o novo líder
  election_msgs              mensagens ELECTION+ANSWER+COORDINATOR após t0 (sem HB)
  false_suspicions           suspeitas sobre nós vivos (deve ser ~0)

Uso:
    python experiments/run_experiments.py --nodes 3 5 7 9 --reps 10 --out results
    python experiments/run_experiments.py --nodes 3 5 --reps 2 --out /tmp/smoke   # rápido

Saídas em --out:  raw.csv, summary.csv, env.json
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pandas as pd

ELECTION_TYPES = {"ELECTION", "ANSWER", "COORDINATOR"}
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from tests import log_checks as lc  # noqa: E402


def free_ports(n):
    socks = [socket.socket() for _ in range(n)]
    for s in socks:
        s.bind(("127.0.0.1", 0))
    ports = [s.getsockname()[1] for s in socks]
    for s in socks:
        s.close()
    return ports


def read_events(logdir: Path):
    events = []
    for f in logdir.glob("node_*.jsonl"):
        for line in f.read_text().splitlines():
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                pass          # linha truncada pelo SIGKILL
    return events


def wait_for(pred, timeout, step=0.05):
    end = time.time() + timeout
    while time.time() < end:
        if pred():
            return True
        time.sleep(step)
    return False


def run_once(n, seed, args):
    ports = free_ports(n)
    peers = ",".join(f"{i + 1}=127.0.0.1:{ports[i]}" for i in range(n))
    logdir = Path(tempfile.mkdtemp(prefix=f"bully_n{n}_s{seed}_"))
    procs = {}
    try:
        for i in range(1, n + 1):
            env = {**os.environ, "NODE_ID": str(i), "PEERS": peers,
                   "HB_INTERVAL": str(args.hb_interval), "HB_TIMEOUT": str(args.hb_timeout),
                   "ELECTION_TIMEOUT": str(args.election_timeout),
                   "COORDINATOR_TIMEOUT": str(args.election_timeout * 2),
                   "STARTUP_DELAY": "0.3", "LOSS": str(args.loss),
                   "DELAY_MS": str(args.delay_ms), "SEED": str(seed),
                   "USE_FD_IN_ELECTION": "1" if args.use_fd else "0",
                   "LOG_PATH": str(logdir / f"node_{i}.jsonl"), "LOG_STDOUT": "0",
                   "PYTHONPATH": str(ROOT)}
            procs[i] = subprocess.Popen([sys.executable, "-m", "bully.main"], env=env,
                                        cwd=ROOT, stdout=subprocess.DEVNULL)
        alive = set(range(1, n + 1))
        if not wait_for(lambda: lc.agreement(read_events(logdir), alive) == n, 20):
            raise RuntimeError("cluster não convergiu na partida")
        time.sleep(args.steady)

        t0 = time.time()
        procs[n].kill()                       # SIGKILL = crash-stop
        procs[n].wait()
        alive.discard(n)
        ok = wait_for(lambda: lc.agreement(read_events(logdir), alive) == n - 1, 30)
        time.sleep(0.6)                       # captura 'stats' finais
        ev = read_events(logdir)

        det = [v for v in lc.detection_times(ev, t0, n, alive).values() if v is not None]
        conv = lc.convergence_time(ev, t0, alive, n - 1) if ok else None
        return {
            "n": n, "seed": seed, "converged": ok,
            "detect_first": min(det) if det else None,
            "detect_all": max(det) if len(det) == len(alive) else None,
            "convergence": conv,
            "election_msgs": lc.total_sent(ev, t0, max(e["ts"] for e in ev),
                                           types=ELECTION_TYPES) if ok else None,
            "false_suspicions": lc.false_suspicions(ev, truly_dead={n}),
        }
    finally:
        for p in procs.values():
            if p.poll() is None:
                p.kill()
                p.wait()


def summarize(df):
    """Média, desvio, p50 e p95 de cada métrica, por número de nós."""
    metrics = ["detect_first", "detect_all", "convergence", "election_msgs"]
    ok = df[df.converged]
    rows = []
    for n, g in ok.groupby("n"):
        row = {"n": n, "reps_ok": len(g)}
        for m in metrics:
            row[f"{m}_mean"] = g[m].mean()
            row[f"{m}_std"] = g[m].std()
            row[f"{m}_p50"] = g[m].quantile(0.5)
            row[f"{m}_p95"] = g[m].quantile(0.95)
        row["false_suspicions_total"] = int(df[df.n == n].false_suspicions.sum())
        rows.append(row)
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--nodes", type=int, nargs="+", default=[3, 5, 7, 9])
    ap.add_argument("--reps", type=int, default=10)
    ap.add_argument("--base-seed", type=int, default=1000)
    ap.add_argument("--hb-interval", type=float, default=0.1)
    ap.add_argument("--hb-timeout", type=float, default=0.5)
    ap.add_argument("--election-timeout", type=float, default=0.3)
    ap.add_argument("--loss", type=float, default=0.0)
    ap.add_argument("--delay-ms", type=float, default=0.0)
    ap.add_argument("--steady", type=float, default=1.0)
    ap.add_argument("--no-fd-in-election", dest="use_fd", action="store_false")
    ap.add_argument("--out", default="results")
    args = ap.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "env.json").write_text(json.dumps({
        "platform": platform.platform(), "python": sys.version, "cpus": os.cpu_count(),
        "machine": platform.machine(), "processor": platform.processor(),
        "args": vars(args), "date": time.strftime("%Y-%m-%d %H:%M:%S"),
    }, indent=2))

    rows = []
    for n in args.nodes:
        for r in range(args.reps):
            row = run_once(n, args.base_seed + r, args)
            rows.append(row)
            print(f"N={n} seed={row['seed']} ok={row['converged']} "
                  f"detect={row['detect_first']} conv={row['convergence']} "
                  f"election_msgs={row['election_msgs']}", flush=True)
    df = pd.DataFrame(rows)
    df.to_csv(out / "raw.csv", index=False)
    summarize(df).to_csv(out / "summary.csv", index=False)
    print(f"\nResultados em {out}/ (raw.csv, summary.csv, env.json)")


if __name__ == "__main__":
    main()
