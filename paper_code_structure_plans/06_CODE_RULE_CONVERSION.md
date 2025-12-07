# Code Rule Conversion Script

One-off script to convert GDPEval code rules from MA-gym signature to our signature.

**Purpose**: Convert all GDPEval code rules during data loading so they work with our evaluation architecture.

---

## Conversion Strategy

### From (MA-gym):
```python
def evaluate(workflow: Workflow, context: ValidationContext) -> float | tuple[float, str]:
    # Uses:
    # - context.get_primary_output() -> Resource
    # - context.files.read_excel(resource_id, sheet_name='...') -> DataFrame
    # - context.files.read_pdf_text(resource_id) -> str
    # - context.files.get_path(resource_id) -> Path
    # - workflow (usually not used)
```

### To (Our signature):
```python
def evaluate(task_input: str, agent_reasoning: str, output_files: dict[str, bytes]) -> float | tuple[float, str]:
    # Uses:
    # - output_files: dict mapping file paths to bytes
    # - Direct file operations (pandas, pdfplumber, etc.)
    # - task_input: Original task description
    # - agent_reasoning: Worker's reasoning/output text
```

---

## Conversion Patterns

### Pattern 1: Get Primary Output
```python
# Before:
output = context.get_primary_output()
if not output:
    return 0.0
file_path = context.files.get_path(output.id)

# After:
if not output_files:
    return 0.0
# Use first file (or find by name/type)
first_file_path = list(output_files.keys())[0]
file_content = output_files[first_file_path]
```

### Pattern 2: Read Excel
```python
# Before:
df = context.files.read_excel(output.id, sheet_name='Analysis')

# After:
import pandas as pd
import io
# Find Excel file in output_files
excel_path = next(k for k in output_files.keys() if k.endswith('.xlsx'))
df = pd.read_excel(io.BytesIO(output_files[excel_path]), sheet_name='Analysis')
```

### Pattern 3: Read PDF
```python
# Before:
text = context.files.read_pdf_text(output.id)

# After:
import pdfplumber
import io
# Find PDF file
pdf_path = next(k for k in output_files.keys() if k.endswith('.pdf'))
with pdfplumber.open(io.BytesIO(output_files[pdf_path])) as pdf:
    text = "\n".join(page.extract_text() for page in pdf.pages)
```

### Pattern 4: Read DOCX
```python
# Before:
text = context.files.read_docx_text(output.id)

# After:
from docx import Document
import io
# Find DOCX file
docx_path = next(k for k in output_files.keys() if k.endswith('.docx'))
doc = Document(io.BytesIO(output_files[docx_path]))
text = "\n".join(para.text for para in doc.paragraphs)
```

### Pattern 5: Get All Outputs
```python
# Before:
all_outputs = context.get_all_outputs()
for output in all_outputs:
    if output.is_spreadsheet:
        # ...

# After:
for file_path, file_content in output_files.items():
    if file_path.endswith(('.xlsx', '.xls', '.csv')):
        # ...
```

---

## Implementation

```python
# scripts/convert_code_rules.py
"""
Convert GDPEval code rules from (workflow, context) to (task_input, agent_reasoning, output_files) signature.
Uses LLM to transpile Python functions.
"""
from pathlib import Path
import json
from openai import OpenAI

# Initialize OpenAI client (or use your preferred LLM provider)
client = OpenAI()

CONVERSION_PROMPT = """You are converting a Python evaluation function from one API signature to another.

**Original signature:**
```python
def evaluate(workflow: Workflow, context: ValidationContext) -> float | tuple[float, str]:
```

**Target signature:**
```python
def evaluate(task_input: str, agent_reasoning: str, output_files: dict[str, bytes]) -> float | tuple[float, str]:
```

**Conversion rules:**
1. Replace function signature parameters: `workflow` and `context` → `task_input`, `agent_reasoning`, `output_files`
2. Replace `context.get_primary_output()` → use `output_files` dict (first file or find by extension)
3. Replace `context.files.read_excel(resource_id, sheet_name='...')` → `pd.read_excel(io.BytesIO(output_files[excel_path]), sheet_name='...')`
4. Replace `context.files.read_pdf_text(resource_id)` → use `pdfplumber.open(io.BytesIO(output_files[pdf_path]))`
5. Replace `context.files.read_docx_text(resource_id)` → use `Document(io.BytesIO(output_files[docx_path]))`
6. Replace `context.files.get_path(resource_id)` → use keys from `output_files` dict
7. Replace `context.get_all_outputs()` → iterate over `output_files.items()`
8. Add necessary imports (pandas, pdfplumber, docx, io) at the top if needed
9. Remove any references to `workflow` parameter (usually unused)
10. Preserve all logic, comments, and return values exactly

**Example conversions:**

Before:
```python
def evaluate(workflow: Workflow, context: ValidationContext) -> float:
    output = context.get_primary_output()
    if not output:
        return 0.0
    df = context.files.read_excel(output.id, sheet_name='Analysis')
    return 1.0 if len(df) > 0 else 0.0
```

After:
```python
import pandas as pd
import io

def evaluate(task_input: str, agent_reasoning: str, output_files: dict[str, bytes]) -> float:
    if not output_files:
        return 0.0
    excel_path = next(k for k in output_files.keys() if k.endswith('.xlsx'))
    df = pd.read_excel(io.BytesIO(output_files[excel_path]), sheet_name='Analysis')
    return 1.0 if len(df) > 0 else 0.0
```

Now convert the following function:

```python
{code}
```

Return ONLY the converted Python code, no explanations or markdown formatting."""

def convert_code_rule(code: str, model: str = "gpt-4o") -> str:
    """
    Convert a single code rule using LLM transpilation.
    
    Args:
        code: Original Python code with MA-gym signature
        model: LLM model to use for conversion
        
    Returns:
        Converted Python code with our signature
    """
    prompt = CONVERSION_PROMPT.format(code=code)
    
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You are a Python code transpiler that converts function signatures and API calls."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.0,  # Deterministic conversion
    )
    
    converted_code = response.choices[0].message.content.strip()
    
    # Remove markdown code blocks if present
    if converted_code.startswith("```python"):
        converted_code = converted_code[9:]
    if converted_code.startswith("```"):
        converted_code = converted_code[3:]
    if converted_code.endswith("```"):
        converted_code = converted_code[:-3]
    
    return converted_code.strip()

def convert_rubric_file(rubric_file: Path, model: str = "gpt-4o") -> Path:
    """
    Convert all code rules in a rubric JSONL file.
    
    Args:
        rubric_file: Path to input JSONL file
        model: LLM model to use for conversion
        
    Returns:
        Path to converted output file
    """
    output_file = rubric_file.parent / f"{rubric_file.stem}_converted.jsonl"
    
    converted_count = 0
    failed_rules = []
    
    with open(rubric_file) as f_in, open(output_file, 'w') as f_out:
        for line_num, line in enumerate(f_in, 1):
            data = json.loads(line)
            
            # Convert code rules in each stage
            for stage in data.get("rubric", {}).get("stages", []):
                for rule_idx, rule in enumerate(stage.get("rules", [])):
                    if rule.get("type") == "code":
                        try:
                            original_code = rule["code"]
                            rule["code"] = convert_code_rule(original_code, model=model)
                            converted_count += 1
                        except Exception as e:
                            failed_rules.append({
                                "line": line_num,
                                "stage": stage.get("name", "unknown"),
                                "rule_idx": rule_idx,
                                "error": str(e)
                            })
                            # Keep original code on failure
                            print(f"⚠️  Failed to convert rule at line {line_num}, stage {stage.get('name')}, rule {rule_idx}: {e}")
            
            f_out.write(json.dumps(data) + "\n")
    
    print(f"✅ Converted {converted_count} code rules")
    if failed_rules:
        print(f"⚠️  {len(failed_rules)} rules failed conversion (kept originals)")
    
    return output_file

if __name__ == "__main__":
    # Convert all rubric files
    data_dir = Path("paper_code_structure_plans/data/generated/staged_v2")
    
    for rubric_file in data_dir.glob("*_rubrics.jsonl"):
        print(f"Converting {rubric_file.name}...")
        convert_rubric_file(rubric_file)
        print(f"✅ Converted to {rubric_file.stem}_converted.jsonl")
```

---

## Usage

Run during Phase 1 data loading:

```python
# h_arcane/experiments/loader.py
from scripts.convert_code_rules import convert_rubric_file

def load_gdpeval_tasks(...):
    # ... load rubrics ...
    
    # Convert code rules
    rubric_file = DATA_DIR / "generated" / "staged_v2" / "staged_rubrics.jsonl"
    converted_file = convert_rubric_file(rubric_file)
    
    # Use converted file for loading
    # ...
```

---

## Notes

- **LLM-based transpilation**: Uses GPT-4o (or configurable model) to semantically understand and convert code
- **One-time conversion**: Run once during data loading, not at runtime
- **Preserve originals**: Keep original files, write converted versions
- **Error handling**: Failed conversions keep original code and are logged for manual review
- **Deterministic**: Uses temperature=0.0 for consistent conversions
- **Testing**: Test converted rules work with our evaluation architecture
- **Fallback**: If conversion fails for a rule, original code is preserved and error is logged

