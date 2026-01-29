"""Decider Mode - Autonomous governance voting agent.

This is the original sidecar mode that:
1. Polls for governance proposals on the blockchain
2. Uses a local LLM to make voting decisions based on Fork values
3. Submits signed vote transactions automatically

This mode runs as an autonomous agent - no human intervention required.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from adapter import (
    ForkCache,
    PersonaLoader,
    PersonaMapper,
    PersonaMappingError,
    PersonaNotFoundError,
)
from brain.decision import DecisionEngine
from brain.llm import LLMWrapper
from chain.client import ChainClient
from chain.governance import GovernanceClient
from chain.wallet import InsufficientFundsError, WalletManager
from config.fork import Fork, ForkValidationError
from data import SharedLaw, SharedLawLoadError
from sidecar.loop import SidecarLoop
from sidecar.state import SidecarState

if TYPE_CHECKING:
    import argparse

    from config.settings import Settings

logger = logging.getLogger(__name__)


def run_decider_mode(args: "argparse.Namespace", settings: "Settings") -> int:
    """Run the sidecar in Decider Mode (autonomous voting agent).

    Args:
        args: Parsed command line arguments.
        settings: Loaded settings from config.yaml.

    Returns:
        Exit code (0 for success, non-zero for error).
    """
    agent_name = args.name or "Sidecar"
    logger.info(f"Starting DAHAO {agent_name} in Decider Mode")

    # Load shared law (DAHAO governance data)
    shared_law = _load_shared_law(args)

    # Load or generate Fork
    fork, llm = _load_fork(args, settings, shared_law)
    if fork is None:
        return 1

    # Validate fork against shared law
    if not _validate_fork(args, fork, shared_law, llm, settings):
        return 1

    # Get mnemonic from CLI arg or env var
    mnemonic = args.wallet or settings.mnemonic
    if not mnemonic:
        logger.error(
            "No mnemonic configured. Use --wallet or set LEVIATHAN_MNEMONIC environment variable "
            "with your wallet's 24-word mnemonic."
        )
        return 1

    # Initialize chain client
    try:
        chain_client = ChainClient(settings.chain)
        logger.info(f"Connected to chain at {settings.chain.grpc_url}")
    except Exception as e:
        logger.error(f"Failed to connect to chain: {e}")
        return 1

    # Initialize wallet
    try:
        wallet = WalletManager(mnemonic, settings.chain.address_prefix)
        logger.info(f"Wallet address: {wallet.address}")
    except Exception as e:
        logger.error(f"Failed to initialize wallet: {e}")
        return 1

    # Check wallet balance (fail fast if no gas tokens)
    try:
        wallet.ensure_funded(chain_client)
    except InsufficientFundsError as e:
        logger.error(str(e))
        return 1
    except Exception as e:
        logger.error(f"Failed to check wallet balance: {e}")
        return 1

    # Initialize LLM (if not already done during persona mapping)
    if llm is None:
        llm = _initialize_llm(settings)
        if llm is None:
            return 1

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
        return 1

    logger.info("DAHAO Sidecar stopped")
    return 0


def _load_shared_law(args: "argparse.Namespace") -> SharedLaw | None:
    """Load shared law data from the data directory.

    Args:
        args: Parsed command line arguments.

    Returns:
        SharedLaw instance or None if loading failed.
    """
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
        return shared_law
    except SharedLawLoadError as e:
        logger.warning(f"Failed to load shared law: {e}")
        logger.warning("Continuing without shared law context")
        return None
    except Exception as e:
        logger.warning(f"Error loading shared law: {e}")
        logger.warning("Continuing without shared law context")
        return None


def _load_fork(
    args: "argparse.Namespace",
    settings: "Settings",
    shared_law: SharedLaw | None,
) -> tuple[Fork | None, LLMWrapper | None]:
    """Load Fork from persona or YAML file.

    Args:
        args: Parsed command line arguments.
        settings: Application settings.
        shared_law: SharedLaw instance (required for persona mapping).

    Returns:
        Tuple of (Fork, LLMWrapper) - LLM is returned if initialized during persona mapping.
    """
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
                    logger.error(
                        "Persona mapping requires shared law data. Ensure data/ directory exists."
                    )
                    return None, None

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
            return None, None

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
            logger.error(
                f"Fork file '{args.fork}' not found. Please create it with your voting values."
            )
            return None, None
        except Exception as e:
            logger.error(f"Failed to load fork: {e}")
            return None, None

    return fork, llm


def _validate_fork(
    args: "argparse.Namespace",
    fork: Fork,
    shared_law: SharedLaw | None,
    llm: LLMWrapper | None,
    settings: "Settings",
) -> bool:
    """Validate fork against shared law.

    Args:
        args: Parsed command line arguments.
        fork: Fork to validate.
        shared_law: SharedLaw instance.
        llm: LLMWrapper instance (may be None).
        settings: Application settings.

    Returns:
        True if validation passed or skipped, False if validation failed.
    """
    if not shared_law or args.skip_fork_validation:
        return True

    # Simple validation (if requested) - fast pattern-based check
    if args.simple_validation:
        try:
            fork.validate_against(shared_law)
            logger.info("Fork validated against shared law (simple mode)")
            return True
        except ForkValidationError as e:
            _log_validation_error(e)
            return False

    # LLM-based validation (default, more accurate)
    # Initialize LLM if not already done
    if llm is None:
        llm = _initialize_llm(settings)
        if llm is None:
            return False

    try:
        logger.info("Validating fork with LLM (semantic analysis)...")
        fork.validate_against_with_llm(shared_law, llm)
        logger.info("Fork validated against shared law (LLM mode)")
        return True
    except ForkValidationError as e:
        _log_validation_error(e)
        return False


def _initialize_llm(settings: "Settings") -> LLMWrapper | None:
    """Initialize the LLM wrapper.

    Args:
        settings: Application settings.

    Returns:
        LLMWrapper instance or None if initialization failed.
    """
    try:
        llm = LLMWrapper(settings.llm)
        # Trigger model load now to fail fast
        _ = llm.model
        logger.info("LLM loaded successfully")
        return llm
    except FileNotFoundError as e:
        logger.error(f"LLM model not found: {e}")
        return None
    except Exception as e:
        logger.error(f"Failed to load LLM: {e}")
        return None


def _log_validation_error(e: ForkValidationError):
    """Log fork validation errors.

    Args:
        e: ForkValidationError exception.
    """
    logger.error(f"Fork validation failed: {e}")
    logger.error("Violations:")
    for v in e.violations:
        logger.error(f"  - {v}")
    logger.error(
        "Use --skip-fork-validation to bypass or --simple-validation for pattern-based check"
    )
