.PHONY: help install dev lint test test-cov sample run demo verify monthly dashboard clean

PYTHON  := python3
PIP     := pip
PYTEST  := pytest
GBE     := gbe

help:
	@echo "gulf-buoy-etl — make targets"
	@echo ""
	@echo "  install     pip install (production)"
	@echo "  dev         pip install -e '.[dev]'"
	@echo "  lint        ruff check"
	@echo "  test        pytest"
	@echo "  test-cov    pytest with coverage report"
	@echo "  sample      regenerate offline sample fixtures"
	@echo "  demo        run pipeline end-to-end on sample fixtures (no network)"
	@echo "  run         run pipeline against live NDBC + TABS"
	@echo "  verify      sha256sum -c every archive sidecar"
	@echo "  monthly     dry-run build the monthly submission package"
	@echo "  dashboard   generate dashboard/status.json + index.html"
	@echo "  clean       remove build artefacts and caches"

install:
	$(PIP) install .

dev:
	$(PIP) install -e ".[dev]"

lint:
	ruff check gbe/ tests/

test:
	$(PYTEST) tests/

test-cov:
	$(PYTEST) --cov=gbe --cov-report=term-missing --cov-report=html tests/

sample:
	$(PYTHON) scripts/generate_sample.py

demo: sample
	$(PYTHON) -m scripts.demo_from_sample

run:
	$(GBE) run --archive-root archive

verify:
	bash bin/verify_archive.sh archive/daily

monthly:
	$(GBE) publish "$$(date -u +%Y-%m)" --dry-run

dashboard:
	$(PYTHON) dashboard/generate.py

clean:
	rm -rf build/ dist/ *.egg-info/ .pytest_cache/ htmlcov/ .coverage coverage.xml
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
