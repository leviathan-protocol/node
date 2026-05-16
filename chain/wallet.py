"""Wallet management from mnemonic."""

import logging

from cosmpy.aerial.wallet import LocalWallet

from chain.client import ChainClient

logger = logging.getLogger(__name__)


class InsufficientFundsError(Exception):
    """Raised when wallet has insufficient funds for transactions."""

    pass


class WalletManager:
    """Manages wallet creation and balance checking."""

    def __init__(self, mnemonic: str, prefix: str = "cosmos"):
        if not mnemonic or not mnemonic.strip():
            raise ValueError("Mnemonic cannot be empty")

        self._mnemonic = mnemonic.strip()
        self._prefix = prefix
        self._wallet: LocalWallet | None = None

    @property
    def wallet(self) -> LocalWallet:
        """Lazy-initialize and return the wallet."""
        if self._wallet is None:
            self._wallet = self._create_wallet()
        return self._wallet

    def _create_wallet(self) -> LocalWallet:
        """Create wallet from mnemonic."""
        wallet = LocalWallet.from_mnemonic(self._mnemonic, prefix=self._prefix)
        logger.info(f"Wallet initialized: {wallet.address()}")
        return wallet

    @property
    def address(self) -> str:
        """Return the wallet address."""
        return str(self.wallet.address())

    def ensure_funded(self, chain_client: ChainClient, min_balance: int = 1000):
        """Check that wallet has sufficient funds, raise if not.

        Args:
            chain_client: The chain client to query balance
            min_balance: Minimum required balance in base denom

        Raises:
            InsufficientFundsError: If balance is below minimum
        """
        balance = chain_client.query_balance(self.address)
        logger.info(f"Wallet balance: {balance} {chain_client.config.fee_denom}")

        if balance < min_balance:
            raise InsufficientFundsError(
                f"Wallet {self.address} has {balance} {chain_client.config.fee_denom}. "
                f"Minimum required: {min_balance}. "
                f"Fund it with: leviathan tx bank send alice {self.address} 10000stake --yes"
            )
