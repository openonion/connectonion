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
            f"   • Purchase: https://o.openonion.ai/purchase\n"
            f"   • Check balance: Run 'co status' in terminal\n"
            f"   • Pricing: https://docs.connectonion.com/models/pricing\n"
            f"\n"
            f"{'='*70}\n"
        )


class LLMConnectionError(Exception):
    """
    Raised when the LLM API request times out or fails to connect.

    Common causes: proxy/VPN adding latency, network issues, API server down.
    """

    def __init__(self, original_error, model: str = "unknown", base_url: str = ""):
        self.model = model
        self.base_url = base_url
        self.error_type = type(original_error).__name__

        message = self._format_message()
        super().__init__(message)
        self.__cause__ = original_error

    def _format_message(self):
        return (
            f"\n"
            f"{'='*70}\n"
            f"Connection Failed\n"
            f"{'='*70}\n"
            f"\n"
            f"Model:       {self.model}\n"
            f"Server:      {self.base_url}\n"
            f"Error:       {self.error_type}\n"
            f"\n"
            f"Possible causes:\n"
            f"   - Proxy/VPN slowing down the connection\n"
            f"   - Network connectivity issue\n"
            f"   - API server temporarily unavailable\n"
            f"\n"
            f"Try:\n"
            f"   - Check your internet connection\n"
            f"   - Disable proxy/VPN and retry\n"
            f"   - Run 'curl https://oo.openonion.ai/health' to test\n"
            f"\n"
            f"{'='*70}\n"
        )


class ToolRejectedError(ValueError):
    """Raised when a user rejects a tool execution request."""
