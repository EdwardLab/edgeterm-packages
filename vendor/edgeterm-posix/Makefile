.PHONY: test test-host test-wasix audit

test: test-host test-wasix

test-host:
	./tests/run-host-tests.sh

test-wasix:
	./tests/run-wasix-tests.sh

audit:
	python3 ./scripts/audit-ports.py ../EdgeTerm-Packages/ports
