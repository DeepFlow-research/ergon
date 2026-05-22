from typing import Literal

from pydantic import BaseModel, ConfigDict


class DoctorCommand(BaseModel):
    model_config = ConfigDict(frozen=True)

    action: Literal["check"] = "check"


class DoctorCheck(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: Literal["PASS", "WARN", "FAIL"]
    message: str


class DoctorReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    checks: tuple[DoctorCheck, ...]

    @property
    def all_ok(self) -> bool:
        return all(check.status == "PASS" for check in self.checks)
