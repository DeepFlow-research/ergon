# Migration Blockers: Problems to Address Before Restructuring

This document identifies tightly coupled code, union types, global state, and other issues that will complicate the Benchmark-First Architecture migration.

---

## 🔴 Critical Blockers

### 1. `AnyRule` Union Type in Core Evaluation

**Location:** `h_arcane/evaluation/rules/__init__.py`

```python
AnyRule = Annotated[
    Union[CodeRule, LLMJudgeRule, ProofVerificationRule],
    Field(discriminator="type"),
]
```

**Problem:** 
- `ProofVerificationRule` is MiniF2F-specific but included in `AnyRule` which is exported from `evaluation/`
- This means `core/evaluation/` will import from `benchmarks/minif2f/` — **violates one-way dependency rule**

**Impact:** Cannot cleanly separate core from benchmarks

**Solution Options:**
1. **Option A: Core only has generic rules, benchmarks define their own union**
   ```python
   # core/evaluation/rules/__init__.py
   CoreRule = Annotated[Union[CodeRule, LLMJudgeRule], Field(discriminator="type")]
   
   # benchmarks/minif2f/rules/__init__.py
   MiniF2FRule = Annotated[
       Union[CodeRule, LLMJudgeRule, ProofVerificationRule],
       Field(discriminator="type")
   ]
   ```

2. **Option B: Runtime rule registration (plugin pattern)**
   ```python
   # core/evaluation/rules/registry.py
   RULE_TYPES: dict[str, type[BaseRule]] = {}
   
   def register_rule(rule_type: str, rule_class: type[BaseRule]):
       RULE_TYPES[rule_type] = rule_class
   ```

**Recommendation:** Option A — simpler, type-safe, matches benchmark-first philosophy

---

### 2. `EvaluationStage.rules` Hardcoded to `CodeRule | LLMJudgeRule`

**Location:** `h_arcane/evaluation/schemas.py:65`

```python
class EvaluationStage(BaseModel):
    rules: list[CodeRule | LLMJudgeRule] = Field(...)  # MiniF2F can't use this!
```

**Problem:**
- `EvaluationStage` is in core (`evaluation/schemas.py`)
- But it hardcodes which rule types are allowed
- MiniF2F needs `ProofVerificationRule` in its stages
- Adding it here means core imports benchmark code

**Impact:** MiniF2F cannot use the standard `EvaluationStage` model

**Solution Options:**
1. **Option A: Generic EvaluationStage with `list[BaseRule]`**
   ```python
   class EvaluationStage(BaseModel):
       rules: list[BaseRule] = Field(...)  # Generic - any rule
   ```
   *Problem: Loses discriminated union type safety for serialization*

2. **Option B: EvaluationStage is generic, benchmark-specific subclasses**
   ```python
   # core/evaluation/rubric.py
   T = TypeVar("T", bound=BaseRule)
   class EvaluationStage(BaseModel, Generic[T]):
       rules: list[T] = Field(...)
   
   # benchmarks/gdpeval/rubric.py
   GDPEvalStage = EvaluationStage[CodeRule | LLMJudgeRule]
   
   # benchmarks/minif2f/rubric.py  
   MiniF2FStage = EvaluationStage[CodeRule | LLMJudgeRule | ProofVerificationRule]
   ```

3. **Option C: Each benchmark defines its own rubric structure**
   - GDPEval uses `StagedRubric`
   - MiniF2F uses `MiniF2FRubric` (simpler, proof-focused)

**Recommendation:** Option C — MiniF2F probably doesn't need the same rubric complexity

---

### 3. `StagedRubric` / `GDPEvalStagedRubric` Coupling

**Locations:**
- `h_arcane/evaluation/schemas.py` — defines `StagedRubric`, `GDPEvalStagedRubric`
- `h_arcane/benchmarks/gdpeval/schemas.py` — imports `StagedRubric`
- `h_arcane/benchmarks/gdpeval/stakeholder.py` — uses `StagedRubric`
- `h_arcane/inngest/functions/worker_execute.py` — creates `StagedRubric`

**Problem:**
- `StagedRubric` is deeply GDPEval-specific (stages, gates, min_score_to_pass)
- But it lives in "core" `evaluation/schemas.py`
- MiniF2F doesn't need this complexity — it's just "did the proof verify?"

**Impact:** Benchmark-specific concepts leak into core

**Solution:**
- Move `StagedRubric`, `EvaluationStage`, `GDPEvalStagedRubric` to `benchmarks/gdpeval/`
- Core only has abstract `BaseRubric` interface (if needed at all)
- MiniF2F can have simpler `MiniF2FRubric` or just use `ProofVerificationRule` directly

---

### 4. Global State in `sandbox_executor.py`

**Location:** `h_arcane/agents/sandbox_executor.py`

```python
_current_run_id: UUID | None = None

def set_sandbox_manager(sandbox_manager: SandboxManager, run_id: UUID) -> None:
    global _current_run_id
    _current_run_id = run_id
```

**Problem:**
- Global mutable state for `run_id`
- Required because `@function_tool` decorated functions can't easily receive context
- Toolkits call `set_sandbox_manager()` before returning tools
- Breaks if multiple runs execute concurrently

**Impact:** 
- Can't run multiple experiments in parallel in same process
- Makes testing difficult
- Hidden coupling between toolkit and tools

**Solution:**
- New architecture: Skills are called via `sandbox_manager.run_skill()` which takes `run_id`
- No global state needed — toolkit wrappers close over `run_id`
- See `10_BENCHMARK_FIRST_ARCHITECTURE.md` toolkit pattern

---

### 5. `SandboxManager` Singleton Pattern

**Location:** `h_arcane/agents/sandbox.py`

```python
class SandboxManager:
    _instance: "SandboxManager | None" = None
    _sandboxes: dict[UUID, AsyncSandbox] = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
```

**Problem:**
- Singleton with class-level state
- `_sandboxes` dict is shared across all instances (but there's only one)
- Creates issues: `get_sandbox_manager()` returns `SandboxManager()` (new instance that's actually the singleton)

**Impact:** Confusing semantics, hard to test, hidden shared state

**Solution:**
- Pass `SandboxManager` explicitly where needed
- Or keep singleton but make it explicit (not hidden in `__new__`)

---

## 🟡 Medium Blockers

### 6. Tool Functions in `h_arcane/agents/tools.py` Mix All Benchmarks

**Location:** `h_arcane/agents/tools.py`

```python
# GDPEval tools
@function_tool
async def read_pdf(file_path: str) -> str: ...

@function_tool
async def create_docx(...) -> str: ...

# MiniF2F tools (in same file!)
@function_tool
async def write_lean_file(filename: str, content: str) -> str: ...

@function_tool
async def check_lean_file(filename: str) -> str: ...
```

**Problem:**
- All tools from all benchmarks in one file
- GDPEval toolkit imports Lean tools even though it doesn't use them
- Toolkits just select which subset to return

**Impact:** No isolation between benchmarks at tool level

**Solution:**
- Each benchmark's toolkit creates its own tool wrappers
- Tool functions live in benchmark's `skills/` folder
- No shared `tools.py` file

---

### 7. Hardcoded `formal_math_tool_map` in `sandbox_executor.py`

**Location:** `h_arcane/agents/sandbox_executor.py:83-87`

```python
formal_math_tool_map = {
    "write_lean_file": ("formal_math.lean_write", "write_lean_file"),
    "check_lean_file": ("formal_math.lean_check", "check_lean_file"),
    "verify_lean_proof": ("formal_math.lean_verify", "verify_lean_proof"),
}
```

**Problem:**
- Core code has hardcoded knowledge of MiniF2F-specific tools
- Adding a new benchmark means editing this map in core

**Impact:** Core knows about benchmark-specific implementation details

**Solution:**
- New skills architecture: benchmark specifies its skills folder
- `run_skill()` just imports from `{benchmark}.{skill_name}`
- No hardcoded mapping needed

---

### 8. `upload_tools_to_sandbox()` Uploads ALL Tools

**Location:** `h_arcane/agents/sandbox_executor.py:171-259`

```python
async def upload_tools_to_sandbox(sandbox_manager: SandboxManager, run_id: UUID) -> None:
    tools_dir = Path(__file__).parent.parent / "tools"
    # ... uploads everything including formal_math/
```

**Problem:**
- Uploads ALL tools to EVERY sandbox
- GDPEval sandbox gets Lean tools it doesn't need
- MiniF2F sandbox gets PDF tools it doesn't need

**Impact:** Wasted upload time, potential confusion, bloated sandboxes

**Solution:**
- `SandboxManager.create(run_id, skills_dir)` only copies benchmark's skills
- See `10_BENCHMARK_FIRST_ARCHITECTURE.md`

---

### 9. `responses.py` Inheritance Chain

**Locations:**
- `h_arcane/tools/responses.py` — base `ToolResponse`
- `h_arcane/tools/formal_math/responses.py` — imports base, defines Lean responses

```python
# formal_math/responses.py
if "/tools" in sys.path:
    from responses import ToolResponse
else:
    from h_arcane.tools.responses import ToolResponse
```

**Problem:**
- Hacky import switching for VM vs local
- Tight coupling between tools and formal_math

**Impact:** Fragile, confusing, will break if paths change

**Solution:**
- Each benchmark has its own `responses.py`
- Core `_core/base.py` is copied to every VM
- Relative imports: `from _core.base import ToolResponse`

---

## 🟢 Minor Issues (Fix During Migration)

### 10. Duplicate `RubricStakeholder` Definitions

**Locations:**
- `h_arcane/agents/stakeholder.py` — `RubricStakeholder` (older)
- `h_arcane/benchmarks/gdpeval/stakeholder.py` — `RubricStakeholder` (newer, extends `BaseStakeholder`)

**Problem:** Two versions of same class

**Solution:** Delete `h_arcane/agents/stakeholder.py`, keep only benchmark version

---

### 11. `FlattenedCriterion` Hardcoded Rule Types

**Location:** `h_arcane/evaluation/schemas.py:142-148`

```python
class FlattenedCriterion(BaseModel):
    stage: EvaluationStage
    rule: CodeRule | LLMJudgeRule  # No ProofVerificationRule!
    stage_idx: int
    rule_idx: int
```

**Problem:** Same as #2 — hardcoded rule types

**Solution:** Move to benchmark-specific schemas or make generic

---

### 12. `inngest/events.py` References Specific Rule Types

**Location:** `h_arcane/inngest/events.py:7`

```python
from h_arcane.evaluation.rules import CodeRule, LLMJudgeRule
```

**Problem:** Event schemas import specific rule types

**Solution:** Events should be generic or benchmark events should be separate

---

## Summary: Blocking Dependencies

```
Current Dependency Graph (BAD):

evaluation/rules/__init__.py ──imports──> benchmarks/minif2f/rules/proof_verification.py
         │
         └── AnyRule includes ProofVerificationRule

evaluation/schemas.py ──hardcodes──> CodeRule | LLMJudgeRule (excludes MiniF2F)

agents/sandbox_executor.py ──hardcodes──> formal_math tool paths

agents/tools.py ──contains──> ALL benchmark tools (GDPEval + MiniF2F)
```

```
Target Dependency Graph (GOOD):

                    ┌──────────────────────────────────────────┐
                    │                CORE                       │
                    │  evaluation/rules/ (BaseRule, CodeRule)   │
                    │  agents/ (worker, protocols)              │
                    │  infrastructure/ (sandbox, db)            │
                    └───────────────────┬──────────────────────┘
                                        │ depends on (one-way)
                    ┌───────────────────┴──────────────────────┐
                    │                                          │
          ┌─────────▼─────────┐               ┌───────────────▼────────────┐
          │  benchmarks/gdpeval │               │  benchmarks/minif2f       │
          │  - skills/         │               │  - skills/                │
          │  - rules/          │               │  - rules/proof_verification│
          │  - toolkit         │               │  - toolkit                 │
          │  - stakeholder     │               │  - stakeholder             │
          └────────────────────┘               └────────────────────────────┘
                    │                                         │
                    └─────────── NO CROSS-IMPORTS ────────────┘
```

---

## Pre-Migration Checklist

Before starting the restructure:

1. [ ] **Decide on rubric strategy**: Is `StagedRubric` GDPEval-only? Does MiniF2F need stages?
2. [ ] **Decide on AnyRule**: Remove from core, each benchmark defines own union?
3. [ ] **Audit all `from h_arcane.evaluation` imports** — which are truly generic?
4. [ ] **Remove global state**: Plan for `_current_run_id` elimination
5. [ ] **Delete duplicate stakeholder**: `h_arcane/agents/stakeholder.py`
6. [ ] **Map all tool usage**: Which tools are actually called by which benchmark?

