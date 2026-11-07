"""
config.py
---------
Parâmetros de um nó. Em contêiner, tudo vem de variáveis de ambiente
(mesma imagem em qualquer ambiente; só a configuração muda).

Variáveis de ambiente reconhecidas (todas opcionais, exceto NODE_ID e PEERS):
    NODE_ID              id inteiro do nó (maior id = maior prioridade no Bully)
    PEERS                "1=host1:7000,2=host2:7000,..."  (inclui o próprio nó)
    HB_INTERVAL          período de envio de heartbeats (s)
    HB_TIMEOUT           silêncio máximo antes de suspeitar de um par (s)
    HB_TIMEOUT_INCREMENT >0 liga o timeout adaptativo (detector tipo ◊P)
    ELECTION_TIMEOUT     espera por ANSWER após enviar ELECTION (s)
    COORDINATOR_TIMEOUT  espera por COORDINATOR após receber ANSWER (s)
    CONNECT_TIMEOUT      timeout explícito de conexão/escrita TCP (s)
    STARTUP_DELAY        espera antes da primeira eleição (s)
    FD_STARTUP_GRACE     janela inicial antes de habilitar suspeitas (s); por padrão,
                         STARTUP_DELAY + HB_TIMEOUT
    USE_FD_IN_ELECTION   1/0: eleição ignora pares suspeitos (padrão 1)
    FD_EARLY_ABORT       1/0: encerra a espera por ANSWER assim que o detector passa a
                         suspeitar de todos os nós consultados (padrão 1)
    LOSS                 probabilidade [0,1] de descartar cada mensagem enviada
    DELAY_MS             atraso máximo (uniforme) injetado em cada envio (ms)
    SEED                 semente do RNG de falhas (reprodutibilidade)
    LOG_PATH             arquivo .jsonl de eventos (opcional)
    LOG_STDOUT           1/0: também imprime eventos na saída padrão
"""
from __future__ import annotations

import os
from dataclasses import dataclass


def parse_peers(spec: str) -> dict[int, tuple[str, int]]:
    """'1=h1:7000,2=h2:7000' -> {1: ('h1', 7000), 2: ('h2', 7000)}"""
    peers: dict[int, tuple[str, int]] = {}
    for item in spec.split(","):
        item = item.strip()
        if not item:
            continue
        pid, addr = item.split("=")
        host, port = addr.rsplit(":", 1)
        peers[int(pid)] = (host, int(port))
    return peers


@dataclass
class Config:
    node_id: int
    peers: dict  # id -> (host, port), inclui o próprio nó
    hb_interval: float = 0.5
    hb_timeout: float = 2.0
    hb_timeout_increment: float = 0.0
    election_timeout: float = 1.0
    coordinator_timeout: float = 2.0
    connect_timeout: float = 0.5
    startup_delay: float = 0.5
    fd_startup_grace: float | None = None
    use_fd_in_election: bool = True
    fd_early_abort: bool = True
    loss: float = 0.0
    delay_ms: float = 0.0
    seed: int = 0
    log_path: str | None = None
    log_stdout: bool = True

    @classmethod
    def from_env(cls, env=os.environ) -> "Config":
        g = env.get
        return cls(
            node_id=int(env["NODE_ID"]),
            peers=parse_peers(env["PEERS"]),
            hb_interval=float(g("HB_INTERVAL", 0.5)),
            hb_timeout=float(g("HB_TIMEOUT", 2.0)),
            hb_timeout_increment=float(g("HB_TIMEOUT_INCREMENT", 0.0)),
            election_timeout=float(g("ELECTION_TIMEOUT", 1.0)),
            coordinator_timeout=float(g("COORDINATOR_TIMEOUT", 2.0)),
            connect_timeout=float(g("CONNECT_TIMEOUT", 0.5)),
            startup_delay=float(g("STARTUP_DELAY", 0.5)),
            fd_startup_grace=(
                float(g("FD_STARTUP_GRACE"))
                if g("FD_STARTUP_GRACE") else None
            ),
            use_fd_in_election=g("USE_FD_IN_ELECTION", "1") not in ("0", "false"),
            fd_early_abort=g("FD_EARLY_ABORT", "1") not in ("0", "false"),
            loss=float(g("LOSS", 0.0)),
            delay_ms=float(g("DELAY_MS", 0.0)),
            seed=int(g("SEED", 0)),
            log_path=g("LOG_PATH") or None,
            log_stdout=g("LOG_STDOUT", "1") not in ("0", "false"),
        )
