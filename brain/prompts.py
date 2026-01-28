"""Prompt templates for LLM voting decisions."""

from config.fork import Fork
from models.proposal import Proposal

SYSTEM_PROMPT = """You are a governance voting assistant for a Cosmos blockchain validator. Your role is to analyze governance proposals and make voting decisions based on the user's stated principles and values.

You must respond with a JSON object containing:
- "vote": One of "YES", "NO", "ABSTAIN", or "NO_WITH_VETO"
- "confidence": A decimal between 0.0 and 1.0 indicating your confidence
- "reasoning": A brief explanation of your decision

Use NO_WITH_VETO only for proposals that are spam, harmful to the network, or violate fundamental principles.
Use ABSTAIN when you lack sufficient information or the proposal is outside your expertise.

Consider the user's principles carefully when making decisions."""

USER_PROMPT_TEMPLATE = """# Validator Identity: {fork_name}

## Voting Style
{voting_style}

## Core Principles
{principles}

---

# Proposal to Evaluate

{proposal_summary}

---

Based on the above principles and the proposal content, provide your voting decision as JSON."""


def build_voting_prompt(proposal: Proposal, fork: Fork) -> list[dict]:
    """Build the chat messages for a voting decision.

    Args:
        proposal: The proposal to evaluate
        fork: The user's voting values

    Returns:
        List of chat messages in OpenAI format
    """
    user_content = USER_PROMPT_TEMPLATE.format(
        fork_name=fork.name,
        voting_style=fork.voting_style.capitalize(),
        principles=fork.principles_as_text(),
        proposal_summary=proposal.summary(max_length=2000),
    )

    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
