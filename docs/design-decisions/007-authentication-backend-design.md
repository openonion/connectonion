# Why We Chose Client-Side Challenges for Authentication

*September 2025*

When building the authentication system for ConnectOnion's managed keys, we faced a fundamental question: How do we verify that someone owns a private key without ever seeing that private key? This led us to a surprisingly simple solution that goes against conventional wisdom.

## The Problem: Public Keys Are... Public

We use Ed25519 public keys as addresses (like `0x3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c`). But here's the thing - anyone can see a public key. It's public! 

So how do we authenticate users based on something everyone can see?

The naive approach would be:
```python
# WRONG - Don't do this!
POST /auth
{ "public_key": "0x3d40...660c" }
→ Returns JWT token

# Why is this wrong? 
# Anyone could get a token for ANY public key!
```

## The Standard Solution (That We Didn't Use)

Most authentication systems use server-generated challenges:

```python
# Step 1: Get challenge from server
POST /auth/challenge
{ "public_key": "0x3d40...660c" }
→ { "challenge": "random_nonce_abc123" }

# Step 2: Sign it and send back
POST /auth/verify  
{
  "public_key": "0x3d40...660c",
  "challenge": "random_nonce_abc123",
  "signature": "signed_abc123"
}
→ { "token": "jwt_token" }
```

This works! It's secure! It's also... complicated:
- Two API calls for every authentication
- Server needs to store challenges temporarily
- Need to track challenge sessions
- Handle challenge expiry
- Clean up old challenges
- Deal with race conditions

We spent a week building this. Then we asked: "Why are we making this so complicated?"

## The Revelation: Let Clients Create Their Own Challenges

Here's our "aha" moment: **The challenge doesn't need to be random, it just needs to be unique and recent.**

The client can create their own challenge using a timestamp:

```python
# Client side
timestamp = int(time.time())
message = f"ConnectOnion-Auth-{public_key}-{timestamp}"
signature = private_key.sign(message)

# One API call
POST /auth
{
  "public_key": "0x3d40...660c",
  "message": "ConnectOnion-Auth-0x3d40...660c-1701234567",
  "signature": "abc123..."
}
→ { "token": "jwt_token" }
```

## Why This Is Secure

**"But wait!"** you might say. **"If clients create their own challenges, can't they cheat?"**

No! Here's why:

1. **Only the private key owner can create valid signatures**
   - The math of Ed25519 ensures this
   - You can verify with public key, but can't forge without private key

2. **Timestamps prevent replay attacks**
   - Server rejects messages older than 5 minutes
   - Can't reuse old signatures

3. **No secrets involved**
   - Timestamp isn't secret
   - Public key isn't secret
   - Only the signature proves ownership

## The Complete Implementation

Here's our entire authentication flow:

**Client:**
```python
import time
from nacl.signing import SigningKey

def authenticate(private_key: SigningKey, server_url: str):
    public_key = "0x" + private_key.verify_key.encode().hex()
    timestamp = int(time.time())
    message = f"ConnectOnion-Auth-{public_key}-{timestamp}"
    
    signature = private_key.sign(message.encode()).signature
    
    response = requests.post(f"{server_url}/auth", json={
        "public_key": public_key,
        "message": message,
        "signature": signature.hex()
    })
    
    return response.json()["token"]
```

**Server:**
```python
from fastapi import FastAPI, HTTPException
from nacl.signing import VerifyKey
import jwt
import time

app = FastAPI()

@app.post("/auth")
def authenticate(public_key: str, message: str, signature: str):
    # Extract and verify timestamp (prevent replay attacks)
    timestamp = int(message.split("-")[-1])
    if abs(time.time() - timestamp) > 300:  # 5 minute window
        raise HTTPException(400, "Message expired")
    
    # Verify signature (proves private key ownership)
    verify_key = VerifyKey(bytes.fromhex(public_key[2:]))
    verify_key.verify(message.encode(), bytes.fromhex(signature))
    
    # Create JWT token (valid for 24 hours)
    token = jwt.encode(
        {"public_key": public_key, "exp": time.time() + 86400},
        "your-secret-key",
        algorithm="HS256"
    )
    
    return {"token": token}
```

## Why JWT After Authentication?

Once you've proven you own the private key, we give you a JWT token. Why?

**Without JWT:** Every API call needs signature verification (slow)
**With JWT:** Verify signature once, then use fast token validation

The JWT is just a performance optimization. The real security comes from the signature verification.

## Security Analysis

### What Attacks Does This Prevent?

1. **Impersonation**: Can't create signatures without private key ✓
2. **Replay**: Timestamps expire after 5 minutes ✓
3. **Man-in-the-middle**: Signatures are bound to specific message ✓
4. **Token theft**: JWTs expire after 24 hours ✓

### What About These Concerns?

**Q: "Timestamps aren't random! Isn't that less secure?"**
A: Randomness prevents prediction, but we don't need unpredictability here. We need uniqueness and recency, which timestamps provide.

**Q: "Client controls the timestamp! Can't they lie?"**
A: They can only lie by ±5 minutes. Doesn't help them. Old signatures are rejected, future signatures are rejected.

**Q: "What if clocks are out of sync?"**
A: 5-minute window handles normal clock drift. For serious drift, NTP exists.

## Comparison: Server vs Client Challenges

| Aspect | Server Challenge | Client Challenge (Our Choice) |
|--------|-----------------|------------------------------|
| API Calls | 2 (challenge + verify) | 1 (just verify) |
| Server Storage | Required (sessions) | None |
| Complexity | Medium | Simple |
| Code Lines | ~100 | ~20 |
| Stateless | No | Yes |
| Security | ✓ Secure | ✓ Equally secure |

## Real-World Validation

After implementing this, we discovered we're not alone:
- **Discord** uses client-signed timestamps for bot authentication
- **Telegram** uses similar client-generated challenges
- **Many Web3 apps** use "Sign this message with timestamp" patterns

The industry has quietly converged on this pattern because it works.

## Implementation Tips

### For ConnectOnion SDK Users

```python
from connectonion import authenticate

# It just works - complexity hidden
token = authenticate()  # Uses local keys from ~/.co/keys/
```

### For Direct API Users

```bash
# Generate signature with your tool of choice
TIMESTAMP=$(date +%s)
MESSAGE="ConnectOnion-Auth-${PUBLIC_KEY}-${TIMESTAMP}"
SIGNATURE=$(echo -n $MESSAGE | sodium sign)

# Single POST request
curl -X POST https://api.openonion.ai/auth \
  -H "Content-Type: application/json" \
  -d "{
    \"public_key\": \"$PUBLIC_KEY\",
    \"message\": \"$MESSAGE\",
    \"signature\": \"$SIGNATURE\"
  }"
```

## The Bottom Line

We chose client-generated challenges because:
- ✅ It's simpler (1 API call vs 2)
- ✅ It's stateless (no session storage)
- ✅ It's secure (cryptographically sound)
- ✅ It's proven (Discord, Telegram use similar patterns)

Sometimes the best solution isn't the most sophisticated one. It's the one that does exactly what you need, nothing more, nothing less.

---

*Remember: Keep simple things simple. That's the ConnectOnion way.*