#!/usr/bin/env python3
"""
Mock Phone with SML (Small Language Model)

Simulates a mobile phone that:
1. Has a user persona (values, priorities)
2. Uses small LLM (qwen3:4b) to analyze proposals
3. Generates voting decision + reasoning
4. Signs with EIP-712 and submits to Observer

This tests the full semantic firewall flow:
- Phone (SML) generates reasoning based on persona
- Observer (larger LLM) validates reasoning consistency
- If consistent → vote submitted to DAHAO Subnet

Usage:
    python tests/mock_phone_sml.py --node-url http://localhost:8080 --persona eco_warrior
    python tests/mock_phone_sml.py --persona profit_maximizer --proposal-id 2
    python tests/mock_phone_sml.py --list-personas
    python tests/mock_phone_sml.py --list-proposals
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass
from typing import Any

import requests
from eth_account import Account
from eth_account.messages import encode_typed_data

# =============================================================================
# Personas - Different voter archetypes
# =============================================================================

PERSONAS = {
    "eco_warrior": {
        "name": "Eco Warrior",
        "description": "Prioritizes environmental sustainability above all",
        "values": ["environment", "sustainability", "green energy", "conservation"],
        "against": ["pollution", "deforestation", "fossil fuels", "mining"],
    },
    "profit_maximizer": {
        "name": "Profit Maximizer",
        "description": "Focuses on economic growth and returns",
        "values": ["profit", "efficiency", "growth", "ROI"],
        "against": ["excessive regulation", "wasteful spending"],
    },
    "community_builder": {
        "name": "Community Builder",
        "description": "Values community welfare and inclusion",
        "values": ["community", "fairness", "accessibility", "education"],
        "against": ["exclusion", "centralization", "inequality"],
    },
    "tech_progressive": {
        "name": "Tech Progressive",
        "description": "Believes in technological advancement",
        "values": ["innovation", "technology", "automation", "AI"],
        "against": ["stagnation", "outdated systems"],
    },
}

# =============================================================================
# Mock Proposals - Test scenarios
# =============================================================================

MOCK_PROPOSALS = [
    {
        "id": 1,
        "title": "Fund Solar Panel Installation",
        "description": "Allocate 100,000 DAHAO to install solar panels on community buildings, reducing carbon footprint by 40%.",
    },
    {
        "id": 2,
        "title": "Increase Mining Operations Budget",
        "description": "Expand mining operations to increase token supply. This will boost short-term profits but may impact local environment.",
    },
    {
        "id": 3,
        "title": "Community Education Program",
        "description": "Fund free blockchain education workshops for underrepresented communities. Budget: 50,000 DAHAO.",
    },
    {
        "id": 4,
        "title": "Implement AI-Powered Trading Bot",
        "description": "Develop and deploy an AI trading bot to maximize treasury returns through automated DeFi strategies.",
    },
    {
        "id": 5,
        "title": "Build New Coal Power Plant",
        "description": "Construct a coal-fired power plant to reduce energy costs by 30%. Estimated CO2 emissions: 500,000 tons/year.",
    },
]


@dataclass
class VoteDecision:
    """Parsed SML voting decision."""

    vote: str  # YES, NO, ABSTAIN
    reasoning: str
    confidence: float


# EWOQ test account (pre-funded with 1M DAHAO tokens on local subnet)
EWOQ_PRIVATE_KEY = "56289e99c94b6912bfc12adc093c9b51124f0dc54ac7a766b2bc5ccf558d8027"
EWOQ_ADDRESS = "0x8db97C7cEcE249c2b98bDC0226Cc4C2A57BF52FC"


class SMLPhoneClient:
    """Mock phone client with small language model for voting decisions."""

    def __init__(
        self,
        node_url: str,
        persona_key: str,
        ollama_host: str = "http://localhost:11434",
        model: str = "qwen3:4b",
        use_ewoq: bool = False,
        use_local_proposals: bool = False,
    ):
        self.node_url = node_url.rstrip("/")
        self.ollama_host = ollama_host.rstrip("/")
        self.model = model
        self.persona_key = persona_key
        self.persona = PERSONAS[persona_key]
        self.use_local_proposals = use_local_proposals

        # Use EWOQ test account (has tokens) or generate random wallet
        if use_ewoq:
            self.account = Account.from_key(EWOQ_PRIVATE_KEY)
        else:
            self.account = Account.create()
        self.session_id: str | None = None

    @property
    def address(self) -> str:
        return self.account.address

    # =========================================================================
    # Ollama Integration
    # =========================================================================

    def _call_ollama(self, prompt: str) -> str:
        """Call Ollama with the small model."""
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.0,  # Deterministic for consistent test results
                "num_predict": 1500,  # Ensure thinking models can complete
            },
        }

        try:
            response = requests.post(
                f"{self.ollama_host}/api/generate",
                json=payload,
                timeout=120,  # Longer timeout for slower models
            )
            response.raise_for_status()
            data = response.json()

            # Qwen3 models put thinking in separate field, response may be empty
            result = data.get("response", "")
            thinking = data.get("thinking", "")

            # If response is empty but thinking has content, use thinking
            if not result.strip() and thinking:
                result = thinking

            # Debug: print response
            print(f"[DEBUG] LLM response:\n{result[:500]}...\n[END DEBUG]")
            return result
        except requests.exceptions.RequestException as e:
            print(f"Error calling Ollama: {e}")
            raise

    def analyze_proposal(self, proposal: dict) -> VoteDecision:
        """Use SML to analyze proposal based on persona."""
        # Prompt that puts VOTE at the very end to avoid premature output
        values = ', '.join(self.persona['values'][:2])
        against = ', '.join(self.persona['against'][:2])

        prompt = f"""/no_think
Your values: {values}
You oppose: {against}

Proposal: {proposal['title']}
Details: {proposal['description'][:150]}

Question: Does this proposal support your values or oppose them?

Think step by step:
1. What does this proposal do?
2. Does it align with {values}?
3. Does it involve {against} which you oppose?

Then output your final answer in EXACTLY this format:
REASONING: [one sentence explaining why]
CONFIDENCE: [0.0-1.0]
VOTE: [YES if supports your values, NO if opposes them]"""

        response = self._call_ollama(prompt)
        return self._parse_response(response)

    def _parse_response(self, response: str) -> VoteDecision:
        """Parse SML response into structured format."""
        # Clean up response - remove thinking tags if present
        response = re.sub(r"<think>.*?</think>", "", response, flags=re.DOTALL)
        response = response.strip()

        # Extract VOTE - use LAST match (model may echo examples first)
        vote = "ABSTAIN"
        vote_matches = re.findall(r"VOTE:\s*(YES|NO|ABSTAIN)", response, re.IGNORECASE)
        if vote_matches:
            # Use the LAST vote (the model's actual answer, not echoed examples)
            vote = vote_matches[-1].upper()
        else:
            # Try to find standalone YES/NO at start of line - use last match
            line_matches = re.findall(r"^(YES|NO|ABSTAIN)\b", response, re.IGNORECASE | re.MULTILINE)
            if line_matches:
                vote = line_matches[-1].upper()
            # Or look for "I vote YES/NO" - use last match
            else:
                vote_statements = re.findall(r"\bvote\s+(YES|NO)\b", response, re.IGNORECASE)
                if vote_statements:
                    vote = vote_statements[-1].upper()

        # Extract REASONING - try multiple patterns
        reasoning = ""
        reasoning_match = re.search(
            r"REASONING:\s*(.+?)(?=CONFIDENCE:|$)", response, re.IGNORECASE | re.DOTALL
        )
        if reasoning_match:
            reasoning = reasoning_match.group(1).strip()

        # If no reasoning found, try to extract text after the vote line
        if not reasoning:
            lines = response.split('\n')
            for i, line in enumerate(lines):
                if re.search(r"^(YES|NO|ABSTAIN|VOTE:)", line, re.IGNORECASE):
                    # Get the next lines as reasoning
                    remaining = '\n'.join(lines[i+1:]).strip()
                    # Remove CONFIDENCE line if present
                    remaining = re.sub(r"CONFIDENCE:.*$", "", remaining, flags=re.IGNORECASE | re.MULTILINE)
                    if remaining and len(remaining) > 20:
                        reasoning = remaining.strip()
                    break

        # If still no reasoning, look for any substantive sentences
        if not reasoning:
            sentences = re.findall(r"[A-Z][^.!?]*[.!?]", response)
            explanatory = [s.strip() for s in sentences if len(s) > 30 and not re.search(r"^(VOTE|REASONING|CONFIDENCE)", s)]
            if explanatory:
                reasoning = " ".join(explanatory[:2])

        # Final fallback
        if not reasoning:
            reasoning = f"Based on my {self.persona['name']} values ({', '.join(self.persona['values'][:2])}), I vote {vote}."

        # Extract CONFIDENCE
        confidence = 0.7
        confidence_match = re.search(r"CONFIDENCE:\s*([\d.]+)", response, re.IGNORECASE)
        if confidence_match:
            try:
                confidence = float(confidence_match.group(1))
                confidence = max(0.0, min(1.0, confidence))
            except ValueError:
                pass
        else:
            # Look for any decimal number that might be confidence
            num_match = re.search(r"\b(0\.\d+|1\.0)\b", response)
            if num_match:
                try:
                    confidence = float(num_match.group(1))
                except ValueError:
                    pass

        return VoteDecision(vote=vote, reasoning=reasoning, confidence=confidence)

    # =========================================================================
    # Node Communication
    # =========================================================================

    def connect_to_node(self) -> bool:
        """Connect to node and register EVM address.

        Uses the simplified /register_evm endpoint for testing.
        """
        try:
            # Register EVM address (simplified for testing)
            resp = requests.post(
                f"{self.node_url}/api/v1/register_evm",
                json={"voter_address": self.address},
                timeout=10,
            )
            resp.raise_for_status()
            result = resp.json()
            print(f"Registered: {result.get('status')}")
            return True
        except requests.exceptions.RequestException as e:
            print(f"Failed to register with node: {e}")
            return False

    def get_proposal(self, proposal_id: int) -> dict:
        """Get proposal from node or use mock."""
        # If using local proposals, skip API
        if not self.use_local_proposals:
            # Try to get from node
            try:
                resp = requests.get(f"{self.node_url}/api/v1/proposals")
                resp.raise_for_status()
                proposals = resp.json().get("proposals", [])
                for p in proposals:
                    if p.get("id") == proposal_id:
                        return p
            except requests.exceptions.RequestException:
                pass

        # Fall back to mock proposals
        for p in MOCK_PROPOSALS:
            if p["id"] == proposal_id:
                return p

        # Return a default mock
        return MOCK_PROPOSALS[0]

    # =========================================================================
    # EIP-712 Signing
    # =========================================================================

    def create_signed_vote(
        self,
        proposal_id: int,
        decision: VoteDecision,
        forwarder_address: str,
        governor_address: str,
        chain_id: int,
    ) -> dict:
        """Create EIP-712 signed vote request."""
        import secrets

        # Get nonce from forwarder (mock as 0 for testing)
        nonce = 0

        # Deadline 1 hour from now
        deadline = int(time.time()) + 3600

        # Encode castVote call data
        # castVote(uint256 proposalId, uint8 support)
        # support: 0=Against, 1=For, 2=Abstain
        support_map = {"NO": 0, "YES": 1, "ABSTAIN": 2}
        support = support_map.get(decision.vote, 2)

        # Function selector for castVote(uint256,uint8)
        call_data = bytes.fromhex("56781388")  # castVote selector
        call_data += proposal_id.to_bytes(32, "big")
        call_data += support.to_bytes(32, "big")

        # Build ForwardRequest
        request = {
            "from": self.address,
            "to": governor_address,
            "value": 0,
            "gas": 150000,
            "nonce": nonce,
            "deadline": deadline,
            "data": "0x" + call_data.hex(),
        }

        # EIP-712 typed data
        typed_data = {
            "types": {
                "EIP712Domain": [
                    {"name": "name", "type": "string"},
                    {"name": "version", "type": "string"},
                    {"name": "chainId", "type": "uint256"},
                    {"name": "verifyingContract", "type": "address"},
                ],
                "ForwardRequest": [
                    {"name": "from", "type": "address"},
                    {"name": "to", "type": "address"},
                    {"name": "value", "type": "uint256"},
                    {"name": "gas", "type": "uint256"},
                    {"name": "nonce", "type": "uint256"},
                    {"name": "deadline", "type": "uint48"},
                    {"name": "data", "type": "bytes"},
                ],
            },
            "primaryType": "ForwardRequest",
            "domain": {
                "name": "DAHAOForwarder",
                "version": "1",
                "chainId": chain_id,
                "verifyingContract": forwarder_address,
            },
            "message": request,
        }

        # Sign
        signable = encode_typed_data(full_message=typed_data)
        signed = self.account.sign_message(signable)

        # Build API request with all required fields
        return {
            "proposal_id": proposal_id,
            "voter_address": self.address,
            "vote_option": decision.vote,
            "public_reasoning": decision.reasoning,
            "confidence_score": decision.confidence,  # API expects confidence_score
            "timestamp": int(time.time()),  # Current unix timestamp
            "nonce": secrets.token_hex(16),  # Random nonce for replay protection
            "eip712_signature": signed.signature.hex(),
        }

    # =========================================================================
    # Main Flow
    # =========================================================================

    def submit_vote(
        self,
        proposal_id: int,
        forwarder_address: str = "0x4Ac1d98D9cEF99EC6546dEd4Bd550b0b287aaD6D",
        governor_address: str = "0xa4DfF80B4a1D748BF28BC4A271eD834689Ea3407",
        chain_id: int = 43210,
    ) -> dict:
        """Full flow: analyze -> decide -> sign -> submit."""
        # 1. Get proposal
        print(f"\n{'='*60}")
        print(f"Proposal #{proposal_id}")
        print(f"{'='*60}")
        proposal = self.get_proposal(proposal_id)
        print(f"Title: {proposal['title']}")
        print(f"Description: {proposal['description'][:100]}...")

        # 2. Analyze with SML
        print(f"\n{'='*60}")
        print("SML Analysis")
        print(f"{'='*60}")
        print(f"Model: {self.model}")
        print("Analyzing...")

        decision = self.analyze_proposal(proposal)

        print(f"\nVOTE: {decision.vote}")
        print(f"REASONING: {decision.reasoning}")
        print(f"CONFIDENCE: {decision.confidence:.2f}")

        # 3. Sign with EIP-712
        print(f"\n{'='*60}")
        print("Signing Vote")
        print(f"{'='*60}")
        signed_request = self.create_signed_vote(
            proposal_id,
            decision,
            forwarder_address,
            governor_address,
            chain_id,
        )
        print(f"Voter: {self.address}")
        print(f"Signature: {signed_request['eip712_signature'][:20]}...")

        # 4. Submit to Observer
        print(f"\n{'='*60}")
        print("Submitting to Observer")
        print(f"{'='*60}")
        try:
            response = requests.post(
                f"{self.node_url}/api/v1/submit_vote",
                json=signed_request,
                timeout=30,
            )
            result = response.json()
            print(f"Status: {response.status_code}")
            print(f"Response: {json.dumps(result, indent=2)}")
            return result
        except requests.exceptions.RequestException as e:
            print(f"Error submitting vote: {e}")
            return {"error": str(e)}


def list_personas():
    """Print available personas."""
    print("\nAvailable Personas:")
    print("=" * 60)
    for key, persona in PERSONAS.items():
        print(f"\n{key}:")
        print(f"  Name: {persona['name']}")
        print(f"  Description: {persona['description']}")
        print(f"  Values: {', '.join(persona['values'])}")
        print(f"  Against: {', '.join(persona['against'])}")


def list_proposals():
    """Print mock proposals."""
    print("\nMock Proposals:")
    print("=" * 60)
    for p in MOCK_PROPOSALS:
        print(f"\n#{p['id']}: {p['title']}")
        print(f"   {p['description']}")


def main():
    parser = argparse.ArgumentParser(
        description="Mock Phone with SML for semantic firewall testing"
    )
    parser.add_argument("--node-url", default="http://localhost:8080", help="Observer node URL")
    parser.add_argument(
        "--persona",
        choices=list(PERSONAS.keys()),
        default="eco_warrior",
        help="Voter persona",
    )
    parser.add_argument("--proposal-id", type=int, default=1, help="Proposal ID to vote on")
    parser.add_argument(
        "--ollama-host", default="http://localhost:11434", help="Ollama server URL"
    )
    parser.add_argument("--model", default="qwen3:4b", help="Ollama model for SML")
    parser.add_argument(
        "--use-ewoq",
        action="store_true",
        help="Use EWOQ test account (has 1M DAHAO tokens)",
    )
    parser.add_argument("--list-personas", action="store_true", help="List available personas")
    parser.add_argument("--list-proposals", action="store_true", help="List mock proposals")
    parser.add_argument(
        "--forwarder",
        default="0x4Ac1d98D9cEF99EC6546dEd4Bd550b0b287aaD6D",
        help="Forwarder contract address",
    )
    parser.add_argument(
        "--governor",
        default="0xa4DfF80B4a1D748BF28BC4A271eD834689Ea3407",
        help="Governor contract address",
    )
    parser.add_argument("--chain-id", type=int, default=43210, help="Chain ID")
    parser.add_argument(
        "--use-local-proposals",
        action="store_true",
        help="Use built-in test proposals instead of fetching from API",
    )

    args = parser.parse_args()

    if args.list_personas:
        list_personas()
        sys.exit(0)

    if args.list_proposals:
        list_proposals()
        sys.exit(0)

    # Create client
    print("\n" + "=" * 60)
    print("Mock Phone with SML")
    print("=" * 60)
    print(f"Persona: {PERSONAS[args.persona]['name']}")
    print(f"Model: {args.model}")
    print(f"Node: {args.node_url}")

    client = SMLPhoneClient(
        node_url=args.node_url,
        persona_key=args.persona,
        ollama_host=args.ollama_host,
        model=args.model,
        use_ewoq=args.use_ewoq,
        use_local_proposals=args.use_local_proposals,
    )

    # Connect to node
    print("\nConnecting to node...")
    if not client.connect_to_node():
        print("Warning: Could not connect to node, continuing anyway...")

    # Submit vote
    result = client.submit_vote(
        proposal_id=args.proposal_id,
        forwarder_address=args.forwarder,
        governor_address=args.governor,
        chain_id=args.chain_id,
    )

    # Summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    if result.get("status") == "success" or result.get("success"):
        print("Vote submitted successfully!")
        if result.get("tx_hash"):
            print(f"TX Hash: {result['tx_hash']}")
    else:
        print(f"Vote submission result: {result.get('status', 'unknown')}")
        if result.get("error"):
            print(f"Error: {result['error']}")


if __name__ == "__main__":
    main()
