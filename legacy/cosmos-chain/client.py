"""LedgerClient wrapper for Cosmos chain interaction."""

import logging

import grpc
from cosmpy.aerial.client import LedgerClient, NetworkConfig
from cosmpy.aerial.urls import parse_url

from config.settings import ChainConfig

logger = logging.getLogger(__name__)


class ChainClient:
    """Wrapper around CosmPy LedgerClient for chain interactions."""

    def __init__(self, config: ChainConfig):
        self.config = config
        self._client: LedgerClient | None = None
        self._channel: grpc.Channel | None = None

    @property
    def client(self) -> LedgerClient:
        """Lazy-initialize and return the LedgerClient."""
        if self._client is None:
            self._client = self._create_client()
        return self._client

    @property
    def channel(self) -> grpc.Channel:
        """Return the gRPC channel for direct stub access."""
        # Access the client to ensure it's initialized, which sets up _channel
        _ = self.client
        return self._channel

    def _create_client(self) -> LedgerClient:
        """Create a new LedgerClient with the configured settings."""
        logger.info(f"Connecting to chain {self.config.chain_id} at {self.config.grpc_url}")

        network_config = NetworkConfig(
            chain_id=self.config.chain_id,
            url=self.config.grpc_url,
            fee_minimum_gas_price=1,
            fee_denomination=self.config.fee_denom,
            staking_denomination=self.config.fee_denom,
        )

        client = LedgerClient(network_config)

        # Create gRPC channel for direct stub access (e.g., governance queries)
        parsed = parse_url(self.config.grpc_url)
        self._channel = grpc.insecure_channel(parsed.host_and_port)

        return client

    def query_balance(self, address: str, denom: str | None = None) -> int:
        """Query the balance of an address."""
        denom = denom or self.config.fee_denom
        return self.client.query_bank_balance(address, denom)

    def close(self):
        """Close the client connection."""
        self._client = None
