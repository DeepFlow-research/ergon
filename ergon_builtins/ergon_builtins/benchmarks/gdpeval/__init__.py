"""GDPEval domain package: document-processing evaluation with staged rubrics.

Namespace package only.  Concrete classes live in submodules and must
be imported via explicit submodule paths:

    from ergon_builtins.benchmarks.gdpeval.task        import GDPEvalTask
    from ergon_builtins.benchmarks.gdpeval.rubric           import StagedRubric
    from ergon_builtins.benchmarks.gdpeval.sandbox          import GDPEvalSandbox

Keeping this file empty of eager imports lets
``StagedRubric`` and ``GDPEvalSandbox`` be imported standalone without
pulling in data-only dependencies.
"""
