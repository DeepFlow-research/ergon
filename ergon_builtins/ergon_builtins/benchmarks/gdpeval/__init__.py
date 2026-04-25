"""GDPEval benchmark — document-processing evaluation with staged rubrics.

Namespace package only.  Concrete classes live in submodules and must
be imported via explicit submodule paths:

    from ergon_builtins.benchmarks.gdpeval.benchmark import GDPEvalBenchmark
    from ergon_builtins.benchmarks.gdpeval.rubric   import StagedRubric
    from ergon_builtins.benchmarks.gdpeval.sandbox  import GDPEvalSandboxManager

This package previously eagerly imported the benchmark class in
``__init__.py``, which transitively loaded ``pandas`` via
``gdpeval/loader.py``.  That made ``registry_core.py``'s module-level
import of ``.rubric.StagedRubric`` crash in any container that doesn't
install the ``ergon-builtins[data]`` extra (i.e. the production api
image).  Keeping this file empty of eager imports lets ``StagedRubric``
and ``GDPEvalSandboxManager`` be imported standalone without pulling
in the benchmark's data-only dependencies.
"""
