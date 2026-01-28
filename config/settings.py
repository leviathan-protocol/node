"""Pydantic settings for chain, LLM, and sidecar configuration."""

from pathlib import Path

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ChainConfig(BaseModel):
    """Cosmos chain connection settings."""

    chain_id: str = "dahao"
    grpc_url: str = "grpc+http://localhost:9090"
    fee_denom: str = "stake"
    address_prefix: str = "cosmos"
    gas_limit: int = 200000
    fee_amount: int = 1000


class LLMConfig(BaseModel):
    """Ollama LLM settings."""

    model_name: str = "ministral-3:8b"
    ollama_host: str = "http://localhost:11434"
    n_ctx: int = 8192


class SidecarConfig(BaseModel):
    """Sidecar behavior settings."""

    poll_interval_seconds: int = 60
    max_retries: int = 3
    state_file: str = "sidecar_state.json"
    decisions_log: str = "decisions.log"


class Settings(BaseSettings):
    """Main settings container, loaded from config.yaml and environment."""

    model_config = SettingsConfigDict(
        env_prefix="LEVIATHAN_",
        env_nested_delimiter="__",
    )

    chain: ChainConfig = Field(default_factory=ChainConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    sidecar: SidecarConfig = Field(default_factory=SidecarConfig)

    # Sensitive values from environment
    mnemonic: str = Field(default="", description="Wallet mnemonic from LEVIATHAN_MNEMONIC env var")

    @classmethod
    def from_yaml(cls, config_path: str | Path = "config.yaml") -> "Settings":
        """Load settings from YAML file, with env var overrides."""
        config_path = Path(config_path)
        if config_path.exists():
            with open(config_path) as f:
                yaml_config = yaml.safe_load(f) or {}
        else:
            yaml_config = {}

        return cls(**yaml_config)
