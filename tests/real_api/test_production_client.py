"""Test connectonion client against production API"""
import os
import time
import requests
from pydantic import BaseModel
from nacl.signing import SigningKey
from nacl.encoding import HexEncoder
from connectonion import llm_do


# Production URL
PRODUCTION_URL = "http://3.24.102.245"


class EmailDraft(BaseModel):
    """Email draft with subject and body"""
    subject: str
    body: str


def get_test_token():
    """Generate test auth token for production backend"""
    signing_key = SigningKey.generate()
    public_key = "0x" + signing_key.verify_key.encode(encoder=HexEncoder).decode()
    timestamp = int(time.time())
    message = f"ConnectOnion-Auth-{public_key}-{timestamp}"
    signature = signing_key.sign(message.encode()).signature.hex()

    response = requests.post(
        f"{PRODUCTION_URL}/api/v1/auth",
        json={
            "public_key": public_key,
            "message": message,
            "signature": signature
        }
    )

    if response.status_code != 200:
        raise Exception(f"Auth failed: {response.status_code} - {response.text}")

    return response.json()["token"]


def test_production_llm_do_structured():
    """Test llm_do() with structured output against production API"""
    print("\n" + "=" * 80)
    print("TESTING CONNECTONION CLIENT AGAINST PRODUCTION")
    print(f"Target: {PRODUCTION_URL}")
    print("=" * 80)

    # Point to production instead of localhost
    os.environ["OPENONION_API_URL"] = PRODUCTION_URL

    # Get auth token from production
    token = get_test_token()
    os.environ["OPENONION_API_KEY"] = token

    print("\n✓ Authentication successful")
    print(f"  Using production API: {PRODUCTION_URL}")

    # Test structured output with co/ model
    print("\nTesting llm_do() with structured output (EmailDraft)...")
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

    print("\n✓ Structured output test PASSED!")
    print(f"  Subject: {draft.subject}")
    print(f"  Body preview: {draft.body[:150]}...")

    print("\n" + "=" * 80)
    print("✅ CONNECTONION CLIENT WORKS WITH PRODUCTION API!")
    print("   Issue #9 is fully resolved in production")
    print("=" * 80)


if __name__ == "__main__":
    try:
        test_production_llm_do_structured()
    except Exception as e:
        print(f"\n❌ Production client test failed: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
