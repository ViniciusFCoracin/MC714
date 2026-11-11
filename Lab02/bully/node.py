"""
node.py
-------
Nó que executa o algoritmo do Valentão (Bully) apoiado por um detector de
falhas por heartbeat.

Mensagens:
    HB          {leader}  heartbeat periódico; informa quem o remetente crê ser o líder
    ELECTION              "quero ser líder": enviada a todos com id MAIOR
    ANSWER                "estou vivo e sou maior": resposta a um ELECTION
    COORDINATOR           "eu sou o líder": enviada a todos pelo vencedor

Regras (resumo):
  1. Um nó inicia eleição ao subir ou ao suspeitar do líder atual.
  2. Envia ELECTION aos ids maiores (se use_fd_in_election, ignora os suspeitos).
     - ninguém para responder  -> torna-se líder e envia COORDINATOR a todos
     - recebeu ANSWER          -> espera COORDINATOR; se estourar o timeout, repete
  3. Ao receber ELECTION de um id menor: responde ANSWER e inicia a própria eleição.
  4. Ao receber COORDINATOR de um id MAIOR: adota-o como líder.
     Ao receber COORDINATOR de um id MENOR: reafirma-se iniciando eleição.
  5. Resolução de conflito (ex.: após partição curar): se um HB traz um líder
     maior que o meu, e esse líder não é suspeito, inicio eleição.

Eventos registrados (JSON lines) -- base das verificações de correção:
    boot, suspect, trust, election_start, early_abort, elected, leader, stats
"""
from __future__ import annotations

import asyncio
import json
import time

from .detector import HeartbeatDetector
from .transport import Transport

HB, ELECTION, ANSWER, COORDINATOR = "HB", "ELECTION", "ANSWER", "COORDINATOR"


class Node:
    def __init__(self, cfg, on_event=None):
        self.cfg = cfg
        self.id = cfg.node_id
        self.on_event = on_event          # callback opcional (usado nos testes)
        self.leader: int | None = None
        self.others = sorted(p for p in cfg.peers if p != self.id)

        self.transport = Transport(cfg, self._on_message)
        self.fd = HeartbeatDetector(
            self.others, cfg.hb_timeout, self._on_suspect, self._on_trust,
            increment=cfg.hb_timeout_increment,
        )
        self._got_answer = asyncio.Event()
        self._got_coord = asyncio.Event()
        self._wake = asyncio.Event()      # ANSWER chegou ou o detector mudou
        self._election_task: asyncio.Task | None = None
        self._tasks: list[asyncio.Task] = []
        self._fh = None
        self._fd_startup_grace = (
            cfg.fd_startup_grace
            if cfg.fd_startup_grace is not None
            else cfg.startup_delay + cfg.hb_timeout
        )

    # log
    def _log(self, event: str, **fields):
        rec = {"ts": time.time(), "node": self.id, "event": event, **fields}
        line = json.dumps(rec)
        if self._fh:
            self._fh.write(line + "\n")
            self._fh.flush()
        if self.cfg.log_stdout:
            print(line, flush=True)
        if self.on_event:
            self.on_event(rec)

    # ciclo de vida
    async def start(self):
        if self.cfg.log_path:
            self._fh = open(self.cfg.log_path, "a", encoding="utf-8")
        await self.transport.start()
        self._log("boot", peers=sorted(self.cfg.peers))
        self._tasks = [
            asyncio.create_task(self._hb_loop()),
            asyncio.create_task(self._fd_loop()),
            asyncio.create_task(self._stats_loop()),
            asyncio.create_task(self._first_election()),
        ]

    async def stop(self):
        """Crash-stop simulado em processo (nos testes). Não avisa ninguém."""
        for t in self._tasks + ([self._election_task] if self._election_task else []):
            t.cancel()
        await self.transport.stop()
        if self._fh:
            self._fh.close()
            self._fh = None

    async def _first_election(self):
        await asyncio.sleep(self.cfg.startup_delay)
        self._ensure_election()

    # laços periódicos
    async def _hb_loop(self):
        while True:
            for p in self.others:
                await self.transport.send(p, {"type": HB, "leader": self.leader})
            await asyncio.sleep(self.cfg.hb_interval)

    async def _fd_loop(self):
        # Os processos podem subir em ordem diferente. Sem esta janela, o
        # detector pode suspeitar de um nó correto antes do primeiro heartbeat.
        await asyncio.sleep(self._fd_startup_grace)
        while True:
            self.fd.check()
            await asyncio.sleep(self.cfg.hb_interval / 2)

    async def _stats_loop(self):
        while True:
            self._log("stats", sent=dict(self.transport.sent),
                      dropped=self.transport.dropped)
            await asyncio.sleep(0.5)

    # callbacks do detector
    def _on_suspect(self, peer: int):
        self._log("suspect", peer=peer)
        self._wake.set()                  # pode encerrar uma espera por ANSWER
        if peer == self.leader:
            self._set_leader(None)
            self._ensure_election()

    def _on_trust(self, peer: int):
        self._log("trust", peer=peer)

    # mensagens
    async def _on_message(self, msg: dict):
        t, src = msg["type"], msg["src"]
        if t == HB:
            self.fd.heartbeat(src)
            lead = msg.get("leader")
            if (lead is not None and self.leader is not None and lead > self.leader
                    and lead not in self.fd.suspected):
                self._log("leader_conflict", other=lead)
                self._ensure_election()
        elif t == ELECTION:
            await self.transport.send(src, {"type": ANSWER})
            if src < self.id:
                self._ensure_election()
        elif t == ANSWER:
            self._got_answer.set()
            self._wake.set()
        elif t == COORDINATOR:
            if src > self.id:
                self._set_leader(src)
                self._got_coord.set()
            else:
                self._ensure_election()   # um id menor se declarou líder: reafirmar

    # eleição
    def _set_leader(self, leader: int | None):
        if leader != self.leader:
            self.leader = leader
            self._log("leader", leader=leader)

    def _ensure_election(self):
        if self._election_task is None or self._election_task.done():
            self._election_task = asyncio.create_task(self._election())

    async def _election(self):
        self._log("election_start")
        while True:
            self._got_answer.clear()
            self._got_coord.clear()
            higher = [p for p in self.others if p > self.id]
            if self.cfg.use_fd_in_election:
                higher = [p for p in higher if p not in self.fd.suspected]
            if not higher:
                await self._become_leader()
                return
            for p in higher:
                await self.transport.send(p, {"type": ELECTION})
            if not await self._wait_answer(higher):
                await self._become_leader()      # nenhum maior respondeu (ou todos suspeitos)
                return
            try:
                await asyncio.wait_for(self._got_coord.wait(), self.cfg.coordinator_timeout)
                return                           # um maior assumiu a liderança
            except asyncio.TimeoutError:
                self._log("coordinator_timeout")  # o maior sumiu: tenta de novo

    async def _wait_answer(self, higher) -> bool:
        """
        Espera um ANSWER por até election_timeout. Com fd_early_abort, desiste
        antes se o detector passar a suspeitar de TODOS os consultados: sem isso,
        um nó que ainda não detectou a queda (corrida de milissegundos) esperaria
        um timeout inteiro por uma resposta que nunca virá.
        """
        loop = asyncio.get_running_loop()
        end = loop.time() + self.cfg.election_timeout
        while True:
            if self._got_answer.is_set():
                return True
            if self.cfg.fd_early_abort and all(p in self.fd.suspected for p in higher):
                self._log("early_abort")
                return False
            left = end - loop.time()
            if left <= 0:
                return False
            self._wake.clear()
            try:
                await asyncio.wait_for(self._wake.wait(), left)
            except asyncio.TimeoutError:
                pass

    async def _become_leader(self):
        self._set_leader(self.id)
        self._log("elected")
        for p in self.others:
            await self.transport.send(p, {"type": COORDINATOR})
