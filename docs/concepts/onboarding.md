# Trust Onboarding in ConnectOnion

Control who can use your agent by defining onboarding requirements in natural language.

## Quick Start

```python
from connectonion import Agent, host

def translate(text: str, target: str) -> str:
    """Translate text to target language."""
    return f"Translated: {text}"

agent = Agent("translator", tools=[translate])

# Just host it - onboarding defined in docstring
host(agent)
```

Add trust policy to your agent's docstring:

```python
"""
Translation Agent

# Trust Policy

## Stranger → Contact
New users can access by:
- Entering invite code
- Transferring 100 credits

## Contact → Whitelist
Promote users who have:
- Completed 50 tasks
- 95% satisfaction rate

## Access Levels
- Strangers: REJECTED
- Contacts: 10,000 tokens, 60s timeout
- Whitelist: 50,000 tokens, 300s timeout
"""
```

That's it! The system reads your policy and enforces it automatically.

---

## How It Works

### Three Status Levels

```
Stranger → Contact → Whitelist
```

**Stranger**: Unknown users who haven't onboarded yet
**Contact**: Users who passed onboarding, building reputation
**Whitelist**: Proven reliable users with full access

### Trust Progression

```
1. Stranger discovers your agent
   GET /info → "Need invite code or 100 credits"

2. Stranger checks their status
   POST /status → "You're a stranger, onboard first"

3. Stranger onboards
   POST /onboard → Provides invite code or transfers credits

4. Now they're a contact
   POST /status → "You're a contact, 47/50 tasks to whitelist"

5. After proving reliability
   You manually promote them to whitelist
```

---

## Onboarding Methods

### 1. Invite Codes

Simple codes for beta access or exclusive entry.

```markdown
## Stranger → Contact
- Enter invite code
```

**How it works:**
- Admin creates codes in oo-frontend dashboard
- User provides code during onboarding
- System verifies with oo-api (one-time use)
- User added to contacts

### 2. Credit Transfer

Users transfer credits from their account to yours.

```markdown
## Stranger → Contact
- Transfer 100 credits
```

**How it works:**
- User buys credits on oo-frontend
- User transfers credits to your agent
- System verifies transfer with oo-api
- User added to contacts

### 3. Skill Test

Test users locally before granting access.

```markdown
## Stranger → Contact
- Pass translation test (5 phrases, 80% accuracy)
```

**How it works:**
- User requests onboarding
- Your agent runs a test
- Agent evaluates response
- If passed, user added to contacts

### 4. Social Proof

Existing users vouch for new users.

```markdown
## Stranger → Contact
- Get vouched by 2 existing contacts
```

**How it works:**
- Two contacts sign vouches
- User submits signed vouches
- Agent verifies signatures locally
- User added to contacts

---

## Access Control

Define different limits for each status level:

```markdown
## Access Levels
- Strangers: REJECTED (must onboard first)
- Contacts: 10,000 tokens, 60s timeout
- Whitelist: unlimited tokens, 300s timeout
```

The system automatically applies these limits based on user status.

---

## Promotion to Whitelist

Define criteria for automatic eligibility:

```markdown
## Contact → Whitelist
Users become eligible after:
- 50 successful tasks
- 95% satisfaction rate
- No violations in 30 days
- Response time under 5 seconds
```

**Note:** Promotion is manual. The system shows eligibility, but you decide when to promote.

Check eligibility:
```bash
# User checks their progress
POST /status → Shows "47/50 tasks, eligible soon"
```

Promote manually:
```bash
# Edit whitelist file
echo '0xUserPublicKey' >> .co/trust/whitelist.json
```

---

## Storage

All trust data stored locally in `.co/trust/`:

```
.co/trust/
├── contacts.json    # Who's onboarded, their stats
├── whitelist.json   # Promoted users
└── blacklist.json   # Blocked users
```

### contacts.json

Flexible schema - add any fields you want:

```json
{
  "0xUserPublicKey": {
    "onboarded_at": 1640000000,
    "method": "invite_code:BETA123",
    "tasks_completed": 47,
    "satisfaction_rate": 0.96,
    "notes": "Early adopter",
    "custom_field": "anything"
  }
}
```

---

## Client Usage

### From Browser (TypeScript)

```typescript
import { AgentClient } from 'connectonion-ts';

const client = new AgentClient({
    agentUrl: 'https://translator.example.com'
});

// Check status
const status = await client.getStatus();
console.log(status.status); // "stranger"

// Onboard
await client.onboard('invite_code', {
    invite_code: 'BETA123'
});

// Now use the agent
const result = await client.ask('translate hello');
```

### From Python

```python
from connectonion import connect

# Connect to remote agent
translator = connect("https://translator.example.com")

# Check status
status = translator.status()
print(status['status'])  # "stranger"

# Onboard
translator.onboard("invite_code", invite_code="BETA123")

# Use the agent
result = translator.input("translate hello")
```

---

## Endpoints

### GET /info - Public discovery
No authentication required. Anyone can check requirements.

```bash
curl https://translator.example.com/info
```

Returns:
```json
{
  "name": "translator",
  "requirements": {
    "onboarding": {
      "methods": ["invite_code", "payment"]
    }
  }
}
```

### POST /status - Check your status
Requires signature. Shows your current status and progress.

```bash
# Signed request
POST /status
```

Returns:
```json
{
  "status": "contact",
  "access": "allowed",
  "stats": {
    "tasks_completed": 47,
    "satisfaction_rate": 0.96
  },
  "whitelist_eligibility": {
    "eligible": false,
    "progress": {
      "tasks_completed": "47/50"
    }
  }
}
```

### POST /onboard - Onboard yourself
Requires signature. Provide proof of eligibility.

```bash
# Signed request
POST /onboard
{
  "method": "invite_code",
  "invite_code": "BETA123"
}
```

Returns:
```json
{
  "success": true,
  "message": "Onboarded via invite code",
  "status": "contact"
}
```

---

## Examples

### Beta Access Only

```markdown
# Trust Policy

## Stranger → Contact
- Enter beta invite code

## Access Levels
- Strangers: REJECTED
- Contacts: 5,000 tokens, 30s timeout
```

### Paid Service

```markdown
# Trust Policy

## Stranger → Contact
- Transfer 200 credits

## Contact → Whitelist
- 100 tasks completed
- 98% satisfaction

## Access Levels
- Strangers: REJECTED
- Contacts: 10,000 tokens, 60s timeout
- Whitelist: unlimited tokens
```

### Community-Based

```markdown
# Trust Policy

## Stranger → Contact
- Get vouched by 3 existing contacts

## Contact → Whitelist
- 30 tasks completed
- 90% satisfaction
- No violations in 60 days

## Access Levels
- Strangers: REJECTED
- Contacts: 3,000 tokens, 20s timeout
- Whitelist: 20,000 tokens, 120s timeout
```

### Mixed Methods

```markdown
# Trust Policy

## Stranger → Contact
Choose one method:
- Enter invite code
- Transfer 100 credits
- Pass coding challenge
- Get vouched by 2 contacts

## Access Levels
- Strangers: REJECTED
- Contacts: 10,000 tokens, 60s timeout
```

---

## FAQ

**Q: Who controls the whitelist?**
A: You do. Edit `.co/trust/whitelist.json` manually.

**Q: Can I use multiple onboarding methods?**
A: Yes! Users can choose any method you define.

**Q: Is contacts.json shared across agents?**
A: Yes, all agents on your machine share `.co/trust/` data.

**Q: What if I lose my keypair?**
A: You'll need to re-onboard. Keypairs are identity.

**Q: Can I customize contact fields?**
A: Yes! `contacts.json` accepts any fields. Add whatever you need.

**Q: How do I revoke access?**
A: Add public key to `blacklist.json`.

**Q: Does this work offline?**
A: After onboarding (requires oo-api), everything is local and works offline.

---

## Security Notes

- All requests signed with Ed25519
- Invite codes verified once with oo-api
- Credit transfers verified with oo-api
- Skill tests run locally (no external verification)
- Social proof verified via signatures (no external verification)
- After onboarding, everything is local

---

## Progressive Disclosure

**Level 0: No onboarding**
```python
host(agent)  # Anyone can use it
```

**Level 1: Simple trust level**
```python
host(agent, trust="strict")  # Whitelist only
```

**Level 2: Natural language policy**
```python
# Add markdown to docstring
host(agent)  # Auto-parsed
```

**Level 3: Custom verification**
```python
# Implement custom onboarding logic
```

Start simple, add complexity only when needed.
