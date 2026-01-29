"""Authz module for executing votes on behalf of users (Gasless Voting).

Uses Cosmos SDK's authz module to allow the node to submit votes
on behalf of users who have granted MsgVote authorization.

Flow:
1. User grants authz to node: MsgGrant(granter=user, grantee=node, MsgVote)
2. User signs voting intent and sends to node
3. Node validates and creates: MsgExec(grantee=node, msgs=[MsgVote(voter=user)])
4. Node signs and broadcasts (node pays gas)
5. Vote is recorded on chain as if user voted directly
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from cosmpy.aerial.tx import SigningCfg, Transaction, TxFee
from cosmpy.aerial.tx_helpers import SubmittedTx
from cosmpy.protos.cosmos.authz.v1beta1.tx_pb2 import MsgExec
from cosmpy.protos.cosmos.gov.v1beta1.gov_pb2 import (
    VOTE_OPTION_ABSTAIN,
    VOTE_OPTION_NO,
    VOTE_OPTION_NO_WITH_VETO,
    VOTE_OPTION_YES,
)
from cosmpy.protos.cosmos.gov.v1beta1.tx_pb2 import MsgVote
from google.protobuf.any_pb2 import Any as ProtoAny

if TYPE_CHECKING:
    from cosmpy.aerial.client import LedgerClient
    from cosmpy.aerial.wallet import LocalWallet

    from chain.client import ChainClient
    from config.settings import ChainConfig

logger = logging.getLogger(__name__)


# Map string vote options to Cosmos vote option constants
VOTE_OPTION_MAP = {
    "YES": VOTE_OPTION_YES,
    "NO": VOTE_OPTION_NO,
    "ABSTAIN": VOTE_OPTION_ABSTAIN,
    "NO_WITH_VETO": VOTE_OPTION_NO_WITH_VETO,
    # Also support lowercase
    "yes": VOTE_OPTION_YES,
    "no": VOTE_OPTION_NO,
    "abstain": VOTE_OPTION_ABSTAIN,
    "no_with_veto": VOTE_OPTION_NO_WITH_VETO,
}


class AuthzVoteError(Exception):
    """Error during authz vote execution."""

    def __init__(self, message: str, reason: str = "unknown"):
        super().__init__(message)
        self.reason = reason


def vote_on_behalf(
    ledger_client: "LedgerClient",
    node_wallet: "LocalWallet",
    voter_address: str,
    proposal_id: int,
    vote_option: str,
    chain_id: str,
    gas_limit: int = 200000,
    fee_amount: int = 1000,
    fee_denom: str = "stake",
) -> str:
    """Execute a vote on behalf of a user using authz MsgExec.

    Creates MsgVote with voter=user_address, wraps in MsgExec with
    grantee=node_address, signs with node wallet, and broadcasts.

    Args:
        ledger_client: CosmPy LedgerClient for chain interaction.
        node_wallet: Node's wallet for signing (pays gas).
        voter_address: User's Cosmos address (who granted authz).
        proposal_id: ID of the proposal to vote on.
        vote_option: Vote choice (YES/NO/ABSTAIN/NO_WITH_VETO).
        chain_id: Chain identifier.
        gas_limit: Gas limit for transaction.
        fee_amount: Fee amount in smallest denomination.
        fee_denom: Fee denomination (e.g., "stake").

    Returns:
        Transaction hash as string.

    Raises:
        AuthzVoteError: If vote execution fails.
    """
    logger.info(
        f"Voting on behalf: voter={voter_address}, "
        f"proposal={proposal_id}, vote={vote_option}"
    )

    # Validate vote option
    if vote_option.upper() not in VOTE_OPTION_MAP:
        raise AuthzVoteError(
            f"Invalid vote option: {vote_option}",
            reason="invalid_vote_option",
        )

    cosmos_vote_option = VOTE_OPTION_MAP[vote_option.upper()]

    try:
        # Create the inner MsgVote (voter is the user who granted authz)
        msg_vote = MsgVote(
            proposal_id=proposal_id,
            voter=voter_address,
            option=cosmos_vote_option,
        )

        # Wrap MsgVote in protobuf Any type
        vote_any = ProtoAny()
        vote_any.Pack(msg_vote)

        # Create MsgExec (grantee is the node executing on behalf)
        node_address = str(node_wallet.address())
        msg_exec = MsgExec(
            grantee=node_address,
            msgs=[vote_any],
        )

        logger.debug(
            f"Created MsgExec: grantee={node_address}, "
            f"inner_msg=MsgVote(voter={voter_address}, option={vote_option})"
        )

        # Build transaction
        tx = Transaction()
        tx.add_message(msg_exec)

        # Query account for sequence and account number
        account = ledger_client.query_account(node_wallet.address())

        # Create fee
        fee = TxFee(
            amount=f"{fee_amount}{fee_denom}",
            gas_limit=gas_limit,
        )

        # Sign and complete transaction
        # Transaction lifecycle: Draft → seal() → sign() → complete() → broadcast
        tx.seal(
            signing_cfgs=SigningCfg.direct(node_wallet.public_key(), account.sequence),
            fee=fee,
        )
        tx.sign(node_wallet.signer(), chain_id, account.number)
        tx.complete()

        # Broadcast and wait for inclusion
        submitted_tx = ledger_client.broadcast_tx(tx)
        submitted_tx.wait_to_complete()

        tx_hash = submitted_tx.tx_hash
        logger.info(f"Vote on behalf submitted successfully. TX hash: {tx_hash}")

        return tx_hash

    except AuthzVoteError:
        raise
    except Exception as e:
        logger.error(f"Failed to execute vote on behalf: {e}")
        raise AuthzVoteError(
            f"Vote execution failed: {e}",
            reason="execution_failed",
        )


def vote_on_behalf_with_client(
    chain_client: "ChainClient",
    config: "ChainConfig",
    node_wallet: "LocalWallet",
    voter_address: str,
    proposal_id: int,
    vote_option: str,
) -> str:
    """Convenience wrapper using ChainClient and ChainConfig.

    Args:
        chain_client: ChainClient instance.
        config: Chain configuration.
        node_wallet: Node's wallet.
        voter_address: User's address.
        proposal_id: Proposal ID.
        vote_option: Vote choice.

    Returns:
        Transaction hash.
    """
    return vote_on_behalf(
        ledger_client=chain_client.client,
        node_wallet=node_wallet,
        voter_address=voter_address,
        proposal_id=proposal_id,
        vote_option=vote_option,
        chain_id=config.chain_id,
        gas_limit=config.gas_limit,
        fee_amount=config.fee_amount,
        fee_denom=config.fee_denom,
    )


# Mock function for testing without chain
def vote_on_behalf_mock(
    voter_address: str,
    proposal_id: int,
    vote_option: str,
    should_succeed: bool = True,
) -> str:
    """Mock vote_on_behalf for testing without chain connection.

    Args:
        voter_address: User's address.
        proposal_id: Proposal ID.
        vote_option: Vote choice.
        should_succeed: Whether the mock should succeed.

    Returns:
        Mock transaction hash.

    Raises:
        AuthzVoteError: If should_succeed is False.
    """
    logger.info(
        f"(Mock) Voting on behalf: voter={voter_address}, "
        f"proposal={proposal_id}, vote={vote_option}"
    )

    if not should_succeed:
        raise AuthzVoteError("Mock vote failed", reason="mock_failure")

    # Generate mock tx hash
    import hashlib
    mock_data = f"{voter_address}:{proposal_id}:{vote_option}"
    tx_hash = hashlib.sha256(mock_data.encode()).hexdigest().upper()

    logger.info(f"(Mock) Vote submitted. TX hash: {tx_hash}")
    return tx_hash


if __name__ == "__main__":
    # Quick test with mock
    import sys

    logging.basicConfig(level=logging.DEBUG)

    print("=== Testing mock vote_on_behalf ===")

    # Successful vote
    tx_hash = vote_on_behalf_mock(
        voter_address="cosmos1alice123",
        proposal_id=42,
        vote_option="NO",
        should_succeed=True,
    )
    print(f"Mock vote success: {tx_hash[:16]}...")

    # Failed vote
    try:
        vote_on_behalf_mock(
            voter_address="cosmos1bob456",
            proposal_id=42,
            vote_option="YES",
            should_succeed=False,
        )
    except AuthzVoteError as e:
        print(f"Mock vote failed as expected: {e.reason}")

    sys.exit(0)
