# ConnectOnion Network Tests

Tests for agent network features (serve and connect).

## Configuration

Tests use **production relay server** by default: `wss://oo.openonion.ai/ws/announce`

### Override Relay URL

```bash
# Use local relay server
RELAY_URL=ws://localhost:8000/ws/announce python tests/test_serve.py

# Use custom relay
RELAY_URL=ws://custom.server:8000/ws/announce python tests/test_serve.py
```

## Manual Tests

### Test Serving Agent

Start an agent that serves on the relay network:

```bash
# Use production relay (default)
python tests/test_serve.py

# Use local relay
RELAY_URL=ws://localhost:8000/ws/announce python tests/test_serve.py
```

The agent will:
1. Load or generate Ed25519 keys from `.co/`
2. Connect to relay server
3. Send ANNOUNCE message
4. Wait for INPUT messages
5. Send heartbeat every 60s

Press Ctrl+C to stop.

### Test Connecting to Agent

Connect to a remote agent and send a request:

```bash
# Use production relay (default)
python tests/test_connect.py <agent-address>

# Use local relay
RELAY_URL=ws://localhost:8000/ws/announce python tests/test_connect.py <agent-address>
```

Example:
```bash
python tests/test_connect.py 0xd5f4b57815bd62c715c9efaa8b9aa5e74bff0f6a1e8b4090f8127cb19faacace
```

## Pytest Configuration

The `conftest.py` file provides:

- `relay_url` fixture - Production relay URL (default)
- `local_relay_url` fixture - Local relay URL for development
- `test_agent` fixture - Test agent with search tool

### Command Line Options

```bash
# Use custom relay URL
pytest tests/ --relay-url=ws://custom:8000/ws/announce

# Use local relay
pytest tests/ --use-local-relay
```

## Environment Variables

- `RELAY_URL` - Override default relay server URL
- `OPENAI_API_KEY` - OpenAI API key (required)
- `ANTHROPIC_API_KEY` - Anthropic API key (optional)
- `GEMINI_API_KEY` - Google Gemini API key (optional)

## API Keys

Make sure to comment out `OPENONION_API_KEY` in `.env` if you want to use real API keys:

```bash
# .env file
OPENAI_API_KEY=sk-...

# Comment this out to use real API keys
# OPENONION_API_KEY=...
```
