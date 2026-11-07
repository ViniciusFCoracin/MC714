"""
log_checks.py
-------------
Verificações reproduzíveis de PROPRIEDADES DE CORREÇÃO a partir dos logs de
eventos (lista de dicts com ts/node/event/...). Usado pelos testes e pelo
harness de experimentos.

Propriedades (Bully + detector de falhas), sem partições e com FD eventualmente
acurado:
  S1 (acordo)        em quiescência, todos os nós vivos têm o MESMO líder
  S2 (validade)      esse líder é o MAIOR id entre os nós vivos
  L1 (terminação)    após o crash do líder, todo nó vivo adota um novo líder
                     dentro de um limite de tempo
  FD1 (completude)   todo nó que sofreu crash é suspeito por todo nó vivo
  FD2 (acurácia)     nenhum nó vivo é suspeito (em execuções sem falhas/perdas)
"""
from __future__ import annotations

import collections


def final_leaders(events, alive):
    """Último valor de 'leader' registrado por cada nó vivo."""
    last = {n: None for n in alive}
    for e in sorted(events, key=lambda e: e["ts"]):
        if e["event"] == "leader" and e["node"] in last:
            last[e["node"]] = e["leader"]
    return last


def agreement(events, alive):
    """S1: devolve o líder comum, ou None se houver divergência."""
    leaders = set(final_leaders(events, alive).values())
    return leaders.pop() if len(leaders) == 1 else None


def convergence_time(events, t0, alive, expected):
    """
    L1: tempo (s) desde t0 até o último nó vivo adotar `expected` como líder.
    None se algum nó vivo não terminou com `expected`.
    """
    if any(v != expected for v in final_leaders(events, alive).values()):
        return None
    t_last = t0
    for e in events:
        if (e["event"] == "leader" and e["node"] in alive
                and e["leader"] == expected and e["ts"] >= t0):
            t_last = max(t_last, e["ts"])
    return t_last - t0


def detection_times(events, t0, crashed, alive):
    """FD1: por nó vivo, tempo até suspeitar do nó `crashed` (None se nunca)."""
    out = {n: None for n in alive}
    for e in sorted(events, key=lambda e: e["ts"]):
        if (e["event"] == "suspect" and e["peer"] == crashed and e["node"] in out
                and out[e["node"]] is None and e["ts"] >= t0):
            out[e["node"]] = e["ts"] - t0
    return out


def false_suspicions(events, truly_dead=(), since=None):
    """FD2: nº de suspeitas de pares vivos após um instante opcional."""
    return sum(1 for e in events
               if (e["event"] == "suspect"
                   and e["peer"] not in truly_dead
                   and (since is None or e["ts"] >= since)))


def total_sent(events, t0, t1, types=None):
    """
    Mensagens enviadas (todos os nós) entre t0 e t1, via eventos 'stats'
    (contadores cumulativos por tipo). `types` filtra por tipo de mensagem,
    ex.: {"ELECTION", "ANSWER", "COORDINATOR"} (custo da eleição, sem HB).
    """
    per_node = collections.defaultdict(list)
    for e in events:
        if e["event"] == "stats":
            c = sum(v for k, v in e["sent"].items() if types is None or k in types)
            per_node[e["node"]].append((e["ts"], c))
    total = 0
    for series in per_node.values():
        series.sort()

        def at(t):
            v = 0
            for ts, c in series:
                if ts <= t:
                    v = c
            return v
        total += at(t1) - at(t0)
    return total
