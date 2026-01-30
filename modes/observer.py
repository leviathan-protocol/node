"""Observer Mode - API gateway for Gasless Voting.

This mode runs a FastAPI server that:
1. Accepts signed voting intents from mobile clients
2. Validates signatures, authorization, and reasoning consistency
3. Executes votes on behalf of users
4. Returns transaction hashes or rejection reasons

Supports both chain types:
- Cosmos: Uses Authz (MsgExec) for delegated voting
- EVM: Uses EIP-2771 meta-transactions via Forwarder contract

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
from chain.adapter import ChainAdapter, ChainType, create_chain_adapter
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
    chain_type = settings.chain.type
    logger.info(f"Starting DAHAO Sidecar in Observer Mode ({chain_type.upper()} chain)")

    # Load shared law (needed for semantic validation)
    shared_law = _load_shared_law(args)

    # Initialize chain adapter based on chain type
    chain_adapter = _initialize_chain_adapter(settings)

    # Initialize wallet (for Cosmos mode - paying gas on behalf of users)
    node_wallet = None
    node_address = None

    if chain_type == "cosmos":
        mnemonic = args.wallet or settings.mnemonic
        if mnemonic:
            node_wallet = _initialize_wallet(mnemonic, settings)
            if node_wallet:
                node_address = node_wallet.address
                logger.info(f"Node wallet (Cosmos): {node_address}")
        else:
            logger.warning(
                "No wallet mnemonic configured for Cosmos. "
                "Set LEVIATHAN_MNEMONIC or use --wallet for production."
            )
            node_address = "cosmos1node..."
    elif chain_type == "evm":
        # For EVM, the relayer wallet is loaded from RELAYER_PRIVATE_KEY
        # when the adapter initializes
        if chain_adapter and chain_adapter.is_connected:
            try:
                node_address = chain_adapter.client.account.address
                logger.info(f"Relayer wallet (EVM): {node_address}")
            except Exception:
                logger.warning(
                    "No RELAYER_PRIVATE_KEY set. "
                    "Gasless voting will not work without relayer wallet."
                )
                node_address = "0x..."

    # Initialize LLM (for semantic validation)
    llm = _initialize_llm(settings)

    # Store shared resources in app state for route handlers
    app_state.chain_adapter = chain_adapter
    app_state.chain_client = None  # Legacy - use chain_adapter instead
    app_state.chain_config = settings.chain
    app_state.llm = llm
    app_state.shared_law = shared_law
    app_state.node_wallet = node_wallet
    app_state.node_address = node_address
    app_state.chain_id = settings.chain.chain_id
    app_state.chain_type = chain_type
    app_state.node_url = f"http://{args.host}:{args.port}"

    # Get CORS origins from settings or use defaults
    cors_origins = getattr(settings, "cors_origins", None)

    # Create FastAPI app
    app = create_app(
        config=settings.api if hasattr(settings, "api") else None,
        cors_origins=cors_origins,
    )

    # Get host and port from args
    host = args.host
    port = args.port

    logger.info(f"Starting Observer Mode API server on {host}:{port}")
    logger.info(f"  Chain Type: {chain_type.upper()}")
    logger.info(f"  Chain ID: {settings.chain.chain_id}")
    logger.info(f"  Node Address: {node_address}")

    if chain_type == "evm":
        logger.info(f"  Governor: {settings.chain.governor_address or 'Not configured'}")
        logger.info(f"  Token: {settings.chain.token_address or 'Not configured'}")
        logger.info(f"  Forwarder: {settings.chain.forwarder_address or 'Not configured'}")
    else:
        logger.info(f"  gRPC: {settings.chain.grpc_url}")

    logger.info(f"  Shared Law: {'loaded' if shared_law else 'not loaded'}")
    logger.info(f"  LLM: {'loaded' if llm else 'heuristic validation only'}")

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
    finally:
        # Clean up chain adapter
        if chain_adapter:
            chain_adapter.close()

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


def _initialize_chain_adapter(settings: "Settings") -> ChainAdapter | None:
    """Initialize chain adapter based on configuration.

    Args:
        settings: Application settings.

    Returns:
        ChainAdapter instance or None if initialization failed.
    """
    try:
        adapter = create_chain_adapter(settings.chain)

        # Verify connection
        if adapter.is_connected:
            logger.info(
                f"Connected to {adapter.chain_type.value.upper()} chain "
                f"(Chain ID: {adapter.chain_id})"
            )
            return adapter
        else:
            logger.warning("Chain adapter created but not connected")
            return adapter

    except Exception as e:
        logger.warning(f"Failed to initialize chain adapter: {e}")
        logger.warning("Vote execution will use mock mode")
        return None


def _initialize_wallet(mnemonic: str, settings: "Settings") -> WalletManager | None:
    """Initialize node wallet for paying gas fees (Cosmos only).

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
