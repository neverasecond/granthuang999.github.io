.PHONY: sync social-latest social-issue social-help

PYTHON ?= python3
SOCIAL_SCRIPT := operations/generate_social_pack.py

sync:
	git pull --ff-only origin main

social-latest:
	$(PYTHON) $(SOCIAL_SCRIPT) --latest

social-issue:
ifndef ISSUE
	$(error Usage: make social-issue ISSUE=284)
endif
	$(PYTHON) $(SOCIAL_SCRIPT) --issue $(ISSUE)

social-help:
	@echo "make sync"
	@echo "make social-latest"
	@echo "make social-issue ISSUE=284"
