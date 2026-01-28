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
