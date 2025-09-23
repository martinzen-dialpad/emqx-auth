start:
	@echo "Starting MQTT service stack"
	@docker compose up -d

kill:
	@echo "Destroying MQTT service stack"
	@docker compose down

.PHONY: test
test:
	@echo "Running integration tests..."
	@uv run pytest
