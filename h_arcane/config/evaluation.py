"""Evaluation configuration loaded from YAML."""

from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class LLMEvaluationConfig(BaseModel):
    """Configuration for LLM evaluation."""

    model: str = Field(description="LLM model to use for evaluation")
    temperature: float = Field(
        ge=0.0, le=2.0, description="Temperature for LLM evaluation (0.0 = deterministic)"
    )
    max_tokens: int = Field(ge=1, description="Maximum tokens for LLM evaluation response")
    seed: int | None = Field(
        default=None, description="Random seed for deterministic evaluation (None = random)"
    )


class LLMStakeholderConfig(BaseModel):
    """Configuration for LLM stakeholder responses."""

    model: str = Field(description="LLM model to use for stakeholder responses")
    temperature: float = Field(ge=0.0, le=2.0, description="Temperature for stakeholder responses")
    max_tokens: int = Field(ge=1, description="Maximum tokens for stakeholder response")
    seed: int | None = Field(
        default=None, description="Random seed for stakeholder responses (None = random)"
    )


class EvaluationConfig(BaseModel):
    """Root evaluation configuration."""

    llm_evaluation: LLMEvaluationConfig = Field(description="LLM evaluation settings")
    llm_stakeholder: LLMStakeholderConfig = Field(description="LLM stakeholder settings")

    @classmethod
    def from_yaml(cls, yaml_path: Path | str) -> "EvaluationConfig":
        """Load configuration from YAML file."""
        yaml_path = Path(yaml_path)
        if not yaml_path.exists():
            raise FileNotFoundError(
                f"Evaluation config file not found: {yaml_path}. "
                "Please create config/evaluation.yaml with required llm_evaluation settings."
            )

        with open(yaml_path, "r") as f:
            data = yaml.safe_load(f) or {}

        return cls(**data)

    @classmethod
    def load_default(cls) -> "EvaluationConfig":
        """Load configuration from default location."""
        # Path: h_arcane/config/ -> h_arcane -> arcane_extension -> config/evaluation.yaml
        config_path = Path(__file__).parent.parent.parent / "config" / "evaluation.yaml"
        return cls.from_yaml(config_path)


# Global evaluation config instance
evaluation_config = EvaluationConfig.load_default()
