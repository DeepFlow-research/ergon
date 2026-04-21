"""Unit tests for TemplateSpec and NoSetup sentinel."""

from __future__ import annotations

from pathlib import Path

import pytest

from ergon_core.api.template_spec import (
    NoSetup,
    NoSetupSentinel,
    TemplateSpec,
    _NoSetupType,
)


class TestTemplateSpec:
    def test_frozen_rejects_mutation(self) -> None:
        spec = TemplateSpec(e2b_template_id="my-template")
        with pytest.raises(Exception):  # pydantic ValidationError or AttributeError
            spec.e2b_template_id = "other"  # type: ignore[misc]

    def test_default_all_none(self) -> None:
        spec = TemplateSpec()
        assert spec.e2b_template_id is None
        assert spec.build_recipe_path is None
        assert spec.runtime_install == ()

    def test_runtime_install_tuple(self) -> None:
        spec = TemplateSpec(runtime_install=("pdfplumber", "PyPDF2==3.0.0"))
        assert len(spec.runtime_install) == 2
        assert "pdfplumber" in spec.runtime_install

    def test_build_recipe_path_accepts_path(self) -> None:
        p = Path("/some/benchmark/sandbox")
        spec = TemplateSpec(e2b_template_id="ergon-minif2f-v1", build_recipe_path=p)
        assert spec.build_recipe_path == p

    def test_full_combo(self) -> None:
        spec = TemplateSpec(
            e2b_template_id="ergon-minif2f-v1",
            build_recipe_path=Path("/fake"),
            runtime_install=("lean4-extra",),
        )
        assert spec.e2b_template_id == "ergon-minif2f-v1"

    def test_e2b_template_id_only(self) -> None:
        spec = TemplateSpec(e2b_template_id="ergon-swebench-v1")
        assert spec.e2b_template_id == "ergon-swebench-v1"
        assert spec.build_recipe_path is None
        assert spec.runtime_install == ()


class TestNoSetupSingleton:
    def test_singleton_identity(self) -> None:
        a = _NoSetupType()
        b = _NoSetupType()
        assert a is b
        assert a is NoSetup

    def test_repr(self) -> None:
        assert repr(NoSetup) == "NoSetup"

    def test_isinstance_alias(self) -> None:
        assert isinstance(NoSetup, NoSetupSentinel)

    def test_not_template_spec(self) -> None:
        assert not isinstance(NoSetup, TemplateSpec)

    def test_isinstance_nosetup_type(self) -> None:
        assert isinstance(NoSetup, _NoSetupType)
