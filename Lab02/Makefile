.PHONY: test experiments plots up down crash-leader logs

test:            ## testes automatizados de correção
	python -m pytest -v tests/

experiments:     ## experimento completo (N = 3,5,7,9; 10 repetições) -> results/
	python experiments/run_experiments.py --nodes 3 5 7 9 --reps 10 --out results

plots:           ## gráficos a partir de results/
	python experiments/plot_results.py --in results

up:              ## sobe os 5 nós em contêineres
	docker compose up --build -d

down:            ## derruba e remove tudo
	docker compose down -v

crash-leader:    ## crash-stop do líder atual (nó 5): SIGKILL, sem aviso
	docker kill node5

logs:            ## acompanha os eventos de todos os nós
	docker compose logs -f
