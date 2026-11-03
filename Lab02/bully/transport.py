"""
transport.py
------------
Camada de comunicação: mensagens JSON (uma por linha) sobre TCP, uma conexão
curta por mensagem, com TIMEOUTS EXPLÍCITOS (nada bloqueia indefinidamente).

Injeção de falhas no nível da aplicação (repetível via SEED):
  * LOSS     -> descarta a mensagem antes de enviar (perda)
  * DELAY_MS -> atraso aleatório antes do envio (jitter; pode reordenar)
  * block    -> partição: ignora envio/recebimento com os ids bloqueados
Crash-stop é feito matando o processo/contêiner (SIGKILL / docker kill).

Modelo de canal resultante: ponto a ponto, não confiável (perdas só quando
injetadas), sem duplicação, sem garantia de ordem quando há DELAY_MS>0.
"""
from __future__ import annotations

import asyncio
import json
import random
from collections import Counter


class Transport:
    def __init__(self, cfg, on_message):
        self.cfg = cfg
        self.on_message = on_message          # async callable(msg: dict)
        self.rng = random.Random(cfg.seed * 1000 + cfg.node_id)
        self.sent = Counter()                 # mensagens "enviadas" por tipo
        self.dropped = 0                      # descartadas por loss/partição
        self.blocked: set[int] = set()
        self._server = None
        self._tasks: set[asyncio.Task] = set()

    # ---------------- recepção ----------------
    async def start(self):
        port = self.cfg.peers[self.cfg.node_id][1]
        self._server = await asyncio.start_server(self._handle, "0.0.0.0", port)

    async def stop(self):
        for t in list(self._tasks):
            t.cancel()
        if self._server:
            self._server.close()
            try:
                await asyncio.wait_for(self._server.wait_closed(), 1.0)
            except asyncio.TimeoutError:
                pass

    async def _handle(self, reader, writer):
        try:
            while True:
                line = await asyncio.wait_for(reader.readline(), 5.0)
                if not line:
                    break
                msg = json.loads(line)
                if msg.get("type") == "CTRL":          # canal de controle de testes
                    self.blocked = set(msg.get("block", []))
                    continue
                if msg.get("src") in self.blocked:
                    self.dropped += 1
                    continue
                await self.on_message(msg)
        except (asyncio.TimeoutError, json.JSONDecodeError, ConnectionError):
            pass
        finally:
            writer.close()

    # ---------------- envio ----------------
    async def send(self, dst: int, msg: dict):
        """Não bloqueia: agenda a entrega (com falhas injetadas) e retorna."""
        msg = {**msg, "src": self.cfg.node_id}
        self.sent[msg["type"]] += 1           # conta a intenção de enviar
        if dst in self.blocked or self.rng.random() < self.cfg.loss:
            self.dropped += 1
            return
        task = asyncio.create_task(self._deliver(dst, msg))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _deliver(self, dst, msg):
        if self.cfg.delay_ms > 0:
            await asyncio.sleep(self.rng.uniform(0, self.cfg.delay_ms) / 1000)
        host, port = self.cfg.peers[dst]
        t = self.cfg.connect_timeout
        try:
            _, writer = await asyncio.wait_for(asyncio.open_connection(host, port), t)
            writer.write(json.dumps(msg).encode() + b"\n")
            await asyncio.wait_for(writer.drain(), t)
            writer.close()
        except (OSError, asyncio.TimeoutError):
            pass  # destino fora do ar: o detector de falhas cuida disso
