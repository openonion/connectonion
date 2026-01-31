"""
ConnectOnion exceptions.

Purpose: Custom exceptions for ConnectOnion framework with formatted, actionable error messages
LLM-Note:
  Dependencies: none | imported by [llm.py] | tested by [tests/test_billing_error_agent.py]
  Data flow: OpenOnionLLM catches openai.APIStatusError(402) → transforms to InsufficientCreditsError → raises with formatted message
  State/Effects: parses error detail from API response | formats beautiful error message with account, balance, cost, shortfall | preserves original error in __cause__
  Integration: exposes InsufficientCreditsError exception class | raised by OpenOnionLLM when insufficient credits
  Performance: lightweight exception creation | formats string message once on init
  Errors: none (this module defines error types)
"""


class InsufficientCreditsError(Exception):
    """
    Raised when an LLM request fails due to insufficient ConnectOnion credits.

    This indicates your ConnectOnion managed keys account needs more credits.
    Join Discord to add credits or ask Aaron for free credits to get started.

    Attributes:
        balance (float): Current account balance in USD
        required (float): Cost of the failed request in USD
        shortfall (float): Additional credits needed in USD
        address (str): Your ConnectOnion account address
    """

    def __init__(self, original_error):
        """
        Create InsufficientCreditsError from OpenAI API error.

        Args:
            original_error: The original openai.APIStatusError from the API
        """
        # Parse error details from API response
        body = getattr(original_error, 'body', {}) or {}
        detail = body.get('detail', {})

        # Extract billing information
        self.balance = detail.get('balance', 0)
        self.required = detail.get('required', 0)
        self.shortfall = detail.get('shortfall', 0)
        self.address = detail.get('address', 'unknown')  # Server provides formatted address
        self.public_key = detail.get('public_key', 'unknown')  # Full public key
        self.original_message = detail.get('message', '')

        # Create clear, beautiful error message
        message = self._format_message()
        super().__init__(message)

        # Keep original error for debugging
        self.__cause__ = original_error

    def _format_message(self):
        """Format a clear, actionable error message."""
        return (
            f"\n"
            f"{'='*70}\n"
            f"❌ Insufficient ConnectOnion Credits\n"
            f"{'='*70}\n"
            f"\n"
            f"Account:     {self.address}\n"
            f"Balance:     ${self.balance:.4f}\n"
            f"Required:    ${self.required:.4f}\n"
            f"Shortfall:   ${self.shortfall:.4f}\n"
            f"\n"
            f"💡 How to add credits:\n"
            f"   • Join Discord: https://discord.gg/4xfD9k8AUF\n"
            f"   • Ask Aaron for free credits to get started\n"
            f"   • Check balance: Run 'co status' in terminal\n"
            f"\n"
            f"{'='*70}\n"
        )
