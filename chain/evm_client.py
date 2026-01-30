"""EVM Chain Client for Web3.py interactions.

Provides low-level EVM chain operations:
- Connection management
- Balance queries
- Transaction sending and receipt waiting
- Nonce management

Supports any EVM-compatible chain:
- Avalanche C-Chain (Mainnet/Fuji)
- Ethereum (Mainnet/Goerli/Sepolia)
- Polygon, Arbitrum, Optimism, etc.
"""

from __future__ import annotations

import logging
from typing import Any

from eth_account import Account
from eth_account.signers.local import LocalAccount
from web3 import Web3
from web3.exceptions import TransactionNotFound
from web3.types import TxParams, TxReceipt, Wei

logger = logging.getLogger(__name__)


class EVMChainClient:
    """Low-level client for EVM chain interactions.

    Handles:
    - RPC connection
    - Account management
    - Transaction building and sending
    - Receipt waiting

    Example:
        >>> client = EVMChainClient("https://api.avax-test.network/ext/bc/C/rpc")
        >>> print(f"Connected: {client.is_connected}, Chain: {client.chain_id}")
        >>> balance = client.get_balance("0x...")
    """

    def __init__(
        self,
        rpc_url: str,
        private_key: str | bytes | None = None,
        timeout: int = 30,
    ):
        """Initialize EVM client.

        Args:
            rpc_url: HTTP(S) RPC endpoint URL.
            private_key: Optional private key for signing transactions.
                        Can be hex string (with or without 0x) or bytes.
            timeout: Request timeout in seconds.
        """
        self.rpc_url = rpc_url
        self._web3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": timeout}))
        self._account: LocalAccount | None = None

        if private_key:
            self._set_account(private_key)

        logger.info(f"EVMChainClient initialized for {rpc_url}")

    def _set_account(self, private_key: str | bytes):
        """Set the account from a private key.

        Args:
            private_key: Private key as hex string or bytes.
        """
        if isinstance(private_key, str):
            # Handle hex string (with or without 0x prefix)
            if not private_key.startswith("0x"):
                private_key = "0x" + private_key
            self._account = Account.from_key(private_key)
        else:
            self._account = Account.from_key(private_key)

        logger.info(f"Account set: {self._account.address}")

    @property
    def web3(self) -> Web3:
        """Return the Web3 instance."""
        return self._web3

    @property
    def is_connected(self) -> bool:
        """Check if connected to the RPC endpoint."""
        try:
            return self._web3.is_connected()
        except Exception:
            return False

    @property
    def chain_id(self) -> int:
        """Get the chain ID."""
        return self._web3.eth.chain_id

    @property
    def account(self) -> LocalAccount | None:
        """Return the configured account."""
        return self._account

    @property
    def address(self) -> str | None:
        """Return the account address if configured."""
        return self._account.address if self._account else None

    @property
    def block_number(self) -> int:
        """Get the latest block number."""
        return self._web3.eth.block_number

    def get_balance(self, address: str) -> Wei:
        """Get native token balance in wei.

        Args:
            address: Ethereum address.

        Returns:
            Balance in wei (smallest unit).
        """
        return self._web3.eth.get_balance(Web3.to_checksum_address(address))

    def get_balance_ether(self, address: str) -> float:
        """Get native token balance in ether.

        Args:
            address: Ethereum address.

        Returns:
            Balance in ether (AVAX for Avalanche).
        """
        balance_wei = self.get_balance(address)
        return float(Web3.from_wei(balance_wei, "ether"))

    def get_nonce(self, address: str | None = None) -> int:
        """Get the transaction nonce for an address.

        Args:
            address: Ethereum address. Uses configured account if None.

        Returns:
            Current nonce (number of transactions sent).
        """
        if address is None:
            if self._account is None:
                raise ValueError("No address specified and no account configured")
            address = self._account.address

        return self._web3.eth.get_transaction_count(Web3.to_checksum_address(address))

    def get_gas_price(self) -> Wei:
        """Get current gas price in wei."""
        return self._web3.eth.gas_price

    def estimate_gas(self, tx: TxParams) -> int:
        """Estimate gas for a transaction.

        Args:
            tx: Transaction parameters.

        Returns:
            Estimated gas units.
        """
        return self._web3.eth.estimate_gas(tx)

    def build_transaction(
        self,
        to: str,
        value: int = 0,
        data: bytes = b"",
        gas: int | None = None,
        gas_price: int | None = None,
        nonce: int | None = None,
    ) -> TxParams:
        """Build a transaction dictionary.

        Args:
            to: Recipient address.
            value: Value to send in wei.
            data: Transaction data (for contract calls).
            gas: Gas limit (estimated if None).
            gas_price: Gas price in wei (current price if None).
            nonce: Transaction nonce (current nonce if None).

        Returns:
            Transaction parameters dictionary.
        """
        if self._account is None:
            raise ValueError("No account configured for building transactions")

        tx: TxParams = {
            "from": self._account.address,
            "to": Web3.to_checksum_address(to),
            "value": value,
            "chainId": self.chain_id,
        }

        if data:
            tx["data"] = data

        if nonce is not None:
            tx["nonce"] = nonce
        else:
            tx["nonce"] = self.get_nonce()

        if gas_price is not None:
            tx["gasPrice"] = gas_price
        else:
            tx["gasPrice"] = self.get_gas_price()

        if gas is not None:
            tx["gas"] = gas
        else:
            tx["gas"] = self.estimate_gas(tx)

        return tx

    def sign_transaction(self, tx: TxParams) -> bytes:
        """Sign a transaction.

        Args:
            tx: Transaction parameters.

        Returns:
            Signed transaction bytes.
        """
        if self._account is None:
            raise ValueError("No account configured for signing")

        signed = self._account.sign_transaction(tx)
        return signed.raw_transaction

    def send_transaction(self, tx: TxParams) -> str:
        """Sign and send a transaction.

        Args:
            tx: Transaction parameters.

        Returns:
            Transaction hash as hex string.
        """
        signed_tx = self.sign_transaction(tx)
        tx_hash = self._web3.eth.send_raw_transaction(signed_tx)
        return tx_hash.hex()

    def send_raw_transaction(self, signed_tx: bytes) -> str:
        """Send a pre-signed transaction.

        Args:
            signed_tx: Signed transaction bytes.

        Returns:
            Transaction hash as hex string.
        """
        tx_hash = self._web3.eth.send_raw_transaction(signed_tx)
        return tx_hash.hex()

    def wait_for_receipt(
        self,
        tx_hash: str,
        timeout: int = 120,
        poll_interval: float = 1.0,
    ) -> TxReceipt:
        """Wait for a transaction receipt.

        Args:
            tx_hash: Transaction hash.
            timeout: Maximum wait time in seconds.
            poll_interval: Polling interval in seconds.

        Returns:
            Transaction receipt.

        Raises:
            TimeoutError: If receipt not received within timeout.
        """
        return self._web3.eth.wait_for_transaction_receipt(
            tx_hash,
            timeout=timeout,
            poll_latency=poll_interval,
        )

    def get_transaction(self, tx_hash: str) -> dict | None:
        """Get transaction by hash.

        Args:
            tx_hash: Transaction hash.

        Returns:
            Transaction data or None if not found.
        """
        try:
            return dict(self._web3.eth.get_transaction(tx_hash))
        except TransactionNotFound:
            return None

    def get_receipt(self, tx_hash: str) -> TxReceipt | None:
        """Get transaction receipt by hash.

        Args:
            tx_hash: Transaction hash.

        Returns:
            Transaction receipt or None if not found/pending.
        """
        try:
            return self._web3.eth.get_transaction_receipt(tx_hash)
        except TransactionNotFound:
            return None

    def call_contract(
        self,
        contract_address: str,
        abi: list[dict],
        function_name: str,
        *args,
        **kwargs,
    ) -> Any:
        """Call a contract function (read-only).

        Args:
            contract_address: Contract address.
            abi: Contract ABI.
            function_name: Function to call.
            *args: Function arguments.

        Returns:
            Function return value.
        """
        contract = self._web3.eth.contract(
            address=Web3.to_checksum_address(contract_address),
            abi=abi,
        )
        function = getattr(contract.functions, function_name)
        return function(*args).call(**kwargs)

    def execute_contract(
        self,
        contract_address: str,
        abi: list[dict],
        function_name: str,
        *args,
        value: int = 0,
        gas: int | None = None,
    ) -> str:
        """Execute a contract function (state-changing).

        Args:
            contract_address: Contract address.
            abi: Contract ABI.
            function_name: Function to call.
            *args: Function arguments.
            value: ETH/AVAX to send with transaction.
            gas: Gas limit (estimated if None).

        Returns:
            Transaction hash.
        """
        if self._account is None:
            raise ValueError("No account configured for contract execution")

        contract = self._web3.eth.contract(
            address=Web3.to_checksum_address(contract_address),
            abi=abi,
        )
        function = getattr(contract.functions, function_name)

        tx = function(*args).build_transaction(
            {
                "from": self._account.address,
                "value": value,
                "nonce": self.get_nonce(),
                "gasPrice": self.get_gas_price(),
                "chainId": self.chain_id,
            }
        )

        if gas:
            tx["gas"] = gas
        else:
            tx["gas"] = self.estimate_gas(tx)

        return self.send_transaction(tx)


# Convenience function for quick testing
def test_connection(rpc_url: str) -> dict:
    """Test connection to an EVM RPC endpoint.

    Args:
        rpc_url: RPC endpoint URL.

    Returns:
        Connection info dict.
    """
    client = EVMChainClient(rpc_url)
    return {
        "connected": client.is_connected,
        "chain_id": client.chain_id if client.is_connected else None,
        "block_number": client.block_number if client.is_connected else None,
        "rpc_url": rpc_url,
    }


if __name__ == "__main__":
    # Quick test for Fuji testnet
    import sys

    rpc_url = sys.argv[1] if len(sys.argv) > 1 else "https://api.avax-test.network/ext/bc/C/rpc"

    print(f"Testing connection to: {rpc_url}")
    info = test_connection(rpc_url)

    print(f"  Connected: {info['connected']}")
    print(f"  Chain ID: {info['chain_id']}")
    print(f"  Block: {info['block_number']}")

    if info["connected"]:
        print("\n✓ Connection successful!")
    else:
        print("\n✗ Connection failed!")
        sys.exit(1)
