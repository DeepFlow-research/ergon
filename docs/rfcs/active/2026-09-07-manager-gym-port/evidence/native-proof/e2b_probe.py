"""One bounded real E2B backend probe; no model calls or MAG implementation."""

import asyncio
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path.cwd() / ".env", override=False)

from ergon_builtins.sandbox.e2b_sandbox import E2BSandbox
from ergon_core.api.sandbox.sandbox import Sandbox
from ergon_core.core.infrastructure.sandbox.lifecycle import terminate_external_sandbox

OUT = Path(__file__).with_name("e2b-result.json")
FILE = "/workspace/final_output/native-proof.txt"


async def attach(sandbox_id: str) -> dict[str, object]:
    sandbox = await Sandbox.from_definition(
        E2BSandbox(timeout_seconds=300).model_dump(mode="json"), sandbox_id=sandbox_id
    )
    data = await sandbox.read_file(FILE)
    result = {
        "read_return_type": type(data).__name__,
        "byte_read_contract": isinstance(data, bytes),
        "initial_content_matches": data in (b"native-proof", "native-proof"),
    }
    await sandbox.write_file(FILE, b"cross-process-proof")
    result["reattach_read_write"] = result["initial_content_matches"]
    try:
        await sandbox.detach()
        result["detach"] = True
    except Exception as exc:
        result["detach"] = False
        result["detach_error_type"] = type(exc).__name__
    return result


async def main() -> None:
    result = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "scope": "real E2B backend and cleanup boundary; not full Inngest task lifecycle",
        "sandbox_timeout_seconds": 300,
    }
    sandbox = E2BSandbox(timeout_seconds=300)
    sandbox_id = None
    try:
        await sandbox.provision()
        sandbox_id = sandbox.sandbox_id
        result.update(provisioned=True, sandbox_id=sandbox_id)
        OUT.write_text(json.dumps(result, indent=2))
        await sandbox.write_file(FILE, b"native-proof")
        completed = await asyncio.to_thread(
            subprocess.run,
            [sys.executable, str(Path(__file__).resolve()), "--attach", sandbox_id],
            capture_output=True,
            text=True,
            timeout=90,
        )
        if completed.returncode != 0:
            result["child_error"] = (
                "attachment subprocess failed; credentials and raw stderr withheld"
            )
        else:
            result.update(json.loads(completed.stdout))
            result["cross_process_output_visible"] = await sandbox.read_file(FILE) in (
                b"cross-process-proof",
                "cross-process-proof",
            )
    except Exception as exc:
        result["error_type"] = type(exc).__name__
        result["http_status"] = getattr(exc, "status_code", None)
    finally:
        if sandbox_id:
            cleanup = await terminate_external_sandbox(sandbox_id)
            result["native_cleanup"] = cleanup.model_dump(mode="json")
            if not cleanup.terminated:
                try:
                    await sandbox.terminate()
                    result["direct_cleanup_fallback"] = True
                except Exception as exc:
                    result["cleanup_error_type"] = type(exc).__name__
        result["finished_at"] = datetime.now(timezone.utc).isoformat()
        OUT.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--attach":
        print(json.dumps(asyncio.run(attach(sys.argv[2]))))
    else:
        asyncio.run(main())
