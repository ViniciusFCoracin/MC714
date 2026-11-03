"""
detector.py
-----------
Detector de falhas por heartbeat (all-to-all, sem estado persistente).

Cada nó envia HB a todos a cada hb_interval; um par é SUSPEITO se não for
ouvido por mais que `timeout`. Se um suspeito voltar a ser ouvido, ele é
"re-confiado" e (opcionalmente) o timeout daquele par cresce em `increment`
-- a adaptação que, sob sincronia parcial, leva a um detector eventualmente
perfeito (◊P). Propriedades alvo:
    * completude forte: todo nó que sofre crash é suspeito por todo nó correto
    * acurácia eventual: após algum tempo, nenhum nó correto é suspeito
"""
from __future__ import annotations

import time


class HeartbeatDetector:
    def __init__(self, peer_ids, timeout, on_suspect, on_trust, increment=0.0,
                 clock=time.monotonic):
        self.clock = clock
        now = clock()
        self.timeouts = {p: timeout for p in peer_ids}
        self.last_seen = {p: now for p in peer_ids}
        self.suspected: set[int] = set()
        self.increment = increment
        self.on_suspect = on_suspect
        self.on_trust = on_trust

    def heartbeat(self, src: int):
        if src not in self.last_seen:
            return
        self.last_seen[src] = self.clock()
        if src in self.suspected:
            self.suspected.discard(src)
            self.timeouts[src] += self.increment   # falso positivo -> afrouxa
            self.on_trust(src)

    def check(self):
        now = self.clock()
        for p, seen in self.last_seen.items():
            if p not in self.suspected and now - seen > self.timeouts[p]:
                self.suspected.add(p)
                self.on_suspect(p)
