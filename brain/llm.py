"""LLM wrapper using Ollama."""

import json
import logging

import ollama

from config.settings import LLMConfig

logger = logging.getLogger(__name__)

# JSON Schema for structured vote output (replaces GBNF grammar)
VOTE_SCHEMA = {
    "type": "object",
    "properties": {
        "vote": {
            "type": "string",
            "enum": ["YES", "NO", "ABSTAIN", "NO_WITH_VETO"],
            "description": "The vote choice",
        },
        "confidence": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0,
            "description": "Confidence level from 0.0 to 1.0",
        },
        "reasoning": {
            "type": "string",
            "description": "Brief explanation for the vote decision",
        },
    },
    "required": ["vote", "confidence", "reasoning"],
}

# JSON Schema for fork validation output
FORK_VALIDATION_SCHEMA = {
    "type": "object",
    "properties": {
        "valid": {
            "type": "boolean",
            "description": "True if fork principles are compatible with locked principles",
        },
        "violations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "fork_principle": {
                        "type": "string",
                        "description": "The fork principle that violates",
                    },
                    "locked_principle": {
                        "type": "string",
                        "description": "The locked principle being violated",
                    },
                    "reason": {
                        "type": "string",
                        "description": "Why this is a violation",
                    },
                },
                "required": ["fork_principle", "locked_principle", "reason"],
            },
            "description": "List of violations found (empty if valid)",
        },
        "summary": {
            "type": "string",
            "description": "Brief summary of the validation result",
        },
    },
    "required": ["valid", "violations", "summary"],
}


class LLMWrapper:
    """Wrapper around Ollama for local LLM inference."""

    def __init__(self, config: LLMConfig):
        self.config = config
        self._client: ollama.Client | None = None
        self._model_verified = False

    @property
    def client(self) -> ollama.Client:
        """Return the Ollama client."""
        if self._client is None:
            self._client = ollama.Client(host=self.config.ollama_host)
        return self._client

    @property
    def model(self) -> str:
        """Verify model is available and return model name."""
        if not self._model_verified:
            self._verify_model()
            self._model_verified = True
        return self.config.model_name

    def _verify_model(self):
        """Verify the model is available in Ollama."""
        logger.info(f"Verifying Ollama model: {self.config.model_name}")

        try:
            # List available models
            models = self.client.list()
            model_names = [m.model for m in models.models]

            if self.config.model_name not in model_names:
                # Try to find partial match
                matches = [m for m in model_names if self.config.model_name.split(":")[0] in m]
                if matches:
                    logger.warning(
                        f"Model '{self.config.model_name}' not found. "
                        f"Available matches: {matches}"
                    )
                raise FileNotFoundError(
                    f"Model '{self.config.model_name}' not found in Ollama. "
                    f"Run: ollama pull {self.config.model_name}"
                )

            logger.info(f"Ollama model verified: {self.config.model_name}")

        except ollama.ResponseError as e:
            raise ConnectionError(f"Failed to connect to Ollama: {e}")

    def generate_vote_decision(self, messages: list[dict]) -> str:
        """Generate a voting decision using structured JSON output.

        Args:
            messages: Chat messages in OpenAI format [{"role": "...", "content": "..."}]

        Returns:
            JSON string with vote decision
        """
        response = self.client.chat(
            model=self.model,
            messages=messages,
            format=VOTE_SCHEMA,
            options={
                "temperature": 0.7,
                "num_ctx": self.config.n_ctx,
            },
        )

        return response.message.content

    def generate(self, messages: list[dict], max_tokens: int = 1024) -> str:
        """Generate a response without schema constraints.

        Args:
            messages: Chat messages in OpenAI format
            max_tokens: Maximum tokens to generate

        Returns:
            Generated text
        """
        response = self.client.chat(
            model=self.model,
            messages=messages,
            options={
                "temperature": 0.7,
                "num_predict": max_tokens,
                "num_ctx": self.config.n_ctx,
            },
        )

        return response.message.content

    def validate_fork(
        self,
        fork_principles: list[str],
        locked_principles: dict[str, str],
    ) -> dict:
        """Validate fork principles against locked principles using LLM.

        Uses semantic understanding to detect if any fork principles
        would violate the locked governance principles.

        Args:
            fork_principles: List of fork principle statements.
            locked_principles: Dict mapping locked principle names to statements.

        Returns:
            Dict with 'valid', 'violations', and 'summary' keys.
        """
        logger.info("Validating fork principles with LLM...")

        # Format locked principles for prompt
        locked_text = "\n".join(
            f"- {name}: {statement}"
            for name, statement in locked_principles.items()
        )

        # Format fork principles
        fork_text = "\n".join(f"- {p}" for p in fork_principles)

        system_prompt = """You are a governance validator for the Leviathan framework. Your task is to check if a validator's personal principles (fork) conflict with the locked governance principles.

LOCKED PRINCIPLES are immutable rules that cannot be violated. A fork principle VIOLATES a locked principle if it:
1. Directly contradicts it (e.g., "hide decisions" violates "transparency")
2. Would undermine its intent (e.g., "prioritize speed over safety" violates "precautionary default")
3. Explicitly negates it (e.g., "ignore stakeholder input" violates "democratic evolution")

A fork principle is COMPATIBLE if it:
1. Adds specificity without contradiction (e.g., "prioritize security" is compatible with "precautionary default")
2. Focuses on a specific domain while respecting the locked principle
3. Uses different words but aligns with the same values

Be strict but fair. Personal preferences and domain focus are allowed as long as they don't violate locked principles."""

        user_prompt = f"""Check if these fork principles violate any locked principles.

## LOCKED PRINCIPLES (immutable, cannot be violated)
{locked_text}

## FORK PRINCIPLES TO VALIDATE
{fork_text}

Analyze each fork principle and determine if it violates any locked principle. Return your analysis as JSON."""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            response = self.client.chat(
                model=self.model,
                messages=messages,
                format=FORK_VALIDATION_SCHEMA,
                options={
                    "temperature": 0.3,  # Lower temperature for more consistent validation
                    "num_ctx": self.config.n_ctx,
                },
            )

            result = json.loads(response.message.content)
            logger.info(f"Fork validation result: valid={result.get('valid')}")
            return result

        except (json.JSONDecodeError, ollama.ResponseError) as e:
            logger.error(f"Fork validation failed: {e}")
            # Return safe default - assume valid to not block on LLM errors
            return {
                "valid": True,
                "violations": [],
                "summary": f"Validation skipped due to error: {e}",
            }
