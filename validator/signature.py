"""Intent signature verification using ECDSA secp256k1.

Mobile clients sign voting intents with their private key.
This module verifies those signatures before processing votes.

Signature process (mobile side):
1. Create canonical JSON (sorted keys, no spaces)
2. SHA256 hash the canonical JSON
3. Sign the hash with secp256k1 private key
4. Base64 encode signature and send to node

Verification process (node side):
1. Recreate canonical JSON from payload
2. SHA256 hash the canonical JSON
3. Decode base64 signature and public key
4. Verify ECDSA signature using secp256k1
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
from typing import Any

from ecdsa import SECP256k1, BadSignatureError, VerifyingKey
from ecdsa.util import sigdecode_der

logger = logging.getLogger(__name__)


class SignatureVerificationError(Exception):
    """Raised when signature verification fails."""

    def __init__(self, message: str, reason: str = "unknown"):
        super().__init__(message)
        self.reason = reason


def create_canonical_json(payload: dict[str, Any]) -> str:
    """Create canonical JSON from a payload dictionary.

    Canonical JSON has:
    - Keys sorted alphabetically (recursively)
    - No whitespace (no spaces, no newlines)
    - Consistent number formatting

    Args:
        payload: Dictionary to serialize.

    Returns:
        Canonical JSON string.

    Example:
        >>> create_canonical_json({"b": 2, "a": 1})
        '{"a":1,"b":2}'
    """
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def hash_payload(payload: dict[str, Any]) -> bytes:
    """Create SHA256 hash of canonical JSON payload.

    Args:
        payload: Dictionary to hash.

    Returns:
        32-byte SHA256 digest.
    """
    canonical = create_canonical_json(payload)
    return hashlib.sha256(canonical.encode("utf-8")).digest()


def verify_intent_signature(
    payload: dict[str, Any],
    signature: str,
    pub_key: str,
) -> bool:
    """Verify an ECDSA secp256k1 signature on a voting intent.

    Args:
        payload: The intent payload that was signed (dict).
        signature: Base64-encoded DER signature.
        pub_key: Base64-encoded compressed or uncompressed public key.

    Returns:
        True if signature is valid, False otherwise.

    Raises:
        SignatureVerificationError: If inputs are malformed (not just invalid signature).

    Example:
        >>> # Mobile signs: canonical_json -> sha256 -> ecdsa_sign
        >>> payload = {
        ...     "proposal_id": 42,
        ...     "voter_address": "cosmos1alice...",
        ...     "vote_option": "NO",
        ...     "timestamp": 1706612345,
        ...     "nonce": "abc123"
        ... }
        >>> valid = verify_intent_signature(payload, sig_b64, pubkey_b64)
    """
    try:
        # Decode base64 inputs
        try:
            signature_bytes = base64.b64decode(signature)
        except Exception as e:
            logger.warning(f"Failed to decode signature base64: {e}")
            raise SignatureVerificationError(
                "Invalid signature encoding",
                reason="invalid_signature_encoding",
            )

        try:
            pub_key_bytes = base64.b64decode(pub_key)
        except Exception as e:
            logger.warning(f"Failed to decode public key base64: {e}")
            raise SignatureVerificationError(
                "Invalid public key encoding",
                reason="invalid_pubkey_encoding",
            )

        # Create verifying key from public key bytes
        try:
            # Try to load as compressed (33 bytes) or uncompressed (65 bytes) key
            if len(pub_key_bytes) == 33:
                # Compressed public key
                verifying_key = VerifyingKey.from_string(
                    pub_key_bytes,
                    curve=SECP256k1,
                )
            elif len(pub_key_bytes) == 65:
                # Uncompressed public key (04 prefix + 64 bytes)
                verifying_key = VerifyingKey.from_string(
                    pub_key_bytes,
                    curve=SECP256k1,
                )
            else:
                logger.warning(f"Invalid public key length: {len(pub_key_bytes)}")
                raise SignatureVerificationError(
                    f"Invalid public key length: {len(pub_key_bytes)} (expected 33 or 65)",
                    reason="invalid_pubkey_length",
                )
        except SignatureVerificationError:
            raise
        except Exception as e:
            logger.warning(f"Failed to parse public key: {e}")
            raise SignatureVerificationError(
                "Invalid public key format",
                reason="invalid_pubkey_format",
            )

        # Hash the payload
        digest = hash_payload(payload)

        # Verify signature
        try:
            # Try DER format first (most common)
            verifying_key.verify_digest(
                signature_bytes,
                digest,
                sigdecode=sigdecode_der,
            )
            logger.debug("Signature verified successfully (DER format)")
            return True
        except BadSignatureError:
            # Try raw format (r || s, 64 bytes)
            if len(signature_bytes) == 64:
                try:
                    verifying_key.verify_digest(signature_bytes, digest)
                    logger.debug("Signature verified successfully (raw format)")
                    return True
                except BadSignatureError:
                    pass
            logger.debug("Signature verification failed")
            return False

    except SignatureVerificationError:
        raise
    except Exception as e:
        logger.error(f"Unexpected error during signature verification: {e}")
        raise SignatureVerificationError(
            f"Signature verification error: {e}",
            reason="verification_error",
        )


def create_test_keypair() -> tuple[bytes, bytes]:
    """Create a test keypair for development/testing.

    Returns:
        Tuple of (private_key_bytes, public_key_bytes_compressed).

    Note:
        Only use for testing! In production, keys come from user wallets.
    """
    from ecdsa import SigningKey

    private_key = SigningKey.generate(curve=SECP256k1)
    public_key = private_key.get_verifying_key()

    return (
        private_key.to_string(),
        public_key.to_string("compressed"),
    )


def sign_payload(payload: dict[str, Any], private_key_bytes: bytes) -> str:
    """Sign a payload with a private key (for testing).

    Args:
        payload: Dictionary to sign.
        private_key_bytes: 32-byte secp256k1 private key.

    Returns:
        Base64-encoded DER signature.

    Note:
        Only use for testing! In production, signing happens on mobile.
    """
    from ecdsa import SigningKey
    from ecdsa.util import sigencode_der

    signing_key = SigningKey.from_string(private_key_bytes, curve=SECP256k1)
    digest = hash_payload(payload)
    signature = signing_key.sign_digest(digest, sigencode=sigencode_der)

    return base64.b64encode(signature).decode("ascii")


if __name__ == "__main__":
    # Quick test
    import sys

    logging.basicConfig(level=logging.DEBUG)

    # Create test keypair
    priv_key, pub_key = create_test_keypair()
    pub_key_b64 = base64.b64encode(pub_key).decode()

    # Test payload
    payload = {
        "proposal_id": 42,
        "voter_address": "cosmos1test123",
        "vote_option": "NO",
        "public_reasoning": "This violates @protection principle",
        "confidence_score": 0.95,
        "timestamp": 1706612345,
        "nonce": "abc123def456",
    }

    # Sign and verify
    signature = sign_payload(payload, priv_key)
    print(f"Payload: {create_canonical_json(payload)}")
    print(f"Public key (b64): {pub_key_b64}")
    print(f"Signature (b64): {signature}")

    result = verify_intent_signature(payload, signature, pub_key_b64)
    print(f"Verification result: {result}")

    # Test with tampered payload
    tampered = payload.copy()
    tampered["vote_option"] = "YES"
    tampered_result = verify_intent_signature(tampered, signature, pub_key_b64)
    print(f"Tampered verification result: {tampered_result}")

    sys.exit(0 if result and not tampered_result else 1)
