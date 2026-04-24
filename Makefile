.PHONY: cost_agent install clean

sites ?= 5

install:
	pip install -r requirements.txt

cost_agent:
	@echo "══════════════════════════════════════════"
	@echo "  GridScout — cost agent ($(sites) sites)"
	@echo "══════════════════════════════════════════"
	python3 pipeline.py --max $(sites)

clean:
	rm -rf mini_caches_10/*.json mini_caches_100/*.json site_cache.json area_cache.json
