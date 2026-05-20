from argparse import Namespace

from ergon_cli.domains.doctor.models import DoctorCommand, DoctorReport
from ergon_cli.domains.doctor.service import run_doctor_checks
from ergon_cli.shared import exit_codes
from ergon_cli.shared.output import render_text


def handle_doctor(args: Namespace) -> int:
    del args
    report = run_doctor_checks(DoctorCommand())
    print(render_doctor_report(report))
    return exit_codes.OK if report.all_ok else exit_codes.RUNTIME_ERROR


def render_doctor_report(report: DoctorReport) -> str:
    lines = ["", "Ergon Doctor — checking your environment", ""]
    lines.extend(f"  [{check.status}] {check.message}" for check in report.checks)
    lines.append("")
    if report.all_ok:
        lines.append("All checks passed.")
    else:
        lines.append("Some checks failed — see warnings above.")
    return render_text(lines)
