"""Tests for the experiments lifecycle façade.

``define_benchmark_experiment`` was deleted in PR 6.5 Phase 2 — tests that
exercised it have been removed.  ``ExperimentService`` was collapsed to
module-level ``persist_benchmark`` (``definition_writer``) and
``run_experiment`` (``service``); coverage lives in
``test_walkthrough_smoketest.py`` and ``test_experiment_launch_service.py``.
"""
