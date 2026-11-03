"""
ctl.py -- envia comandos de controle a um nó em execução (cenários de partição).

    python -m bully.ctl 127.0.0.1 7001 --block 4 5   # nó passa a ignorar 4 e 5
    python -m bully.ctl 127.0.0.1 7001               # remove os bloqueios (cura)
"""
import argparse
import json
import socket

p = argparse.ArgumentParser()
p.add_argument("host")
p.add_argument("port", type=int)
p.add_argument("--block", type=int, nargs="*", default=[])
a = p.parse_args()
with socket.create_connection((a.host, a.port), timeout=2) as s:
    s.sendall(json.dumps({"type": "CTRL", "block": a.block}).encode() + b"\n")
