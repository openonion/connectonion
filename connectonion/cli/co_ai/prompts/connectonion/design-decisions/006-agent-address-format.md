# The Great Address Debate: How We Chose Agent Identity for ConnectOnion

*September 3, 2025*

When building ConnectOnion, we faced a fundamental question: How should agents identify themselves? This seemingly simple decision led us down a fascinating rabbit hole of cryptography, user experience, and philosophical debates about simplicity. Here's the story of how we landed on our solution.

## The Journey Begins: What Even Is an Address?

We started with a simple need: agents in our network need unique identifiers to communicate. Like phone numbers or email addresses, but for AI agents. 

Our first instinct? Look at what's already working. Ethereum uses addresses like `0x742d35Cc6634C0532925a3b844Bc454e3b6a5f8e`. Millions of people recognize this format. MetaMask has trained an entire generation. Surely we should just use that?

But then we dug deeper.

## The Cryptocurrency Temptation

The allure was strong:
- **Ethereum addresses** = instant payment capability
- **MetaMask** = ready-made wallet infrastructure  
- **Web3** = built-in monetization for agents

We could have agents that earn money from day one! An agent completes a translation task, receives USDC. Beautiful.

But wait. Ethereum addresses are actually *hashes* of public keys. You can't recover the public key from the address. For our messaging protocol, this means every message needs to include the public key separately. That's 64 extra bytes per message. Forever.

## The Performance Reality Check

We ran the numbers on signature verification:
- **Ed25519**: 70,000 signatures/second
- **Secp256k1** (Ethereum): 20,000 signatures/second

For a network of AI agents exchanging thousands of messages, this 3x difference matters. Ed25519 is what Signal uses. What WhatsApp uses. What modern messaging systems use.

But Ed25519 isn't compatible with Ethereum. We had to choose: payments or performance?

Honestly? This hurt. We wanted both. We spent weeks trying to have our cake and eat it too. "What if we use both keys?" "What if we create a Merkle tree?" "What if we..."

Every solution made things more complex. And complex is where bugs live.

## The Solana Detour

"What about Solana?" we thought. They use Ed25519. They have Base58 addresses like `5FHneW46xGXNe3mZRwtFJNYiSqJ8RXkPmpnfWUrmTWVv`.

The good:
- Fast signatures
- The address IS the public key (no extra bytes needed)
- Growing ecosystem

The bad:
- Case-sensitive (type one letter wrong = funds lost)
- No error detection built-in
- MetaMask doesn't support it
- Looks foreign to most users

We spent days researching this. Reading Solana's design docs. Looking at adoption numbers. The more we dug, the more we found developers complaining about the same things we worried about.

We kept searching.

## The Revelation: Modern Chains Are Doing Something Different

We discovered that Aptos (from Meta's blockchain team) uses something elegant:

```
0x3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c
```

It's just... the hex-encoded Ed25519 public key. No hashing. No information loss. The address IS the public key.

This was our "aha" moment.

## Comparing Our Options

Here's what we considered:

| Format | Example | Pros | Cons |
|--------|---------|------|------|
| **Ethereum** | `0x742d35Cc6634C0532925a3b844Bc454e3b6a5f8e` | • Instant payments<br>• MetaMask works<br>• Familiar | • 3x slower signatures<br>• Need extra 64 bytes per message<br>• Hash loses information |
| **Solana (Base58)** | `5FHneW46xGXNe3mZRwtFJNYiSqJ8RXkPmpnfWUrmTWVv` | • Fast Ed25519<br>• Address = public key<br>• Compact | • Case-sensitive<br>• No error detection<br>• Foreign to users |
| **Our Choice (Hex Ed25519)** | `0x3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c` | • Fast Ed25519<br>• Familiar format<br>• Address = public key<br>• Simple | • Longer (66 chars)<br>• No direct ETH payments |

## Our Solution: Familiar Format, Honest Content

We chose hex-encoded Ed25519 public keys with a 0x prefix:

```
0x3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c
```

Why this works:
1. **Looks familiar** - Users see "0x" and think "crypto address" 
2. **No magic** - The address IS the public key (not some hash of a hash of a thing)
3. **Fast verification** - Ed25519 performance (70,000 signatures/sec)
4. **Developer-friendly** - `bytes.fromhex(address[2:])` gives you the public key

Yes, it's longer than Ethereum addresses (66 vs 42 characters). But in exchange, we get transparency and performance.

And here's the beautiful part - when developers eventually discover what these addresses are, there's no disappointment. It's not a "fake" Ethereum address. It's not a proprietary format. It's literally just a hex-encoded public key. Nothing special. Nothing hidden. Just honest, boring cryptography that works.

## The User Confusion Problem

We realized we were overthinking from a developer's perspective. Most users coming to ConnectOnion think:
- "I want to build a chatbot"
- "I want to automate my browser"
- "I want an AI assistant"

NOT:
- "I need a cryptographic identity"
- "I need to manage keys"
- "I need an address for my agent"

This hit us during user testing. A developer was trying our framework for the first time. They ran `co init`, saw "Generated agent address: 0x742d35..." and immediately asked:

"Do I need MetaMask for this?"
"No, it's just for agent identity."
"So... where do I put this address?"
"You don't, it's automatic."
"Then why are you showing it to me?"

Silence.

That's when we knew we'd been building for ourselves, not our users.

## The UX Breakthrough: Silent Generation

Then came our biggest realization: **Most users don't need to see addresses at all.**

We had a long debate about this. The crypto side of our brain said: "Users need to see their keys! They need to save recovery phrases! Security! Ownership!"

But the developer tool side argued back: "They're building a Hello World agent. They'll quit if we throw 12 words at them to write down."

The solution? Generate everything silently in the background. No questions asked. No decisions required.

When you run `co init`, we silently generate an identity in the background. It's saved in `.co/keys/`. The user never sees it unless they need networking later.

```bash
$ co init
✅ ConnectOnion project initialized!

Next steps:
1. Add your OpenAI API key
2. Run: python agent.py
```

No addresses. No recovery phrases. No confusion.

"But what about security?" you might ask. Here's the thing - the keys are still there, encrypted and safe in `.co/keys/`. The recovery phrase is saved (yes, we know that's controversial, but pragmatism won). If users want to see them later, they can. But 90% never will, and that's fine.

Later, IF they need agent networking:

```bash
$ co network status
Agent address: 0x3d40...660c
```

Progressive disclosure. Complexity revealed only when needed.

## The Philosophy: Keep Simple Things Simple

This journey taught us something fundamental about ConnectOnion's philosophy:

**Don't make users think about things they don't need to think about.**

Think about it - when you install Git, it doesn't ask you to generate SSH keys immediately. When you create a Python project, pip doesn't demand you set up PyPI credentials. These things come later, when you actually need them.

Why were we different? Why were we throwing cryptographic addresses at someone who just wanted to print "Hello World" from an agent?

- Building an agent ≠ Understanding cryptography
- Writing tools ≠ Managing network identities  
- Getting started ≠ Making irreversible decisions

We generate a cryptographically secure identity for every agent, but we don't burden new users with understanding it. It's there when they need it, invisible when they don't.

## The Technical Details (For the Curious)

For those who care about the implementation:

1. **Seed phrase generation**: 12 BIP39 words for recovery
2. **Key derivation**: Ed25519 from seed for fast signatures
3. **Address format**: "0x" + hex(public_key)
4. **Storage**: Encrypted in .co/keys/
5. **Display**: Truncated (0x3d40...660c) for readability

The address can't receive Ethereum payments (it's not a real Ethereum address), but that's okay. If users need payments later, we can add that as a separate feature.

## What We Learned

The perfect solution isn't always the most technically advanced or the most feature-rich. Sometimes it's the one that:

1. **Works silently** - Generate complexity, don't expose it
2. **Looks familiar** - Use patterns people recognize
3. **Stays honest** - Don't pretend to be something you're not
4. **Scales gracefully** - From simple to complex use cases

## The Bigger Picture

This decision reflects ConnectOnion's core values:

- **Simplicity first** - Start simple, add complexity only when needed
- **Developer respect** - Make the internals clear and hackable
- **User empathy** - Don't make users learn new concepts unnecessarily
- **Technical honesty** - Choose the right tool, not the popular one

We could have chosen Ethereum compatibility for the hype. We could have chosen Solana style for the tech cred. Instead, we chose what actually works best for our users.

## The Key Realization: We're Not a Crypto Project

This was perhaps our most important insight. We kept trying to force cryptocurrency concepts onto an AI agent framework. But we're not building a blockchain. We're not creating a token. We're building a tool for developers to create AI agents.

The moment of clarity came during a late-night discussion:

"Why are we optimizing for payments?"
"Because... that's what everyone expects?"
"But our users are building chatbots and automation tools."
"So why are we making them think about wallets?"
"..."

Once we accepted this, everything became clearer:
- We don't need payment addresses (that's a separate problem)
- We don't need MetaMask compatibility (we're not doing transactions)
- We don't need to follow blockchain conventions (we can do better)

We're an AI agent network. Our priorities are different:
- **Developer simplicity** > Token economics
- **Fast messaging** > Payment rails
- **Progressive disclosure** > Upfront complexity

It's okay to not be Web3. It's okay to just be a good developer tool.

## Moving Forward

Will this decision limit us? Maybe. Can't receive ETH directly. Can't use MetaMask natively. But that's okay because we're building an agent network, not a cryptocurrency.

And for an agent network, what matters is:
- Fast message verification (Ed25519 ✓)
- Simple addressing (hex encoding ✓)
- Progressive complexity (silent generation ✓)
- Future flexibility (can add payment layers ✓)

The best technical decision was admitting what we are and what we're not. We're ConnectOnion, not ConnectCoin.

## The Code That Makes It Work

For the technically curious, here's the elegantly simple implementation:

```python
from nacl.signing import SigningKey
from mnemonic import Mnemonic

def create_agent():
    # Generate seed phrase (but don't show it)
    mnemo = Mnemonic("english")
    seed_phrase = mnemo.generate(strength=128)
    seed = mnemo.to_seed(seed_phrase)
    
    # Derive Ed25519 key (fast!)
    signing_key = SigningKey(seed[:32])
    
    # Create address (just hex-encoded public key)
    address = "0x" + signing_key.verify_key.encode().hex()
    
    # Save silently to .co/keys/
    save_identity(address, signing_key, seed_phrase)
    
    # User never sees this complexity
    return address  # Only shown when needed
```

## The Final Balance

After all this exploration, here's what we learned about balancing transparency and user-friendliness:

**What we show users:**
- Nothing on init (just works)
- Truncated address when networking (0x3d40...660c)
- Full address only when explicitly requested

**What we tell developers who dig deeper:**
- It's just a hex-encoded Ed25519 public key
- Nothing special, nothing proprietary
- You can verify signatures directly from the address
- Yes, we save the recovery phrase locally (pragmatism > dogma)

**The trade-offs we accepted:**
- Can't receive ETH directly → That's fine, we're not a wallet
- Recovery phrase saved locally → Controversial but practical
- No MetaMask support → We're not doing blockchain transactions
- Silent key generation → Users who don't need it never see it

## The Lesson

Building developer tools is an exercise in hidden complexity. The best hammer doesn't explain metallurgy; it just drives nails.

Our agent addresses work the same way. They're cryptographically secure, network-ready, and performance-optimized. But most importantly, they're invisible until you need them.

That's not a compromise. That's design.

The irony? We spent three months debating address formats, only to realize the best solution was to not show them at all. Sometimes the hardest technical decisions lead to the simplest user experiences.

---

*Want to build an agent? Just run `co init`. No addresses required.*

*Want to connect agents? The address is already there, waiting.*

*That's the ConnectOnion way: Keep simple things simple, make complicated things possible.*