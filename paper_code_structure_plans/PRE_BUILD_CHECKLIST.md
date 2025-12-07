# Pre-Build Checklist

What's left before we can start building Phase 1.

---

## ✅ Resolved (Ready to Build)

- ✅ SandboxManager architecture planned
- ✅ Evaluation architecture planned  
- ✅ Code rule conversion strategy (LLM-based transpilation)
- ✅ Input files as DB records (Resource model updated)
- ✅ E2B API calls documented correctly
- ✅ Event architecture planned
- ✅ All major contradictions resolved

---

## 🚨 Critical Decisions Needed (5 minutes each)

### 1. `total_cost_usd` Field Decision ⚠️
**Decision**: Add field to Run model OR aggregate in queries?

**Options**:
- **Option A**: Add `total_cost_usd: float | None = None` to Run model
  - Pros: Simple queries, fast reads
  - Cons: Need to update on every message/action
- **Option B**: Aggregate in queries: `SELECT SUM(cost_usd) FROM messages WHERE run_id = ?`
  - Pros: No denormalization, always accurate
  - Cons: Slower queries, more complex SQL

**Recommendation**: Option A (add field, update incrementally)

**Action**: Update `01_CORE_ENTITIES.md` Run model

---

## 📋 Phase 1 Prerequisites (Foundation)

### Must Have Before Starting

1. **Environment Variables** (5 min)
   - [ ] Document all required env vars:
     - `DATABASE_URL` - PostgreSQL connection string
     - `OPENAI_API_KEY` - For LLM calls
     - `E2B_API_KEY` - For sandbox creation
     - `INNGEST_EVENT_KEY` - For Inngest events
     - `INNGEST_DEV` - Development mode flag (optional)

2. **Database Connection** (30 min)
   - [ ] Create `h_arcane/db/connection.py` with:
     - `get_engine()` function
     - `init_db()` function (creates tables)
     - Connection pooling setup

3. **SQLModel Models** (1 hour)
   - [ ] Copy models from `01_CORE_ENTITIES.md` to `h_arcane/db/models.py`:
     - Experiment
     - Run (with `total_cost_usd` decision)
     - Message
     - Action
     - Resource (with `experiment_id` field)
     - Evaluation
     - CriterionResult
   - [ ] Add `Resource.load_content()` method
   - [ ] Add `Resource.load_text()` method (if applicable)

4. **Database Queries Module** (2 hours)
   - [ ] Create `h_arcane/db/queries.py` with:
     - `queries.runs.*` (get, create, update, get_by_status)
     - `queries.experiments.*` (get, create)
     - `queries.resources.*` (get_by_experiment, get_by_run, create)
     - `queries.messages.*` (create, get_all)
     - `queries.actions.*` (create, get_all)
     - `queries.criterion_results.*` (create, get_all)
     - `queries.evaluations.*` (create)
   - [ ] Decide: async vs sync? (Recommendation: sync for now, can migrate later)

5. **Project Setup** (30 min)
   - [ ] Create `pyproject.toml` with dependencies:
     - `inngest`
     - `sqlmodel`
     - `openai` (for Agents SDK)
     - `openai-agents` (Agents SDK)
     - `e2b-code-interpreter`
     - `fastapi` (if needed)
     - `pydantic`
     - `pandas` (for tools)
     - Tool dependencies: `pdfplumber`, `python-docx`, `openpyxl`, etc.
   - [ ] Create `docker-compose.yml`:
     - PostgreSQL service
     - Inngest Dev Server (optional, can run locally)

6. **Helper Functions** (1 hour)
   - [ ] `get_mime_type(file_path: Path) -> str`
   - [ ] `create_run(experiment_id: UUID) -> UUID` (FastAPI endpoint or helper)

---

## 🔨 Can Build During Implementation

### Phase 1 (Foundation) - Can implement as needed:

- [ ] GDPEval loader (`h_arcane/experiments/loader.py`)
  - Can reference `04_EXPERIMENT_LAYOUT.md` for structure
  - Will need: `load_gdpeval_tasks()`, `load_to_database()`
  
- [ ] Code rule converter (`scripts/convert_code_rules.py`)
  - Already documented in `06_CODE_RULE_CONVERSION.md`
  - Can implement during data loading phase

### Phase 2 (Agents) - Can implement after Phase 1:

- [ ] SandboxManager (`h_arcane/agents/sandbox.py`)
  - Fully documented in `SANDBOX_ARCHITECTURE.md`
  
- [ ] Tool modules (`h_arcane/tools/*.py`)
  - Extract from manager_agent_gym
  - List documented in `MISSING_DETAILS.md` section 15

- [ ] `execute_in_sandbox()` (`h_arcane/agents/sandbox_executor.py`)
  - Fully documented in `SANDBOX_ARCHITECTURE.md`

- [ ] ReActWorker (`h_arcane/agents/worker.py`)
  - Documented in `01_CORE_ENTITIES.md`
  - Helper methods (`_format_task`, `_wrap_with_logging`) can be implemented inline

- [ ] RubricStakeholder (`h_arcane/agents/stakeholder.py`)
  - Documented in `02_RUBRIC_STAKEHOLDER.md` (if exists)

### Phase 3 (Inngest) - Can implement after Phase 2:

- [ ] All Inngest functions documented in `03_EVENT_ARCHITECTURE.md`
- [ ] Evaluation functions documented in `05_EVALUATION_ARCHITECTURE.md`

---

## ⚙️ Implementation Details (Fill in During Build)

These are documented but can be implemented as you go:

1. **Error Handling**
   - Documented in `MISSING_DETAILS.md` section 11
   - Can add try/except blocks as needed

2. **Token/Cost Tracking**
   - Documented in `MISSING_DETAILS.md` section 6
   - Can implement incrementally (start with basic, add aggregation later)

3. **E2B Template Configuration**
   - Documented in `MISSING_DETAILS.md` section 11
   - Can use default template initially

4. **Path Handling**
   - Documented in `MISSING_DETAILS.md` section 10
   - Can use absolute paths initially

5. **Database Session Management**
   - Documented in `MISSING_DETAILS.md` section 14
   - Can use simple `with Session()` pattern initially

---

## 🎯 Recommended Build Order

### Week 1: Foundation
1. **Day 1**: Project setup + database connection + models
   - `pyproject.toml`, `docker-compose.yml`
   - `h_arcane/db/connection.py`
   - `h_arcane/db/models.py` (all 7 models)
   
2. **Day 2**: Database queries module
   - `h_arcane/db/queries.py` (all query methods)
   - Test with simple inserts/selects

3. **Day 3**: Helper functions + GDPEval loader
   - `get_mime_type()`, `create_run()`
   - `h_arcane/experiments/loader.py`
   - Test loading 1-2 experiments

4. **Day 4**: Code rule converter
   - `scripts/convert_code_rules.py`
   - Test conversion on sample rules

5. **Day 5**: Integration test
   - Load full GDPEval dataset
   - Verify all data in DB correctly

### Week 2: Agents (Phase 2)
- SandboxManager
- Tool modules
- ReActWorker
- WorkerToolkit

### Week 3: Orchestration (Phase 3)
- Inngest functions
- Evaluation functions

---

## 🚀 Ready to Start?

**Minimum to begin Phase 1**:
1. ✅ Decision on `total_cost_usd` (5 min)
2. ✅ Environment variables list (5 min)
3. ✅ Project structure (`pyproject.toml`, `docker-compose.yml`) (30 min)

**Then start building**:
- Database connection + models
- Queries module
- Helper functions
- GDPEval loader

**Everything else can be implemented incrementally!**

---

## 📝 Quick Reference

**Key Files to Create First**:
```
h_arcane/
├── __init__.py
├── db/
│   ├── __init__.py
│   ├── connection.py      # Database connection
│   ├── models.py          # All SQLModel models
│   └── queries.py         # Query methods
├── experiments/
│   ├── __init__.py
│   └── loader.py          # GDPEval loader
└── agents/
    └── __init__.py

scripts/
└── convert_code_rules.py  # Code rule converter

pyproject.toml             # Dependencies
docker-compose.yml         # Postgres + Inngest
.env.example               # Environment variables template
```

**Key Decisions Made**:
- ✅ Code rules: Convert via LLM transpilation (one-off script)
- ✅ Input files: Store as Resource records (not JSON)
- ✅ Evaluation: Functional approach (not bound methods)
- ⚠️ `total_cost_usd`: Pending decision (add field vs aggregate)

---

**Status**: Ready to build Phase 1 after resolving `total_cost_usd` decision! 🎉

