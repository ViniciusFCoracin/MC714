"""
transport.py
------------
Camada de comunicação: mensagens JSON (uma por linha) sobre TCP, com UMA
CONEXÃO PERSISTENTE por destino (reconectada quando cai) e TIMEOUTS EXPLÍCITOS
(nada bloqueia indefinidamente).

Por que persistente? Uma conexão por mensagem gera milhares de sockets em
TIME_WAIT por minuto; no Windows isso esgota as portas efêmeras e causa
WinError 10048 / mensagens perdidas. Com conexões persistentes o nº de sockets
é constante (N-1 por nó).

Injeção de falhas no nível da aplicação (repetível via SEED):
  * LOSS     -> descarta a mensagem antes de enviar (perda)
  * DELAY_MS -> atraso aleatório antes do envio (jitter; pode reordenar)
  * block    -> partição: ignora envio/recebimento com os ids bloqueados
Crash-stop é feito matando o processo/contêiner (SIGKILL / docker kill).

Modelo de canal resultante: ponto a ponto, FIFO por conexão (a menos de DELAY_MS),
sem duplicação; perdas só quando injetadas ou ao reconectar com o destino fora do ar.
"""
from __future__ import annotations

import asyncio
import json
import random
from collections import Counter


class _Out:
    """Estado da conexão de saída para um destino."""
    def __init__(self):
        self.writer = None
        self.lock = asyncio.Lock()      # serializa escritas/reconexões (FIFO)
        self.retry_at = 0.0             # backoff após falha de conexão


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
        self._out = {p: _Out() for p in cfg.peers if p != cfg.node_id}
        self._conns: set = set()              # conexões de entrada abertas

    # Recepção
    async def start(self):
        port = self.cfg.peers[self.cfg.node_id][1]
        self._server = await asyncio.start_server(self._handle, "0.0.0.0", port)

    async def stop(self):
        for t in list(self._tasks):
            t.cancel()
        for o in self._out.values():
            if o.writer:
                o.writer.close()
        for w in list(self._conns):           # como num crash: derruba as conexões
            w.close()
        if self._server:
            self._server.close()
            try:
                await asyncio.wait_for(self._server.wait_closed(), 1.0)
            except asyncio.TimeoutError:
                pass

    async def _handle(self, reader, writer):
        self._conns.add(writer)
        try:
            while True:
                line = await asyncio.wait_for(reader.readline(), 30.0)
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
        except (asyncio.TimeoutError, json.JSONDecodeError, OSError):
            pass
        finally:
            self._conns.discard(writer)
            writer.close()

    # Envio
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
        out = self._out[dst]
        t = self.cfg.connect_timeout
        data = json.dumps(msg).encode() + b"\n"
        loop = asyncio.get_running_loop()
        async with out.lock:
            if out.writer is None or out.writer.is_closing():
                if loop.time() < out.retry_at:
                    return                    # destino caiu há pouco: não insiste
                host, port = self.cfg.peers[dst]
                try:
                    _, out.writer = await asyncio.wait_for(
                        asyncio.open_connection(host, port), t)
                except (OSError, asyncio.TimeoutError):
                    out.writer = None
                    out.retry_at = loop.time() + self.cfg.hb_interval
                    return                    # o detector de falhas cuida disso
            try:
                out.writer.write(data)
                await asyncio.wait_for(out.writer.drain(), t)
            except (OSError, asyncio.TimeoutError):
                out.writer.close()
                out.writer = None
