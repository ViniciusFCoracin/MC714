"""
main.py -- ponto de entrada de um nó (um por processo/contêiner).

    NODE_ID=3 PEERS="1=127.0.0.1:7001,2=127.0.0.1:7002,3=127.0.0.1:7003" \
        python -m bully.main
"""
import asyncio
import signal

from .config import Config
from .node import Node


async def amain():
    node = Node(Config.from_env())
    await node.start()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:      # Windows
            pass
    await stop.wait()
    await node.stop()


if __name__ == "__main__":
    try:
        asyncio.run(amain())
    except KeyboardInterrupt:
        pass
