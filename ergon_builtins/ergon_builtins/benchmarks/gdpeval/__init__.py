"""GDPEval benchmark — document-processing evaluation with staged rubrics.

Namespace package only.  Concrete classes live in submodules and must
be imported via explicit submodule paths:

    from ergon_builtins.benchmarks.gdpeval.benchmark        import GDPEvalBenchmark
    from ergon_builtins.benchmarks.gdpeval.rubric           import StagedRubric
    from ergon_builtins.benchmarks.gdpeval.sandbox          import GDPEvalSandbox

This package previously eagerly imported the benchmark class in
``__init__.py``, which transitively loaded ``pandas`` via
``gdpeval/loader.py``. Keeping this file empty of eager imports lets
``StagedRubric`` and ``GDPEvalSandbox`` be imported standalone without
pulling in the benchmark's data-only dependencies.
"""
