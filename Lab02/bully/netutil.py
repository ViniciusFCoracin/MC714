"""
netutil.py -- reserva de portas TCP para os nós de um experimento.

Por que não usar bind(porta 0)? O SO escolhe portas "efêmeras" (Windows:
49152-65535), as MESMAS que conexões de saída usam; entre fechar o socket de
teste e o nó fazer o bind, outro processo pode ocupar a porta (WinError 10048).
Aqui usamos uma faixa baixa (20000-29999), avançando sempre para frente, de
modo que duas rodadas consecutivas nunca reaproveitam portas recentes.
"""
import random
import socket

_LOW, _HIGH = 20000, 29999
_next = random.randrange(_LOW, _LOW + 5000)


def reserve_ports(n: int) -> list[int]:
    """Devolve n portas livres (verificadas por bind) em faixa não efêmera."""
    global _next
    ports: list[int] = []
    while len(ports) < n:
        p = _next
        _next = _LOW if _next >= _HIGH else _next + 1
        s = socket.socket()
        try:
            s.bind(("0.0.0.0", p))
            ports.append(p)
        except OSError:
            pass                     # porta em uso/reservada: tenta a próxima
        finally:
            s.close()
    return ports
