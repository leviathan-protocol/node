"""DAHAO Sidecar - Autonomous governance voting agent.

Entry point for the sidecar that:
1. Connects to a Cosmos blockchain
2. Polls for governance proposals
3. Uses local LLM to make voting decisions based on user values (Fork)
4. Submits signed vote transactions
"""

import argparse
import asyncio
import logging
import os
import sys

from brain.decision import DecisionEngine
from brain.llm import LLMWrapper
from chain.client import ChainClient
from chain.governance import GovernanceClient
from chain.wallet import InsufficientFundsError, WalletManager
from config.fork import Fork
from config.settings import Settings
from sidecar.loop import SidecarLoop
from sidecar.state import SidecarState


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="DAHAO Sidecar - Autonomous governance voting agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to config.yaml (default: config.yaml)",
    )
    parser.add_argument(
        "--fork",
        default="fork.yaml",
        help="Path to fork.yaml with voting principles (default: fork.yaml)",
    )
    parser.add_argument(
        "--wallet",
        help="Wallet mnemonic (24 words). Overrides LEVIATHAN_MNEMONIC env var.",
    )
    parser.add_argument(
        "--state",
        help="Path to state file (default: from config or sidecar_state.json)",
    )
    parser.add_argument(
        "--name",
        help="Override agent name for logging (useful for simulations)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)",
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
    """Main entry point for the DAHAO sidecar."""
    args = parse_args()
    logger = setup_logging(args.log_level, args.name)

    agent_name = args.name or "Sidecar"
    logger.info(f"Starting DAHAO {agent_name}")

    # Load configuration
    try:
        settings = Settings.from_yaml(args.config)
        logger.info(f"Loaded settings for chain: {settings.chain.chain_id}")
    except Exception as e:
        logger.error(f"Failed to load settings: {e}")
        sys.exit(1)

    # Load fork (user values)
    try:
        fork = Fork.from_yaml(args.fork)
        logger.info(f"Loaded fork: {fork.name}")
        logger.info(f"Voting style: {fork.voting_style}")
        logger.info(f"Principles: {len(fork.principles)}")
    except FileNotFoundError:
        logger.error(f"Fork file '{args.fork}' not found. Please create it with your voting values.")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Failed to load fork: {e}")
        sys.exit(1)

    # Get mnemonic from CLI arg or env var
    mnemonic = args.wallet or settings.mnemonic
    if not mnemonic:
        logger.error(
            "No mnemonic configured. Use --wallet or set LEVIATHAN_MNEMONIC environment variable "
            "with your wallet's 24-word mnemonic."
        )
        sys.exit(1)

    # Initialize chain client
    try:
        chain_client = ChainClient(settings.chain)
        logger.info(f"Connected to chain at {settings.chain.grpc_url}")
    except Exception as e:
        logger.error(f"Failed to connect to chain: {e}")
        sys.exit(1)

    # Initialize wallet
    try:
        wallet = WalletManager(mnemonic, settings.chain.address_prefix)
        logger.info(f"Wallet address: {wallet.address}")
    except Exception as e:
        logger.error(f"Failed to initialize wallet: {e}")
        sys.exit(1)

    # Check wallet balance (fail fast if no gas tokens)
    try:
        wallet.ensure_funded(chain_client)
    except InsufficientFundsError as e:
        logger.error(str(e))
        sys.exit(1)
    except Exception as e:
        logger.error(f"Failed to check wallet balance: {e}")
        sys.exit(1)

    # Initialize LLM
    try:
        llm = LLMWrapper(settings.llm)
        # Trigger model load now to fail fast
        _ = llm.model
        logger.info("LLM loaded successfully")
    except FileNotFoundError as e:
        logger.error(f"LLM model not found: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Failed to load LLM: {e}")
        sys.exit(1)

    # Create decision engine
    decision_engine = DecisionEngine(llm, fork)

    # Create governance client
    governance = GovernanceClient(chain_client, settings.chain)

    # Load state - use CLI arg, config, or default
    state_file = args.state or settings.sidecar.state_file
    state = SidecarState.load(state_file)

    # Create and run the sidecar loop
    sidecar = SidecarLoop(
        governance=governance,
        wallet=wallet,
        decision_engine=decision_engine,
        fork=fork,
        config=settings.sidecar,
        state=state,
    )

    logger.info("Starting sidecar loop...")
    try:
        asyncio.run(sidecar.run())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Sidecar crashed: {e}", exc_info=True)
        sys.exit(1)

    logger.info("DAHAO Sidecar stopped")


if __name__ == "__main__":
    main()
