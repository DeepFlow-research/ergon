"""
Convert GDPEval code rules from (workflow, context) to (task_input, agent_reasoning, output_files) signature.
Uses LLM to transpile Python functions.
"""

import argparse
import asyncio
import json
from pathlib import Path

from openai import AsyncOpenAI

from h_arcane.core.settings import settings

# Initialize OpenAI client
client = AsyncOpenAI(api_key=settings.openai_api_key)

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


async def convert_code_rule(code: str, model: str = "gpt-4o") -> str:
    """
    Convert a single code rule using LLM transpilation.

    Args:
        code: Original Python code with MA-gym signature
        model: LLM model to use for conversion

    Returns:
        Converted Python code with our signature
    """
    prompt = CONVERSION_PROMPT.format(code=code)

    response = await client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": "You are a Python code transpiler that converts function signatures and API calls.",
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.0,  # Deterministic conversion
    )

    content = response.choices[0].message.content
    if content is None:
        raise ValueError("LLM returned empty response")
    converted_code = content.strip()

    # Remove markdown code blocks if present
    if converted_code.startswith("```python"):
        converted_code = converted_code[9:]
    if converted_code.startswith("```"):
        converted_code = converted_code[3:]
    if converted_code.endswith("```"):
        converted_code = converted_code[:-3]

    return converted_code.strip()


async def convert_rubric_file(
    rubric_file: Path,
    model: str = "gpt-4o",
    output_file: Path | None = None,
    max_concurrent: int = 10,
) -> Path:
    """
    Convert all code rules in a rubric JSONL file.

    Args:
        rubric_file: Path to input JSONL file
        model: LLM model to use for conversion
        output_file: Optional output path (defaults to {rubric_file.stem}_converted.jsonl)

    Returns:
        Path to converted output file
    """
    if output_file is None:
        output_file = rubric_file.parent / f"{rubric_file.stem}_converted.jsonl"

    # Collect all code rules to convert with their locations
    rules_to_convert = []
    rubric_data = []

    with open(rubric_file) as f_in:
        for line_num, line in enumerate(f_in, 1):
            data = json.loads(line)
            rubric_data.append(data)

            for stage_idx, stage in enumerate(data.get("rubric", {}).get("stages", [])):
                for rule_idx, rule in enumerate(stage.get("rules", [])):
                    if rule.get("type") == "code":
                        rules_to_convert.append(
                            {
                                "line_num": line_num,
                                "stage_idx": stage_idx,
                                "rule_idx": rule_idx,
                                "code": rule["code"],
                                "stage_name": stage.get("name", "unknown"),
                            }
                        )

    if not rules_to_convert:
        # No code rules to convert, just copy file
        with open(rubric_file) as f_in, open(output_file, "w") as f_out:
            f_out.write(f_in.read())
        return output_file

    print(f"  Converting {len(rules_to_convert)} code rules (max {max_concurrent} concurrent)...")

    # Convert all rules concurrently with semaphore for rate limiting
    semaphore = asyncio.Semaphore(max_concurrent)
    converted_count = 0
    failed_rules = []

    async def convert_with_semaphore(rule_info):
        nonlocal converted_count
        async with semaphore:
            try:
                converted_code = await convert_code_rule(rule_info["code"], model=model)
                converted_count += 1
                if converted_count % 10 == 0:
                    print(
                        f"  ✓ Converted {converted_count}/{len(rules_to_convert)} rules", end="\r"
                    )
                return rule_info, converted_code, None
            except Exception as e:
                return rule_info, None, str(e)

    # Run all conversions concurrently
    results = await asyncio.gather(*[convert_with_semaphore(rule) for rule in rules_to_convert])

    # Apply conversions to rubric data
    for rule_info, converted_code, error in results:
        if error:
            failed_rules.append(
                {
                    "line": rule_info["line_num"],
                    "stage": rule_info["stage_name"],
                    "rule_idx": rule_info["rule_idx"],
                    "error": error,
                }
            )
            print(
                f"\n  ⚠️  Failed to convert rule at line {rule_info['line_num']}, "
                f"stage {rule_info['stage_name']}, rule {rule_info['rule_idx']}: {error[:100]}"
            )
        else:
            rubric_data[rule_info["line_num"] - 1]["rubric"]["stages"][rule_info["stage_idx"]][
                "rules"
            ][rule_info["rule_idx"]]["code"] = converted_code

    # Write converted data
    with open(output_file, "w") as f_out:
        for data in rubric_data:
            f_out.write(json.dumps(data) + "\n")

    print(f"\n✅ Converted {converted_count}/{len(rules_to_convert)} code rules")
    if failed_rules:
        print(f"⚠️  {len(failed_rules)} rules failed conversion (kept originals)")

    return output_file


async def main():
    parser = argparse.ArgumentParser(description="Convert GDPEval code rules to new signature")
    parser.add_argument(
        "--rubric-file",
        type=Path,
        help="Path to rubric JSONL file",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path("data/generated/staged_v2"),
        help="Directory containing rubric files",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="gpt-4o",
        help="LLM model to use for conversion",
    )
    parser.add_argument(
        "--max-concurrent",
        type=int,
        default=10,
        help="Maximum concurrent API calls (default: 10)",
    )

    args = parser.parse_args()

    if args.rubric_file:
        # Convert single file
        print(f"Converting {args.rubric_file.name}...")
        output_file = await convert_rubric_file(
            args.rubric_file, model=args.model, max_concurrent=args.max_concurrent
        )
        print(f"✅ Converted to {output_file.name}")
    else:
        # Convert all rubric files in directory
        data_dir = args.data_dir
        if not data_dir.exists():
            print(f"❌ Directory not found: {data_dir}")
            exit(1)

        rubric_files = list(data_dir.glob("*_rubrics.jsonl"))
        print(f"Found {len(rubric_files)} rubric files to process\n")

        for idx, rubric_file in enumerate(rubric_files, 1):
            print(f"[{idx}/{len(rubric_files)}] Converting {rubric_file.name}...")
            output_file = await convert_rubric_file(
                rubric_file, model=args.model, max_concurrent=args.max_concurrent
            )
            print(f"✅ Saved to {output_file.name}\n")


if __name__ == "__main__":
    asyncio.run(main())
