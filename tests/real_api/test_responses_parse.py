"""Test for issue #9 - structured output with managed keys using responses.parse endpoint"""
import os
import pytest
import time
import requests
from pydantic import BaseModel
from nacl.signing import SigningKey
from nacl.encoding import HexEncoder
from connectonion import llm_do


class EmailDraft(BaseModel):
    """Email draft with subject and body"""
    subject: str
    body: str


def get_test_token():
    """Generate test auth token for local backend"""
    signing_key = SigningKey.generate()
    public_key = "0x" + signing_key.verify_key.encode(encoder=HexEncoder).decode()
    timestamp = int(time.time())
    message = f"ConnectOnion-Auth-{public_key}-{timestamp}"
    signature = signing_key.sign(message.encode()).signature.hex()

    # Authenticate with local backend
    response = requests.post(
        "http://localhost:8000/api/v1/auth",
        json={
            "public_key": public_key,
            "message": message,
            "signature": signature
        }
    )

    if response.status_code != 200:
        raise Exception(f"Auth failed: {response.status_code} - {response.text}")

    return response.json()["token"]


@pytest.mark.real_api
def test_structured_output_with_managed_keys():
    """Test that llm_do() with Pydantic output works with co/ models.

    This tests the /v1/responses/parse endpoint on the backend.
    """
    # Use local backend for testing
    os.environ["OPENONION_DEV"] = "1"

    # Get auth token
    token = get_test_token()
    os.environ["OPENONION_API_KEY"] = token

    draft = llm_do(
        "Write a friendly hello email to a new colleague",
        output=EmailDraft,
        temperature=0.7,
        model="co/gpt-4o-mini"
    )

    # Verify we got a valid Pydantic model
    assert isinstance(draft, EmailDraft)
    assert isinstance(draft.subject, str)
    assert isinstance(draft.body, str)
    assert len(draft.subject) > 0
    assert len(draft.body) > 0

    print(f"\n✓ Structured output test passed!")
    print(f"Subject: {draft.subject}")
    print(f"Body: {draft.body[:100]}...")


if __name__ == "__main__":
    # Allow running directly for quick testing
    test_structured_output_with_managed_keys()
