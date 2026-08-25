PYTHON ?= python

.PHONY: install verify demo rtl-smoke release-check

install:
	$(PYTHON) -m pip install -e .

verify:
	PYTHONPATH=. $(PYTHON) -m unittest -v \
		tests.test_sparse_scheduler \
		tests.test_proof_controls_v02 \
		tests.test_dag_parent_commit \
		tests.test_cosmic_kernel \
		tests.test_verified_incident_map

demo:
	PYTHONPATH=. $(PYTHON) -m demos.verified_incident_map --compact

rtl-smoke:
	PYTHONPATH=. $(PYTHON) benchmarks/run_cosmic_hw_12_hmac_kat.py

release-check:
	$(PYTHON) -m compileall -q morphos demos
	$(MAKE) verify PYTHON=$(PYTHON)
	$(MAKE) demo PYTHON=$(PYTHON)
