import random
import simpy


class Metrics:
    """
    Acumula os dados brutos de uma réplica de simulação para depois
    calcular as métricas agregadas (apenas com base no intervalo
    [warmup, sim_time]).
    """

    def __init__(self, n_servers, warmup, sim_time):
        self.n_servers = n_servers
        self.warmup = warmup
        self.sim_time = sim_time

        # Tempos de resposta (fila + serviço) de cada requisição que
        # chegou depois do warm-up (assim garantimos réplicas independentes
        # do período transiente, conforme sugerido no enunciado).
        self.response_times = []

        # Lista de eventos (tempo, delta) para reconstruir N(t) = nº de
        # requisições no sistema (soma dos 3 servidores) ao longo do tempo.
        # delta = +1 em chegada, -1 em partida.
        self.n_events = []

        # Contadores de requisições enviadas para cada servidor (para
        # os logs / dinâmica de distribuição de carga pedidos no enunciado).
        self.jobs_per_server = [0] * n_servers

        # Intervalos de ocupação de cada servidor: lista de (start, end)
        self.busy_intervals = [[] for _ in range(n_servers)]

        # Nº de requisições concluídas dentro do período útil (pós warm-up)
        self.completions_useful = 0

    # registro de eventos
    def register_arrival(self, t):
        self.n_events.append((t, +1))

    def register_departure(self, t):
        self.n_events.append((t, -1))

    def register_response(self, arrival_time, departure_time):
        if arrival_time >= self.warmup:
            self.response_times.append(departure_time - arrival_time)
            self.completions_useful += 1

    def register_busy_interval(self, server_id, start, end):
        self.busy_intervals[server_id].append((start, end))

    # cálculo das métricas agregadas
    def useful_time(self):
        return self.sim_time - self.warmup

    def throughput(self):
        return self.completions_useful / self.useful_time()

    def mean_response_time(self):
        if not self.response_times:
            return 0.0
        return sum(self.response_times) / len(self.response_times)

    def mean_number_in_system(self):
        """
        E[N] = integral de N(t) dt / duração,  para t em [warmup, sim_time].
        Reconstrói N(t) varrendo os eventos ordenados no tempo.
        """
        events = sorted(self.n_events, key=lambda e: e[0])

        n_atual = 0
        t_prev = 0.0
        area = 0.0

        for t, delta in events:
            # calcula a interseção do intervalo [t_prev, t) com [warmup, sim_time]
            t0 = max(t_prev, self.warmup)
            t1 = min(t, self.sim_time)
            if t1 > t0:
                area += n_atual * (t1 - t0)
            n_atual += delta
            t_prev = t

        # trecho final até sim_time, se necessário
        t0 = max(t_prev, self.warmup)
        t1 = self.sim_time
        if t1 > t0:
            area += n_atual * (t1 - t0)

        return area / self.useful_time()

    def utilization(self, server_id):
        """Fração do tempo útil em que o servidor estava ocupado."""
        busy = 0.0
        for start, end in self.busy_intervals[server_id]:
            # Se a simulação terminou com o servidor ainda ocupado, o
            # intervalo fica "censurado": consideramos ocupado até sim_time.
            if end is None:
                end = self.sim_time
            t0 = max(start, self.warmup)
            t1 = min(end, self.sim_time)
            if t1 > t0:
                busy += (t1 - t0)
        return busy / self.useful_time()


class Server:
    """
    Um servidor homogêneo: fila FCFS ilimitada + 1 thread de execução.
    Implementado com simpy.Resource(capacity=1); a fila é implícita
    (requisições aguardam no resource.queue).
    """

    def __init__(self, env, server_id, mu, metrics, rng):
        self.env = env
        self.id = server_id
        self.mu = mu
        self.resource = simpy.Resource(env, capacity=1)
        self.metrics = metrics
        self.rng = rng

    def queue_length(self):
        """Nº de requisições na fila + em execução (para a política Fila Mais Curta)."""
        return len(self.resource.queue) + self.resource.count

    def handle(self, job_id, arrival_time):
        """Processo SimPy: espera pelo servidor, executa e libera."""
        with self.resource.request() as req:
            yield req
            start = self.env.now
            self.metrics.register_busy_interval(self.id, start, None)  # placeholder
            service_time = self.rng.expovariate(self.mu)
            yield self.env.timeout(service_time)
            end = self.env.now

            # corrige o placeholder do intervalo de ocupação
            self.metrics.busy_intervals[self.id][-1] = (start, end)

        departure_time = self.env.now
        self.metrics.register_departure(departure_time)
        self.metrics.register_response(arrival_time, departure_time)


class Dispatcher:
    """
    Balanceador de carga (instantâneo, sem tempo de processamento próprio).
    Escolhe o servidor de acordo com a política configurada.
    """

    def __init__(self, servers, policy, rng):
        self.servers = servers
        self.policy = policy
        self.rng = rng
        self._rr_next = 0  # índice para round robin

    def choose_server(self):
        if self.policy == "random":
            return self.rng.choice(self.servers)

        elif self.policy == "round_robin":
            server = self.servers[self._rr_next]
            self._rr_next = (self._rr_next + 1) % len(self.servers)
            return server

        elif self.policy == "shortest_queue":
            lengths = [s.queue_length() for s in self.servers]
            min_len = min(lengths)
            candidates = [s for s, l in zip(self.servers, lengths) if l == min_len]
            # empates resolvidos aleatoriamente
            return self.rng.choice(candidates)

        else:
            raise ValueError(f"Política desconhecida: {self.policy}")


def arrival_process(env, dispatcher, lam, metrics, rng, sim_time):
    """Processo de chegadas de Poisson(lambda): interchegadas exponenciais."""
    job_id = 0
    while True:
        interarrival = rng.expovariate(lam)
        yield env.timeout(interarrival)
        if env.now > sim_time:
            break

        job_id += 1
        arrival_time = env.now
        metrics.register_arrival(arrival_time)

        server = dispatcher.choose_server()
        metrics.jobs_per_server[server.id] += 1

        env.process(server.handle(job_id, arrival_time))


def run_single_replication(policy, lam, mu=1.0, n_servers=3,
                            sim_time=5000.0, warmup=500.0, seed=None,
                            verbose=False):
    """
    Executa UMA réplica da simulação e retorna um dicionário com as métricas.

    Parâmetros:
        policy   : "random" | "round_robin" | "shortest_queue"
        lam      : taxa de chegada (lambda)
        mu       : taxa de serviço de cada servidor (default 1.0)
        n_servers: número de servidores (default 3)
        sim_time : duração total da simulação
        warmup   : tempo de aquecimento descartado das estatísticas
        seed     : semente do gerador de números aleatórios (reprodutibilidade)
    """
    rng = random.Random(seed)

    env = simpy.Environment()
    metrics = Metrics(n_servers, warmup, sim_time)

    servers = [Server(env, i, mu, metrics, rng) for i in range(n_servers)]
    dispatcher = Dispatcher(servers, policy, rng)

    env.process(arrival_process(env, dispatcher, lam, metrics, rng, sim_time))
    env.run(until=sim_time)

    result = {
        "policy": policy,
        "lambda": lam,
        "seed": seed,
        "X": metrics.throughput(),
        "E[R]": metrics.mean_response_time(),
        "E[N]": metrics.mean_number_in_system(),
    }
    for i in range(n_servers):
        result[f"U{i+1}"] = metrics.utilization(i)

    if verbose:
        print(f"[policy={policy}, lambda={lam}, seed={seed}] "
              f"jobs/server={metrics.jobs_per_server}  "
              f"X={result['X']:.4f}  E[R]={result['E[R]']:.4f}  E[N]={result['E[N]']:.4f}")

    return result


if __name__ == "__main__":
    # cheque de sanidade: com lambda pequeno,
    # E[R] deve tender a E[S] = 1/mu = 1.0
    r = run_single_replication(policy="random", lam=0.1, sim_time=2000,
                                warmup=200, seed=42, verbose=True)
    print(r)
