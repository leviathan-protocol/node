#!/usr/bin/env python3
"""
DAHAO Swarm Simulation - "The Swarm Test"

Runs multiple sidecar agents with different personalities (Forks) to simulate
a diverse validator set voting on governance proposals.

Architecture:
  1 Chain (DAHAO) + 1 LLM (Ollama) + N Sidecars (each with unique Fork + Wallet)

Usage:
  1. Start the chain: cd dahao && ignite chain serve
  2. Start Ollama: ollama serve
  3. Configure wallets in simulation/wallets.yaml
  4. Run: python simulation_swarm.py

The script will launch 5 agents in parallel:
  - Alice (Nature Mother) - Biocentric, votes NO on environmental risks
  - Bob (Capitalist) - Profit-focused, votes YES on growth opportunities
  - Charlie (Anarchist) - Decentralization maximalist
  - Dave (Conformist) - Status quo defender
  - Eve (Hacker) - Security researcher
"""

import argparse
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import yaml

# Default agent configurations
DEFAULT_AGENTS = [
    {"name": "Alice", "fork": "simulation/alice.yaml", "color": "\033[92m"},  # Green
    {"name": "Bob", "fork": "simulation/bob.yaml", "color": "\033[93m"},      # Yellow
    {"name": "Charlie", "fork": "simulation/charlie.yaml", "color": "\033[94m"},  # Blue
    {"name": "Dave", "fork": "simulation/dave.yaml", "color": "\033[95m"},    # Magenta
    {"name": "Eve", "fork": "simulation/eve.yaml", "color": "\033[96m"},      # Cyan
]

RESET_COLOR = "\033[0m"


def load_wallets(wallet_file: str = "simulation/wallets.yaml") -> dict:
    """Load wallet mnemonics from YAML file."""
    wallet_path = Path(wallet_file)
    if not wallet_path.exists():
        return {}

    with open(wallet_path) as f:
        return yaml.safe_load(f) or {}


def create_wallet_template(wallet_file: str = "simulation/wallets.yaml"):
    """Create a template wallets.yaml file."""
    template = """# Wallet mnemonics for simulation agents
# Get these from 'ignite chain serve' output or generate with 'dahaod keys add <name>'
#
# IMPORTANT: These are TEST wallets only. Never use real funds!
#
# To fund test wallets, use:
#   dahaod tx bank send alice <wallet-address> 10000000stake --yes

alice: "your twenty four word mnemonic for alice here"
bob: "your twenty four word mnemonic for bob here"
charlie: "your twenty four word mnemonic for charlie here"
dave: "your twenty four word mnemonic for dave here"
eve: "your twenty four word mnemonic for eve here"
"""
    with open(wallet_file, "w") as f:
        f.write(template)
    print(f"Created wallet template: {wallet_file}")
    print("Please edit this file with your test wallet mnemonics.")


def verify_prerequisites():
    """Check that chain and Ollama are running."""
    errors = []

    # Check Ollama
    try:
        import httpx
        resp = httpx.get("http://localhost:11434/api/tags", timeout=5)
        if resp.status_code != 200:
            errors.append("Ollama is not responding correctly")
    except Exception:
        errors.append("Ollama is not running. Start with: ollama serve")

    # Check chain (try gRPC)
    try:
        import grpc
        channel = grpc.insecure_channel("localhost:9090")
        grpc.channel_ready_future(channel).result(timeout=5)
    except Exception:
        errors.append("Chain gRPC not available. Start with: cd dahao && ignite chain serve")

    return errors


def run_swarm(agents: list, wallets: dict, startup_delay: float = 3.0):
    """Launch all agent sidecars."""
    processes = []

    print("\n" + "=" * 60)
    print("  DAHAO SWARM SIMULATION")
    print("  5 Agents, 5 Worldviews, 1 Democracy")
    print("=" * 60 + "\n")

    # Verify we have wallets for all agents
    missing = [a["name"].lower() for a in agents if a["name"].lower() not in wallets]
    if missing:
        print(f"ERROR: Missing wallet mnemonics for: {', '.join(missing)}")
        print(f"Please edit simulation/wallets.yaml and add mnemonics.")
        sys.exit(1)

    for agent in agents:
        name = agent["name"]
        fork = agent["fork"]
        color = agent["color"]
        mnemonic = wallets[name.lower()]

        # State file per agent to avoid conflicts
        state_file = f"simulation/state_{name.lower()}.json"

        print(f"{color}Starting {name}...{RESET_COLOR}")

        # Build command
        cmd = [
            sys.executable, "main.py",
            "--fork", fork,
            "--wallet", mnemonic,
            "--state", state_file,
            "--name", name,
        ]

        # Start process
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        processes.append({"name": name, "proc": proc, "color": color})

        # Stagger startup to avoid chain congestion
        time.sleep(startup_delay)

    print("\n" + "=" * 60)
    print("  ALL AGENTS RUNNING - Press Ctrl+C to stop")
    print("=" * 60 + "\n")

    return processes


def stream_output(processes: list):
    """Stream output from all processes with color coding."""
    import select

    # Set up file descriptors for select
    fd_to_proc = {}
    for p in processes:
        fd = p["proc"].stdout.fileno()
        fd_to_proc[fd] = p
        # Make non-blocking
        os.set_blocking(fd, False)

    while any(p["proc"].poll() is None for p in processes):
        # Wait for output from any process
        readable = []
        try:
            readable, _, _ = select.select(list(fd_to_proc.keys()), [], [], 1.0)
        except (ValueError, OSError):
            # File descriptor closed
            break

        for fd in readable:
            p = fd_to_proc.get(fd)
            if p is None:
                continue
            try:
                line = p["proc"].stdout.readline()
                if line:
                    print(f"{p['color']}[{p['name']}]{RESET_COLOR} {line}", end="")
            except (IOError, OSError):
                pass


def stop_swarm(processes: list):
    """Gracefully stop all agent processes."""
    print("\n\nStopping swarm...")
    for p in processes:
        if p["proc"].poll() is None:
            p["proc"].terminate()
            print(f"  Stopped {p['name']}")

    # Wait for processes to exit
    for p in processes:
        try:
            p["proc"].wait(timeout=5)
        except subprocess.TimeoutExpired:
            p["proc"].kill()


def main():
    parser = argparse.ArgumentParser(
        description="Run DAHAO Swarm Simulation with multiple voting agents",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python simulation_swarm.py              # Run all 5 agents
  python simulation_swarm.py --init       # Create wallet template
  python simulation_swarm.py --agents 3   # Run first 3 agents only
        """,
    )
    parser.add_argument(
        "--init",
        action="store_true",
        help="Create template wallets.yaml file",
    )
    parser.add_argument(
        "--agents",
        type=int,
        default=5,
        help="Number of agents to run (1-5, default: 5)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=3.0,
        help="Startup delay between agents in seconds (default: 3.0)",
    )
    parser.add_argument(
        "--skip-checks",
        action="store_true",
        help="Skip prerequisite checks",
    )
    args = parser.parse_args()

    # Create template if requested
    if args.init:
        create_wallet_template()
        return

    # Verify prerequisites
    if not args.skip_checks:
        errors = verify_prerequisites()
        if errors:
            print("Prerequisite check failed:")
            for e in errors:
                print(f"  - {e}")
            sys.exit(1)
        print("Prerequisites OK")

    # Load wallets
    wallets = load_wallets()
    if not wallets:
        print("No wallets configured!")
        print("Run: python simulation_swarm.py --init")
        print("Then edit simulation/wallets.yaml with your test mnemonics.")
        sys.exit(1)

    # Select agents
    agents = DEFAULT_AGENTS[:args.agents]

    # Run swarm
    processes = run_swarm(agents, wallets, args.delay)

    # Handle Ctrl+C
    def signal_handler(sig, frame):
        stop_swarm(processes)
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Stream output
    try:
        stream_output(processes)
    finally:
        stop_swarm(processes)


if __name__ == "__main__":
    main()
