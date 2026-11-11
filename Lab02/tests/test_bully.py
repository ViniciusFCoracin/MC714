"""
Testes de correção do Bully + detector de falhas.

Os nós rodam no mesmo processo (asyncio), mas se comunicam por TCP real em
localhost, exatamente como nos contêineres. Crash-stop = Node.stop() (sem aviso).

Executar:  python -m pytest -v tests/
"""
import asyncio
import time as _t

from bully.config import Config
from bully.netutil import reserve_ports
from bully.node import Node
from tests import log_checks as lc

FAST = dict(hb_interval=0.05, hb_timeout=0.3, election_timeout=0.2,
            coordinator_timeout=0.5, connect_timeout=0.2, startup_delay=0.1,
            log_stdout=False)


class Cluster:
    def __init__(self, n, **overrides):
        ports = reserve_ports(n)
        self.peers = {i + 1: ("127.0.0.1", ports[i]) for i in range(n)}
        self.params = {**FAST, **overrides}
        self.events: list[dict] = []
        self.nodes: dict[int, Node] = {}

    async def start(self, ids=None):
        for i in (ids or self.peers):
            await self.start_node(i)

    async def start_node(self, i):
        cfg = Config(node_id=i, peers=self.peers, **self.params)
        self.nodes[i] = Node(cfg, on_event=self.events.append)
        await self.nodes[i].start()

    async def crash(self, i):
        await self.nodes.pop(i).stop()

    async def stop_all(self):
        for n in list(self.nodes.values()):
            await n.stop()
        self.nodes.clear()

    def leaders(self):
        return {i: n.leader for i, n in self.nodes.items()}


async def wait_until(pred, timeout=8.0, step=0.02):
    end = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < end:
        if pred():
            return True
        await asyncio.sleep(step)
    return False


async def all_detected(c, t0, crashed, timeout=5.0):
    """FD1 é eventual: espera todo nó vivo suspeitar de `crashed`."""
    alive = set(c.nodes)
    return await wait_until(
        lambda: all(v is not None for v in
                    lc.detection_times(c.events, t0, crashed, alive).values()),
        timeout)


def run(coro):
    return asyncio.run(coro)


# cenário normal
def test_eleicao_inicial_escolhe_maior_id():
    async def scenario():
        c = Cluster(5)
        try:
            await c.start()
            assert await wait_until(lambda: set(c.leaders().values()) == {5})
            alive = set(c.nodes)
            assert lc.agreement(c.events, alive) == 5                    # S1 + S2
            assert lc.false_suspicions(c.events) == 0                    # FD2
        finally:
            await c.stop_all()
    run(scenario())


# cenário de falha
def test_crash_do_lider_dispara_reeleicao():
    async def scenario():
        c = Cluster(5)
        try:
            await c.start()
            assert await wait_until(lambda: set(c.leaders().values()) == {5})
            t0_wall = _t.time()
            await c.crash(5)
            assert await wait_until(lambda: set(c.leaders().values()) == {4})  # L1
            alive = set(c.nodes)
            assert lc.agreement(c.events, alive) == 4                           # S1+S2
            assert await all_detected(c, t0_wall, 5)                            # FD1 (eventual)
            conv = lc.convergence_time(c.events, t0_wall, alive, 4)
            assert conv is not None and conv < 2.0
        finally:
            await c.stop_all()
    run(scenario())


def test_crash_de_nao_lider_nao_muda_lider():
    async def scenario():
        c = Cluster(5)
        try:
            await c.start()
            assert await wait_until(lambda: set(c.leaders().values()) == {5})
            await c.crash(2)
            await asyncio.sleep(1.0)
            assert set(c.leaders().values()) == {5}
            assert await all_detected(c, 0, 2)                                  # FD1 (eventual)
        finally:
            await c.stop_all()
    run(scenario())


def test_reeleicao_nao_espera_election_timeout():
    """
    Com election_timeout ALTO (2 s), a recuperação ainda deve levar ~hb_timeout.
    Sem o encerramento antecipado, um nó que é consultado antes de suspeitar do
    líder esperaria 2 s por um ANSWER que nunca virá.
    """
    async def scenario():
        c = Cluster(5, election_timeout=2.0, coordinator_timeout=4.0)
        try:
            await c.start()
            assert await wait_until(lambda: set(c.leaders().values()) == {5}, 12.0)
            t0 = _t.time()
            await c.crash(5)
            assert await wait_until(lambda: set(c.leaders().values()) == {4}, 12.0)
            conv = lc.convergence_time(c.events, t0, set(c.nodes), 4)
            assert conv is not None and conv < 1.0, conv
        finally:
            await c.stop_all()
    run(scenario())


# recuperação
def test_no_recuperado_de_maior_id_retoma_lideranca():
    async def scenario():
        c = Cluster(4)
        try:
            await c.start()
            assert await wait_until(lambda: set(c.leaders().values()) == {4})
            await c.crash(4)
            assert await wait_until(lambda: set(c.leaders().values()) == {3})
            await c.start_node(4)            # reinício = nova incarnação, sem estado
            assert await wait_until(lambda: set(c.leaders().values()) == {4})
        finally:
            await c.stop_all()
    run(scenario())


# perda de mensagens
def test_converge_com_perda_de_10_por_cento():
    async def scenario():
        c = Cluster(5, loss=0.10, seed=7, hb_timeout_increment=0.1)
        try:
            await c.start()
            assert await wait_until(lambda: set(c.leaders().values()) == {5}, 15.0)
            await c.crash(5)
            assert await wait_until(lambda: set(c.leaders().values()) == {4}, 15.0)
        finally:
            await c.stop_all()
    run(scenario())


# partição
def test_particao_e_cura():
    async def scenario():
        c = Cluster(5)
        try:
            await c.start()
            assert await wait_until(lambda: set(c.leaders().values()) == {5})
            left, right = {1, 2, 3}, {4, 5}
            for i in left:
                c.nodes[i].transport.blocked = set(right)
            for i in right:
                c.nodes[i].transport.blocked = set(left)
            # cada lado elege o seu maior (comportamento esperado do Bully)
            assert await wait_until(
                lambda: {c.nodes[i].leader for i in left} == {3}
                and {c.nodes[i].leader for i in right} == {5})
            # cura: o conflito de líderes é resolvido via heartbeats
            for n in c.nodes.values():
                n.transport.blocked = set()
            assert await wait_until(lambda: set(c.leaders().values()) == {5}, 10.0)
        finally:
            await c.stop_all()
    run(scenario())


# detector isolado (unidade)
def test_detector_suspeita_e_reconfia():
    from bully.detector import HeartbeatDetector
    t = [0.0]
    ev = []
    fd = HeartbeatDetector([1, 2], 1.0, lambda p: ev.append(("S", p)),
                           lambda p: ev.append(("T", p)), increment=0.5,
                           clock=lambda: t[0])
    t[0] = 0.9
    fd.check()
    assert ev == []
    t[0] = 1.2
    fd.check()
    assert ev == [("S", 1), ("S", 2)]
    fd.heartbeat(1)
    assert ev[-1] == ("T", 1) and fd.timeouts[1] == 1.5      # timeout adaptativo
