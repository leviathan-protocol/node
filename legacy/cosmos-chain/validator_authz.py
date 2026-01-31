"""Cosmos Authz grant validation.

Verifies that users have granted the node permission to vote on their behalf
using Cosmos SDK's authz module (MsgGrant with MsgVote authorization).

Grant structure on chain:
- Granter: User's address (cosmos1alice...)
- Grantee: Node's address (cosmos1node...)
- Authorization: GenericAuthorization for /cosmos.gov.v1beta1.MsgVote
- Expiration: When the grant expires
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from chain.client import ChainClient

logger = logging.getLogger(__name__)


class AuthzStatus(Enum):
    """Status of an Authz grant."""

    VALID = "valid"
    NOT_FOUND = "not_found"
    EXPIRED = "expired"
    WRONG_MSG_TYPE = "wrong_msg_type"
    REVOKED = "revoked"
    ERROR = "error"


@dataclass
class AuthzResult:
    """Result of an Authz grant check."""

    status: AuthzStatus
    granter: str
    grantee: str
    expires_at: datetime | None = None
    msg_type: str | None = None
    error_message: str | None = None

    @property
    def is_valid(self) -> bool:
        """Check if the grant is valid for voting."""
        return self.status == AuthzStatus.VALID

    def to_dict(self) -> dict:
        """Convert to dictionary for API responses."""
        return {
            "status": self.status.value,
            "granter": self.granter,
            "grantee": self.grantee,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "msg_type": self.msg_type,
            "error_message": self.error_message,
        }


# Message type URLs for voting authorization
VOTE_MSG_TYPES = [
    "/cosmos.gov.v1beta1.MsgVote",  # v1beta1 governance
    "/cosmos.gov.v1.MsgVote",  # v1 governance
]


def check_authz_grant(
    chain_client: "ChainClient",
    granter: str,
    grantee: str,
) -> AuthzResult:
    """Check if an Authz grant exists for voting.

    Queries the chain's authz module to verify that `granter` has
    authorized `grantee` to submit MsgVote on their behalf.

    Args:
        chain_client: ChainClient instance for gRPC queries.
        granter: User's Cosmos address (the one who granted).
        grantee: Node's Cosmos address (the one authorized to act).

    Returns:
        AuthzResult with grant status and details.
    """
    logger.info(f"Checking authz grant: {granter} -> {grantee}")

    try:
        # Query grants from chain
        grants = _query_grants(chain_client, granter, grantee)

        if not grants:
            logger.info(f"No authz grants found for {granter} -> {grantee}")
            return AuthzResult(
                status=AuthzStatus.NOT_FOUND,
                granter=granter,
                grantee=grantee,
                error_message="No authorization grant found",
            )

        # Look for MsgVote authorization
        for grant in grants:
            msg_type = grant.get("msg_type_url") or grant.get("authorization", {}).get(
                "@type", ""
            )

            # Check if this is a vote authorization
            is_vote_grant = False
            for vote_type in VOTE_MSG_TYPES:
                if vote_type in msg_type or vote_type in str(grant):
                    is_vote_grant = True
                    break

            # Also check GenericAuthorization with msg field
            authorization = grant.get("authorization", {})
            if authorization.get("@type", "").endswith("GenericAuthorization"):
                msg = authorization.get("msg", "")
                for vote_type in VOTE_MSG_TYPES:
                    if vote_type in msg:
                        is_vote_grant = True
                        msg_type = msg
                        break

            if not is_vote_grant:
                continue

            # Check expiration
            expiration = grant.get("expiration")
            expires_at = None
            if expiration:
                try:
                    # Parse ISO format or timestamp
                    if isinstance(expiration, str):
                        expires_at = datetime.fromisoformat(
                            expiration.replace("Z", "+00:00")
                        )
                    elif isinstance(expiration, (int, float)):
                        expires_at = datetime.fromtimestamp(expiration, tz=timezone.utc)
                except Exception as e:
                    logger.warning(f"Failed to parse expiration: {e}")

            # Check if expired
            if expires_at and expires_at < datetime.now(timezone.utc):
                logger.info(f"Grant expired at {expires_at}")
                return AuthzResult(
                    status=AuthzStatus.EXPIRED,
                    granter=granter,
                    grantee=grantee,
                    expires_at=expires_at,
                    msg_type=msg_type,
                    error_message="Authorization grant has expired",
                )

            # Valid grant found
            logger.info(f"Valid authz grant found: {msg_type}, expires: {expires_at}")
            return AuthzResult(
                status=AuthzStatus.VALID,
                granter=granter,
                grantee=grantee,
                expires_at=expires_at,
                msg_type=msg_type,
            )

        # No MsgVote grant found
        logger.info(f"No MsgVote authorization in grants for {granter}")
        return AuthzResult(
            status=AuthzStatus.WRONG_MSG_TYPE,
            granter=granter,
            grantee=grantee,
            error_message="Grant exists but not for MsgVote",
        )

    except Exception as e:
        logger.error(f"Error checking authz grant: {e}")
        return AuthzResult(
            status=AuthzStatus.ERROR,
            granter=granter,
            grantee=grantee,
            error_message=str(e),
        )


def _query_grants(
    chain_client: "ChainClient",
    granter: str,
    grantee: str,
) -> list[dict]:
    """Query authz grants from chain via gRPC.

    Args:
        chain_client: ChainClient instance.
        granter: Granter address.
        grantee: Grantee address.

    Returns:
        List of grant dictionaries.
    """
    try:
        # Import protobuf types
        from cosmpy.protos.cosmos.authz.v1beta1.query_pb2 import QueryGrantsRequest
        from cosmpy.protos.cosmos.authz.v1beta1.query_pb2_grpc import QueryStub

        # Create authz query client
        authz_client = QueryStub(chain_client.channel)

        # Query grants
        request = QueryGrantsRequest(
            granter=granter,
            grantee=grantee,
        )

        response = authz_client.Grants(request)

        # Convert protobuf to dicts
        grants = []
        for grant in response.grants:
            grant_dict = {
                "authorization": {},
                "expiration": None,
            }

            # Extract authorization type and content
            if grant.authorization:
                auth = grant.authorization
                grant_dict["authorization"] = {
                    "@type": auth.type_url,
                }
                # Try to extract msg field from GenericAuthorization
                if "GenericAuthorization" in auth.type_url:
                    try:
                        from cosmpy.protos.cosmos.authz.v1beta1.authz_pb2 import (
                            GenericAuthorization,
                        )

                        generic = GenericAuthorization()
                        if auth.Unpack(generic):
                            grant_dict["authorization"]["msg"] = generic.msg
                    except Exception:
                        pass

            # Extract expiration
            if grant.expiration:
                grant_dict["expiration"] = grant.expiration.ToDatetime().isoformat()

            grants.append(grant_dict)

        return grants

    except ImportError as e:
        logger.warning(f"Protobuf imports not available: {e}")
        return []
    except Exception as e:
        logger.error(f"gRPC query failed: {e}")
        raise


def check_authz_grant_mock(
    granter: str,
    grantee: str,
    mock_grants: dict[str, dict] | None = None,
) -> AuthzResult:
    """Mock version of check_authz_grant for testing without chain.

    Args:
        granter: User's address.
        grantee: Node's address.
        mock_grants: Dict mapping granter addresses to grant info.

    Returns:
        AuthzResult based on mock data.
    """
    if mock_grants is None:
        # Default: always return valid for testing
        return AuthzResult(
            status=AuthzStatus.VALID,
            granter=granter,
            grantee=grantee,
            expires_at=datetime.now(timezone.utc).replace(year=2027),
            msg_type="/cosmos.gov.v1beta1.MsgVote",
        )

    grant_info = mock_grants.get(granter)
    if grant_info is None:
        return AuthzResult(
            status=AuthzStatus.NOT_FOUND,
            granter=granter,
            grantee=grantee,
            error_message="No authorization grant found",
        )

    if grant_info.get("grantee") != grantee:
        return AuthzResult(
            status=AuthzStatus.NOT_FOUND,
            granter=granter,
            grantee=grantee,
            error_message="Grant is for different grantee",
        )

    expires_at = grant_info.get("expires_at")
    if expires_at and expires_at < datetime.now(timezone.utc):
        return AuthzResult(
            status=AuthzStatus.EXPIRED,
            granter=granter,
            grantee=grantee,
            expires_at=expires_at,
            error_message="Authorization grant has expired",
        )

    return AuthzResult(
        status=AuthzStatus.VALID,
        granter=granter,
        grantee=grantee,
        expires_at=expires_at,
        msg_type=grant_info.get("msg_type", "/cosmos.gov.v1beta1.MsgVote"),
    )


if __name__ == "__main__":
    # Quick test with mock
    import sys

    logging.basicConfig(level=logging.DEBUG)

    # Test mock grant check
    print("=== Testing mock authz check ===")

    # Valid grant
    result = check_authz_grant_mock("cosmos1alice", "cosmos1node")
    print(f"Default mock: {result.status.value} - valid={result.is_valid}")

    # With custom mock data
    mock_data = {
        "cosmos1bob": {
            "grantee": "cosmos1node",
            "expires_at": datetime(2027, 1, 1, tzinfo=timezone.utc),
            "msg_type": "/cosmos.gov.v1beta1.MsgVote",
        },
        "cosmos1expired": {
            "grantee": "cosmos1node",
            "expires_at": datetime(2020, 1, 1, tzinfo=timezone.utc),
        },
    }

    result = check_authz_grant_mock("cosmos1bob", "cosmos1node", mock_data)
    print(f"Bob's grant: {result.status.value} - valid={result.is_valid}")

    result = check_authz_grant_mock("cosmos1expired", "cosmos1node", mock_data)
    print(f"Expired grant: {result.status.value} - valid={result.is_valid}")

    result = check_authz_grant_mock("cosmos1unknown", "cosmos1node", mock_data)
    print(f"Unknown granter: {result.status.value} - valid={result.is_valid}")

    sys.exit(0)
