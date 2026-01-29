"""DAHAO Sidecar - Autonomous governance voting agent.

Entry point for the sidecar that:
1. Connects to a Cosmos blockchain
2. Loads DAHAO shared law (terms, principles, rules, governance)
3. Polls for governance proposals
4. Uses local LLM to make voting decisions based on user values (Fork)
5. Submits signed vote transactions
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from brain.decision import DecisionEngine
from brain.llm import LLMWrapper
from chain.client import ChainClient
from chain.governance import GovernanceClient
from chain.wallet import InsufficientFundsError, WalletManager
from adapter import (
    ForkCache,
    Persona,
    PersonaLoader,
    PersonaMapper,
    PersonaMappingError,
    PersonaNotFoundError,
)
from config.fork import Fork, ForkValidationError
from config.settings import Settings
from data import SharedLaw, SharedLawLoadError
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
        "--data-dir",
        help="Path to shared law data directory (default: data/)",
    )
    parser.add_argument(
        "--skip-fork-validation",
        action="store_true",
        help="Skip validation of fork against shared law",
    )
    parser.add_argument(
        "--simple-validation",
        action="store_true",
        help="Use simple pattern-based validation instead of LLM (faster but less accurate)",
    )
    parser.add_argument(
        "--persona",
        help="Path to persona.json file (converts external persona to Fork)",
    )
    parser.add_argument(
        "--persona-cache",
        action="store_true",
        help="Enable caching of persona-to-fork mappings",
    )
    parser.add_argument(
        "--persona-cache-dir",
        help="Custom cache directory for persona-to-fork mappings",
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

    # Load shared law (DAHAO governance data)
    shared_law = None
    try:
        data_dir = Path(args.data_dir) if args.data_dir else None
        shared_law = SharedLaw(data_dir)
        summary = shared_law.summary()
        logger.info(
            f"Loaded shared law: {summary['instance_id']} v{summary['core_version']}"
        )
        logger.info(
            f"  Terms: {summary['terms_count']}, "
            f"Principles: {summary['principles_count']} "
            f"({summary['locked_principles_count']} locked), "
            f"Rules: {summary['rules_count']}"
        )
    except SharedLawLoadError as e:
        logger.warning(f"Failed to load shared law: {e}")
        logger.warning("Continuing without shared law context")
    except Exception as e:
        logger.warning(f"Error loading shared law: {e}")
        logger.warning("Continuing without shared law context")

    # Initialize fork variable - will be set by persona mapping or fork.yaml
    fork = None
    llm = None

    # Handle persona-based fork generation
    if args.persona:
        try:
            # Load persona
            persona_loader = PersonaLoader(args.persona)
            persona = persona_loader.load_or_raise()
            logger.info(f"Loaded persona: {persona.archetype} (user: {persona.user_id})")

            # Check cache (if enabled)
            if args.persona_cache and shared_law:
                cache = ForkCache(args.persona_cache_dir)
                fork = cache.get(persona, shared_law.core_version)
                if fork:
                    logger.info(f"Loaded Fork from cache: {fork.name}")

            # Map to Fork if not cached
            if fork is None:
                if not shared_law:
                    logger.error("Persona mapping requires shared law data. Ensure data/ directory exists.")
                    sys.exit(1)

                # Initialize LLM early for mapping
                logger.info("Initializing LLM for persona mapping...")
                llm = LLMWrapper(settings.llm)
                _ = llm.model  # Verify model is available
                logger.info("LLM loaded successfully")

                mapper = PersonaMapper(llm, shared_law)
                fork = mapper.map(persona)
                logger.info(f"Generated Fork from persona: {fork.name}")
                logger.info(f"  Principles: {len(fork.principles)}")
                logger.info(f"  Voting style: {fork.voting_style}")

                # Cache the generated fork
                if args.persona_cache:
                    cache = ForkCache(args.persona_cache_dir)
                    cache_path = cache.put(persona, shared_law.core_version, fork)
                    logger.info(f"Cached Fork to: {cache_path}")

        except PersonaNotFoundError as e:
            logger.warning(f"Persona not found: {e}")
            logger.warning("Falling back to fork.yaml")
        except PersonaMappingError as e:
            logger.error(f"Persona mapping failed: {e}")
            sys.exit(1)

    # Load fork from YAML (fallback or default)
    if fork is None:
        try:
            fork = Fork.from_yaml(args.fork)
            logger.info(f"Loaded fork: {fork.name}")
            logger.info(f"  Inherits: {fork.inherits}")
            logger.info(f"  Voting style: {fork.voting_style}")
            logger.info(f"  Principles: {len(fork.principles)}")
            if fork.uses_terms:
                logger.info(f"  Uses terms: {fork.uses_terms}")
        except FileNotFoundError:
            logger.error(f"Fork file '{args.fork}' not found. Please create it with your voting values.")
            sys.exit(1)
        except Exception as e:
            logger.error(f"Failed to load fork: {e}")
            sys.exit(1)

    # Simple validation (if requested) - fast pattern-based check
    if shared_law and not args.skip_fork_validation and args.simple_validation:
        try:
            fork.validate_against(shared_law)
            logger.info("Fork validated against shared law (simple mode)")
        except ForkValidationError as e:
            logger.error(f"Fork validation failed: {e}")
            logger.error("Violations:")
            for v in e.violations:
                logger.error(f"  - {v}")
            logger.error("Use --skip-fork-validation to bypass (not recommended)")
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

    # Initialize LLM (if not already done during persona mapping)
    if llm is None:
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

    # LLM-based fork validation (default, more accurate)
    if shared_law and not args.skip_fork_validation and not args.simple_validation:
        try:
            logger.info("Validating fork with LLM (semantic analysis)...")
            fork.validate_against_with_llm(shared_law, llm)
            logger.info("Fork validated against shared law (LLM mode)")
        except ForkValidationError as e:
            logger.error(f"Fork validation failed: {e}")
            logger.error("Violations:")
            for v in e.violations:
                logger.error(f"  - {v}")
            logger.error("Use --skip-fork-validation to bypass or --simple-validation for pattern-based check")
            sys.exit(1)

    # Create decision engine (with shared law for enhanced prompts)
    decision_engine = DecisionEngine(llm, fork, shared_law)

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
        shared_law=shared_law,
        agent_name=agent_name,
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
