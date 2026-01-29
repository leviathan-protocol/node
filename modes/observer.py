"""Observer Mode - API gateway for Gasless Voting.

This mode runs a FastAPI server that:
1. Accepts signed voting intents from mobile clients
2. Validates signatures, authz grants, and reasoning consistency
3. Executes votes on behalf of users using Cosmos Authz (MsgExec)
4. Returns transaction hashes or rejection reasons

Users sign intents on their mobile devices; the node pays gas fees.
"""

from __future__ import annotations

import asyncio
import logging
import signal
from pathlib import Path
from typing import TYPE_CHECKING

from api.server import app_state, create_app
from brain.llm import LLMWrapper
from chain.client import ChainClient
from chain.wallet import WalletManager
from data import SharedLaw, SharedLawLoadError

if TYPE_CHECKING:
    import argparse

    from config.settings import Settings

logger = logging.getLogger(__name__)


def run_observer_mode(args: "argparse.Namespace", settings: "Settings") -> int:
    """Run the sidecar in Observer Mode (API gateway for mobile clients).

    Args:
        args: Parsed command line arguments.
        settings: Loaded settings from config.yaml.

    Returns:
        Exit code (0 for success, non-zero for error).
    """
    logger.info("Starting DAHAO Sidecar in Observer Mode")

    # Load shared law (needed for semantic validation)
    shared_law = _load_shared_law(args)

    # Initialize chain client (optional in observer mode - for authz verification)
    chain_client = _initialize_chain_client(settings)

    # Initialize wallet (for paying gas on behalf of users)
    node_wallet = None
    mnemonic = args.wallet or settings.mnemonic
    if mnemonic:
        node_wallet = _initialize_wallet(mnemonic, settings)
        if node_wallet:
            logger.info(f"Node wallet: {node_wallet.address}")
    else:
        logger.warning(
            "No wallet mnemonic configured. Vote execution will use mock mode. "
            "Set LEVIATHAN_MNEMONIC or use --wallet for production."
        )

    # Initialize LLM (for semantic validation)
    llm = _initialize_llm(settings)

    # Store shared resources in app state for route handlers
    app_state.chain_client = chain_client
    app_state.chain_config = settings.chain
    app_state.llm = llm
    app_state.shared_law = shared_law
    app_state.node_wallet = node_wallet
    app_state.node_address = node_wallet.address if node_wallet else "cosmos1node..."
    app_state.chain_id = settings.chain.chain_id
    app_state.node_url = f"http://{args.host}:{args.port}"

    # Get CORS origins from settings or use defaults
    cors_origins = getattr(settings, "cors_origins", None)

    # Create FastAPI app
    app = create_app(config=settings.api if hasattr(settings, "api") else None, cors_origins=cors_origins)

    # Get host and port from args
    host = args.host
    port = args.port

    logger.info(f"Starting Observer Mode API server on {host}:{port}")
    logger.info(f"  Chain: {settings.chain.chain_id}")
    logger.info(f"  Node wallet: {app_state.node_address}")
    logger.info(f"  Shared law: {'loaded' if shared_law else 'not loaded'}")
    logger.info(f"  LLM: {'loaded' if llm else 'not loaded (heuristic validation only)'}")

    # Run the server
    try:
        import uvicorn

        # Create shutdown event
        shutdown_event = asyncio.Event()

        # Set up signal handlers
        def signal_handler(sig, frame):
            logger.info(f"Received signal {sig}, initiating graceful shutdown...")
            shutdown_event.set()

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        # Run uvicorn
        config = uvicorn.Config(
            app,
            host=host,
            port=port,
            log_level="info" if args.log_level == "INFO" else args.log_level.lower(),
            access_log=True,
        )
        server = uvicorn.Server(config)

        # Run the server
        asyncio.run(server.serve())

    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.error(f"Observer mode crashed: {e}", exc_info=True)
        return 1

    logger.info("DAHAO Sidecar Observer Mode stopped")
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
        return shared_law
    except SharedLawLoadError as e:
        logger.warning(f"Failed to load shared law: {e}")
        logger.warning("Semantic validation will use heuristic mode only")
        return None
    except Exception as e:
        logger.warning(f"Error loading shared law: {e}")
        logger.warning("Semantic validation will use heuristic mode only")
        return None


def _initialize_chain_client(settings: "Settings") -> ChainClient | None:
    """Initialize chain client for authz verification.

    Args:
        settings: Application settings.

    Returns:
        ChainClient instance or None if initialization failed.
    """
    try:
        chain_client = ChainClient(settings.chain)
        logger.info(f"Connected to chain at {settings.chain.grpc_url}")
        return chain_client
    except Exception as e:
        logger.warning(f"Failed to connect to chain: {e}")
        logger.warning("Authz verification will use mock mode")
        return None


def _initialize_wallet(mnemonic: str, settings: "Settings") -> WalletManager | None:
    """Initialize node wallet for paying gas fees.

    Args:
        mnemonic: Wallet mnemonic (24 words).
        settings: Application settings.

    Returns:
        WalletManager instance or None if initialization failed.
    """
    try:
        wallet = WalletManager(mnemonic, settings.chain.address_prefix)
        return wallet
    except Exception as e:
        logger.warning(f"Failed to initialize wallet: {e}")
        logger.warning("Vote execution will use mock mode")
        return None


def _initialize_llm(settings: "Settings") -> LLMWrapper | None:
    """Initialize LLM for semantic validation.

    Args:
        settings: Application settings.

    Returns:
        LLMWrapper instance or None if initialization failed.
    """
    try:
        llm = LLMWrapper(settings.llm)
        # Trigger model load to verify availability
        _ = llm.model
        logger.info(f"LLM loaded: {settings.llm.model_name}")
        return llm
    except Exception as e:
        logger.warning(f"Failed to load LLM: {e}")
        logger.warning("Semantic validation will use heuristic mode only")
        return None
