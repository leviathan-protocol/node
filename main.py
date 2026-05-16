"""Leviathan Sidecar - Autonomous governance voting agent.

Two modes of operation:
- **Decider Mode** (default): Autonomous polling loop that makes voting decisions
  based on Fork values and submits them automatically.
- **Observer Mode**: API gateway for mobile clients (Gasless Voting) that validates
  and relays signed voting intents from users.

Entry point that:
1. Parses command line arguments
2. Loads configuration
3. Routes to the appropriate mode
"""

import argparse
import logging
import sys

from config.settings import Settings
from modes import run_decider_mode, run_observer_mode


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Leviathan Sidecar - Autonomous governance voting agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run in decider mode (default - autonomous voting)
  python main.py --fork fork.yaml

  # Run in observer mode (API gateway for mobile clients)
  python main.py --mode=observer --host=0.0.0.0 --port=8080

  # Run decider mode with persona file
  python main.py --mode=decider --persona persona.json

  # Run observer mode with custom settings
  python main.py --mode=observer --host=0.0.0.0 --port=8080 --log-level=DEBUG
""",
    )

    # Mode selection
    parser.add_argument(
        "--mode",
        choices=["decider", "observer"],
        default="decider",
        help="Operation mode: 'decider' (autonomous voting) or 'observer' (API gateway). Default: decider",
    )

    # Common arguments
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to config.yaml (default: config.yaml)",
    )
    parser.add_argument(
        "--wallet",
        help="Wallet mnemonic (24 words). Overrides LEVIATHAN_MNEMONIC env var.",
    )
    parser.add_argument(
        "--data-dir",
        help="Path to shared law data directory (default: data/)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)",
    )

    # Decider mode arguments
    decider_group = parser.add_argument_group("Decider Mode Options")
    decider_group.add_argument(
        "--fork",
        default="fork.yaml",
        help="Path to fork.yaml with voting principles (default: fork.yaml)",
    )
    decider_group.add_argument(
        "--state",
        help="Path to state file (default: from config or sidecar_state.json)",
    )
    decider_group.add_argument(
        "--name",
        help="Override agent name for logging (useful for simulations)",
    )
    decider_group.add_argument(
        "--skip-fork-validation",
        action="store_true",
        help="Skip validation of fork against shared law",
    )
    decider_group.add_argument(
        "--simple-validation",
        action="store_true",
        help="Use simple pattern-based validation instead of LLM (faster but less accurate)",
    )
    decider_group.add_argument(
        "--persona",
        help="Path to persona.json file (converts external persona to Fork)",
    )
    decider_group.add_argument(
        "--persona-cache",
        action="store_true",
        help="Enable caching of persona-to-fork mappings",
    )
    decider_group.add_argument(
        "--persona-cache-dir",
        help="Custom cache directory for persona-to-fork mappings",
    )

    # Observer mode arguments
    observer_group = parser.add_argument_group("Observer Mode Options")
    observer_group.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host to bind the API server (default: 0.0.0.0)",
    )
    observer_group.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port for the API server (default: 8080)",
    )

    return parser.parse_args()


def setup_logging(level: str, agent_name: str | None = None):
    """Configure logging with optional agent name prefix."""
    prefix = f"[{agent_name}] " if agent_name else ""
    logging.basicConfig(
        level=getattr(logging, level),
        format=f"%(asctime)s {prefix}[%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    return logging.getLogger(__name__)


def main():
    """Main entry point for the Leviathan sidecar."""
    args = parse_args()

    # Set up logging (with agent name for decider mode)
    agent_name = args.name if args.mode == "decider" else None
    logger = setup_logging(args.log_level, agent_name)

    logger.info(f"Leviathan Sidecar starting in {args.mode.upper()} mode")

    # Load configuration
    try:
        settings = Settings.from_yaml(args.config)
        logger.info(f"Loaded settings for chain: {settings.chain.chain_id}")
    except Exception as e:
        logger.error(f"Failed to load settings: {e}")
        sys.exit(1)

    # Route to appropriate mode
    if args.mode == "decider":
        exit_code = run_decider_mode(args, settings)
    elif args.mode == "observer":
        exit_code = run_observer_mode(args, settings)
    else:
        logger.error(f"Unknown mode: {args.mode}")
        exit_code = 1

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
