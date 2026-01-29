"""DAHAO Sidecar operation modes.

Two modes of operation:
- Decider: Autonomous polling loop that makes voting decisions (original mode)
- Observer: API gateway that validates and relays votes from mobile clients (Gasless Voting)
"""

from .decider import run_decider_mode
from .observer import run_observer_mode

__all__ = [
    "run_decider_mode",
    "run_observer_mode",
]
