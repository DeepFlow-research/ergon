# H-ARCANE: Hypothesis-Based Modeling for Uncertainty-Aware Alignment

Proof-of-concept implementation of the H-ARCANE framework for studying decision-making under uncertainty in agent-stakeholder interactions.

## Overview

This PoC focuses on the **ReAct baseline** - measuring natural LLM clarification behavior before adding Value of Information (VoI) complexity.

**Research Questions**:
- When does an LLM-based worker spontaneously ask questions?
- Does asking improve task performance?
- What's the relationship between questions asked and final score?

## Architecture

- **Single Worker Agent**: ReAct-style worker with `ask_stakeholder` tool + GDPEval tools
- **E2B Sandbox**: All GDPEval tools execute inside isolated sandbox
- **Event-Driven**: Inngest orchestrates execution and evaluation
- **PostgreSQL**: 7-table schema for experiments, runs, messages, actions, resources, evaluations

## Setup

### Prerequisites

1. Python 3.10+
2. Docker & Docker Compose
3. OpenAI API key
4. E2B API key

### Installation

1. Clone repository and navigate to `arcane_extension/`

2. Copy environment variables:
   ```bash
   cp .env.example .env
   # Edit .env with your API keys
   ```

3. Install dependencies:
   ```bash
   pip install -e .
   ```

4. Copy GDPEval data to `data/` directory:
   ```bash
   # Copy data from manager_agent_gym
   cp -r manager_agent_gym/curation/gdpeval/data data/
   ```
   
   The schema is already included in `h_arcane/schemas/staged_rubric_schema.py`.

5. Initialize database:
   ```bash
   python -m h_arcane.db.connection init_db
   ```

## Usage

### Running Experiments

**Automatic Service Management**: The CLI automatically checks if required services (PostgreSQL, Inngest dev server, API server) are running and starts them if needed. You don't need to manually start docker-compose services!

The `run_experiments.py` script provides a CLI for managing experiment runs.

#### Basic Commands

**Run experiments:**
```bash
# Run 10 examples with ReAct baseline
python scripts/run_experiments.py --num-examples 10 --baseline react

# Run with clean database (drops all existing tables first)
python scripts/run_experiments.py --num-examples 1 --baseline react --drop-old-results

# Run all available examples
python scripts/run_experiments.py --baseline react

# Dry run (test without starting runs)
python scripts/run_experiments.py --num-examples 5 --dry-run
```

**Monitor progress:**
```bash
# Check current experiment progress
python scripts/run_experiments.py --progress
```

**Retry failed runs:**
```bash
# Retry all failed runs
python scripts/run_experiments.py --retry-failed
```

#### Command-Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `--num-examples N` | Limit number of tasks to run | All available |
| `--baseline {react}` | Baseline worker type | `react` |
| `--dry-run` | Don't start runs, just show what would run | False |
| `--retry-failed` | Retry all failed runs | False |
| `--progress` | Show current experiment progress | False |
| `--drop-old-results` | Drop all existing database tables before running (clean slate) | False |

#### Examples

```bash
# Test with a small batch
python scripts/run_experiments.py --num-examples 3 --baseline react

# Start fresh with clean database
python scripts/run_experiments.py --num-examples 1 --baseline react --drop-old-results

# Check if everything is working before running full suite
python scripts/run_experiments.py --num-examples 10 --dry-run

# Monitor progress during a long run
python scripts/run_experiments.py --progress

# Recover from failures
python scripts/run_experiments.py --retry-failed
```

#### How It Works

1. **Loading**: Loads GDPEval tasks from `data/generated/staged_v2/staged_rubrics.jsonl`
2. **Database**: Creates `Experiment` records and `Resource` records for input files
3. **Runs**: Creates one `Run` record per experiment with configured baseline settings
4. **Execution**: Sends `run/start` events to Inngest (fire-and-forget)
5. **Concurrency**: Handled at Inngest function level:
   - `worker-execute`: 15 concurrent runs
   - `run-evaluate`: 25 concurrent runs

#### Progress Output

The `--progress` command shows:
- Total runs
- Pending runs
- Currently running runs
- Completed runs
- Failed runs
- Completion rate (percentage)

### Analyze Results

```bash
python scripts/analyze_results.py
```

*(Analysis scripts to be implemented)*

## LLM Utilities

Utilities designed to help LLM assistants (like Copilot) understand and work with the codebase.

### Database Dump Script

**Purpose**: Export all database tables to a formatted log file that LLMs can easily read and analyze.

**Usage**:
```bash
python scripts/dump_database.py
```

**Output**: Creates a timestamped log file in `data/database_dump_YYYYMMDD_HHMMSS.log`

**What it includes**:
- Summary statistics (row counts per table)
- All data from all 9 tables:
  - `experiments`: GDPEval tasks with ground truth rubrics
  - `runs`: Experiment execution runs with status and results
  - `messages`: Worker-stakeholder conversation history
  - `actions`: Tool execution traces with timing and costs
  - `resources`: Input/output file metadata
  - `agent_configs`: Agent configuration snapshots
  - `evaluations`: Aggregate evaluation results
  - `criterion_results`: Per-criterion evaluation scores
  - `task_evaluation_results`: Complete evaluation snapshots

**Use cases**:
- Share run results with LLM assistants for debugging
- Analyze experiment outcomes without database access
- Create snapshots for analysis or reporting
- Help Copilot understand what happened in a run

**Format**: Human-readable with UUIDs as strings, ISO datetimes, pretty-printed JSON, and clear NULL markers.

## Project Structure

```
arcane_extension/
├── h_arcane/              # Main implementation
│   ├── db/               # Database models and queries
│   ├── agents/          # Worker, stakeholder, toolkit
│   ├── tools/           # Tool modules (uploaded to sandbox)
│   ├── inngest/         # Event-driven orchestration
│   ├── evaluation/      # Evaluation pipeline
│   └── experiments/     # Data loading and runner
├── scripts/             # CLI scripts
├── paper_code_structure_plans/  # Documentation and data
└── theory.tex           # Research paper
```

## Development

### Running Tests

```bash
pytest tests/
```

### Database Migrations

Database schema is managed via SQLModel. To update:
1. Modify models in `h_arcane/db/models.py`
2. Run `init_db()` to recreate tables (development only)

## Documentation

See `paper_code_structure_plans/` for detailed architecture documentation:
- `00_MASTER_PLAN.md` - Overall architecture
- `01_CORE_ENTITIES.md` - Database schema
- `03_EVENT_ARCHITECTURE.md` - Inngest events
- `05_EVALUATION_ARCHITECTURE.md` - Evaluation system
- `SANDBOX_ARCHITECTURE.md` - E2B sandbox integration

