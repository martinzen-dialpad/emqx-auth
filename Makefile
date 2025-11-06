start:
	@echo "Starting MQTT service stack"
	@docker compose up -d

stop:
	@echo "Destroying MQTT service stack"
	@docker compose down

.PHONY: test
test:
	@echo "Running integration tests..."
	@uv run pytest

.PHONY: loadtest
loadtest:
	@echo "Running Locust load tests..."
	@echo "Web UI available at http://localhost:8089"
	@uv run locust -f test/load_test.py --config test/locust.conf

.PHONY: loadtest-headless
loadtest-headless:
	@echo "Running Locust load tests in headless mode..."
	@uv run locust -f test/load_test.py --config test/locust.conf --headless
