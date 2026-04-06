import os
import json
from pathlib import Path
from sds_ax.config.schema import AgentConfig
from dotenv import load_dotenv


def load_config(cli_overrides: dict | None = None, project_root: str | None = None) -> AgentConfig:
    """5-level config priority: CLI > env > project > user > defaults"""
    config_dict = {}

    # User global
    user_path = Path.home() / ".deepagents" / "settings.json"
    if user_path.exists():
        with open(user_path) as f:
            config_dict.update(json.load(f))

    # Project
    root = Path(project_root or os.getcwd())
    proj_path = root / ".deepagents" / "settings.json"
    if proj_path.exists():
        with open(proj_path) as f:
            config_dict.update(json.load(f))

    # Env overrides
    load_dotenv()
    if v := os.environ.get("SDS_AX_MODEL"):
        config_dict["model"] = v
    if v := os.environ.get("SDS_AX_FALLBACK_MODEL"):
        config_dict["fallback_model"] = v
    if v := os.environ.get("SDS_AX_SANDBOX_MODE"):
        config_dict.setdefault("sandbox", {})["mode"] = v

    # CLI overrides
    if cli_overrides:
        config_dict.update(cli_overrides)

    config_dict.setdefault("project_root", str(root))
    return AgentConfig(**config_dict)


def ensure_api_keys():
    """Verify required API keys exist."""
    load_dotenv()
    if not os.environ.get("ANTHROPIC_API_KEY") and not os.environ.get("OPENAI_API_KEY"):
        print("Error: Missing ANTHROPIC_API_KEY or OPENAI_API_KEY")
        print("Set in .env file or export in shell.")
        raise SystemExit(1)
