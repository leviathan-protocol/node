#!/usr/bin/env python3
"""
Submit test proposals to the DAHAO chain for swarm simulation testing.

Usage:
    python submit_test_proposals.py              # Submit all proposals
    python submit_test_proposals.py --proposal 1 # Submit specific proposal
    python submit_test_proposals.py --list       # List available proposals
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

PROPOSALS_DIR = Path("simulation/proposals")


def find_dahaod() -> str:
    """Find the dahaod binary in common locations."""
    # Check common locations
    locations = [
        Path.home() / "go" / "bin" / "dahaod",
        Path.home() / ".ignite" / "local" / "bin" / "dahaod",
        Path("dahao") / "build" / "dahaod",
        Path("/usr/local/bin/dahaod"),
    ]

    # Check PATH first
    for path_dir in os.environ.get("PATH", "").split(os.pathsep):
        candidate = Path(path_dir) / "dahaod"
        if candidate.exists():
            return str(candidate)

    # Check known locations
    for loc in locations:
        if loc.exists():
            return str(loc)

    return "dahaod"  # Fall back to hoping it's in PATH

# Proposal metadata for display
PROPOSALS = {
    "01_environmental_protection.json": {
        "name": "Environmental Protection",
        "expected": "Alice: YES, Bob: NO, Eve: Needs audit info",
    },
    "02_defi_expansion.json": {
        "name": "DeFi Expansion",
        "expected": "Bob: YES, Alice: NO (energy), Eve: NO (safety checks removed)",
    },
    "03_decentralize_governance.json": {
        "name": "Full Decentralization",
        "expected": "Charlie: YES, Dave: NO (too radical), Eve: CAUTIOUS",
    },
    "04_security_audit.json": {
        "name": "Security Audit Requirement",
        "expected": "Eve: YES, All others: Likely YES",
    },
    "05_minor_parameter_update.json": {
        "name": "Routine Parameter Update",
        "expected": "Dave: YES, Charlie: SKEPTICAL (core team)",
    },
}


def list_proposals():
    """List available test proposals."""
    print("\nAvailable Test Proposals:")
    print("=" * 60)

    for i, (filename, meta) in enumerate(PROPOSALS.items(), 1):
        filepath = PROPOSALS_DIR / filename
        exists = "✓" if filepath.exists() else "✗"
        print(f"\n{i}. [{exists}] {meta['name']}")
        print(f"   File: {filename}")
        print(f"   Expected votes: {meta['expected']}")

    print("\n" + "=" * 60)


def submit_proposal(filepath: Path, from_account: str = "alice") -> bool:
    """Submit a proposal to the chain."""
    if not filepath.exists():
        print(f"ERROR: Proposal file not found: {filepath}")
        return False

    print(f"\nSubmitting: {filepath.name}")

    dahaod = find_dahaod()
    cmd = [
        dahaod, "tx", "gov", "submit-proposal",
        str(filepath),
        "--from", from_account,
        "--keyring-backend", "test",
        "--chain-id", "dahao",
        "--yes",
        "--output", "json",
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode == 0:
            try:
                output = json.loads(result.stdout)
                txhash = output.get("txhash", "unknown")
                print(f"  ✓ Submitted (txhash: {txhash[:16]}...)")
                return True
            except json.JSONDecodeError:
                print(f"  ✓ Submitted")
                return True
        else:
            print(f"  ✗ Failed: {result.stderr}")
            return False

    except subprocess.TimeoutExpired:
        print("  ✗ Timeout waiting for transaction")
        return False
    except FileNotFoundError:
        print(f"  ✗ dahaod not found at: {dahaod}")
        print("    Try: export PATH=$PATH:~/go/bin")
        print("    Or:  cd dahao && ignite chain build")
        return False


def submit_all(delay: float = 3.0):
    """Submit all proposals with delay between each."""
    print("\n" + "=" * 60)
    print("  Submitting All Test Proposals")
    print("=" * 60)

    success = 0
    failed = 0

    for filename in PROPOSALS.keys():
        filepath = PROPOSALS_DIR / filename
        if submit_proposal(filepath):
            success += 1
        else:
            failed += 1

        # Wait for tx to be processed
        time.sleep(delay)

    print("\n" + "=" * 60)
    print(f"  Complete: {success} submitted, {failed} failed")
    print("  Run: dahaod q gov proposals")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(
        description="Submit test proposals to DAHAO chain",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--list", "-l",
        action="store_true",
        help="List available proposals",
    )
    parser.add_argument(
        "--proposal", "-p",
        type=int,
        help="Submit specific proposal by number (1-5)",
    )
    parser.add_argument(
        "--from",
        dest="from_account",
        default="alice",
        help="Account to submit from (default: alice)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=3.0,
        help="Delay between submissions in seconds (default: 3.0)",
    )
    args = parser.parse_args()

    if args.list:
        list_proposals()
        return

    if args.proposal:
        if args.proposal < 1 or args.proposal > len(PROPOSALS):
            print(f"ERROR: Proposal number must be 1-{len(PROPOSALS)}")
            sys.exit(1)

        filename = list(PROPOSALS.keys())[args.proposal - 1]
        filepath = PROPOSALS_DIR / filename
        if not submit_proposal(filepath, args.from_account):
            sys.exit(1)
    else:
        submit_all(args.delay)


if __name__ == "__main__":
    main()
