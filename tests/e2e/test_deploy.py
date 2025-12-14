"""
E2E test for deploying ConnectOnion agents to production.

This test uses the connectonion deploy infrastructure to deploy a real agent
and verify it's running.

Run:
    # Deploy and print URL (doesn't delete - for manual testing)
    DEPLOY_API_URL=https://oo.openonion.ai pytest tests/e2e/test_deploy.py::test_deploy_manual -v -s

    # Full cycle: deploy → verify → delete
    DEPLOY_API_URL=https://oo.openonion.ai pytest tests/e2e/test_deploy.py::test_deploy_and_cleanup -v -s
"""

import io
import os
import tarfile
import tempfile
import time
import uuid
import pytest
import requests

from connectonion.cli.commands.deploy_commands import API_BASE


pytestmark = [
    pytest.mark.e2e,
    pytest.mark.deploy,
    pytest.mark.skipif(
        not os.getenv("DEPLOY_API_URL"),
        reason="Set DEPLOY_API_URL to run deploy tests"
    ),
]


def get_auth_token(api_url: str) -> str:
    """Authenticate and get JWT token using test keys."""
    from nacl.signing import SigningKey
    from nacl.encoding import HexEncoder

    private_key = "a" * 64
    signing_key = SigningKey(private_key, encoder=HexEncoder)
    public_key = signing_key.verify_key.encode(encoder=HexEncoder).decode()

    timestamp = int(time.time())
    message = f"ConnectOnion-Auth-{public_key}-{timestamp}"
    signed = signing_key.sign(message.encode())
    signature = signed.signature.hex()

    response = requests.post(
        f"{api_url}/api/v1/auth",
        json={"public_key": public_key, "signature": signature, "message": message},
        timeout=10,
    )
    return response.json().get("token")


def create_agent_tarball() -> io.BytesIO:
    """Create a deployable ConnectOnion agent tarball.

    Uses host(agent) which provides:
    - /input, /sessions, /health, /info, /docs, /ws endpoints
    - Interactive docs UI at /docs
    - P2P relay connection
    """
    tarball = io.BytesIO()

    with tarfile.open(fileobj=tarball, mode="w:gz") as tar:
        agent_code = '''"""ConnectOnion agent hosted with host()."""
import os
from connectonion import Agent, host

def calculator(expression: str) -> float:
    """Calculate math expression. Args: expression - e.g. '5*5'"""
    return eval(expression)

def get_time() -> str:
    """Get current UTC time."""
    from datetime import datetime
    return datetime.utcnow().isoformat() + "Z"

agent = Agent(
    name="test-agent",
    tools=[calculator, get_time],
    system_prompt="Use calculator for math, get_time for time.",
    model="co/gemini-2.5-flash",
    quiet=True,
)

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    host(agent, port=port, trust="open")
'''
        info = tarfile.TarInfo(name="agent.py")
        content = agent_code.encode()
        info.size = len(content)
        tar.addfile(info, io.BytesIO(content))

        req = b"connectonion\n"
        info = tarfile.TarInfo(name="requirements.txt")
        info.size = len(req)
        tar.addfile(info, io.BytesIO(req))

    tarball.seek(0)
    return tarball


def wait_for_running(api_url: str, deployment_id: str, headers: dict, timeout: int = 180) -> dict:
    """Wait for deployment to be running."""
    start = time.time()
    while time.time() - start < timeout:
        response = requests.get(
            f"{api_url}/api/v1/deploy/{deployment_id}/status",
            headers=headers,
            timeout=10,
        )
        if response.status_code == 200:
            status = response.json().get("status", {})
            if status.get("running"):
                return status
        time.sleep(5)
        print(".", end="", flush=True)

    raise TimeoutError(f"Deployment not running after {timeout}s")


@pytest.fixture
def api_url():
    return os.getenv("DEPLOY_API_URL", API_BASE)


@pytest.fixture
def auth_headers(api_url):
    token = get_auth_token(api_url)
    return {"Authorization": f"Bearer {token}"}


def test_deploy_manual(api_url):
    """Deploy agent and print URL for manual testing.

    Does NOT delete the deployment - use for manual testing.
    Uses auth token as OPENONION_API_KEY for the deployed agent.
    """
    # Get auth token - this is also the OPENONION_API_KEY
    auth_token = get_auth_token(api_url)
    auth_headers = {"Authorization": f"Bearer {auth_token}"}

    project_name = f"manual-test-{uuid.uuid4().hex[:8]}"
    tarball = create_agent_tarball()

    # Pass auth token as OPENONION_API_KEY for the deployed container
    secrets = f"OPENONION_API_KEY={auth_token}"

    print(f"\nDeploying {project_name}...")
    response = requests.post(
        f"{api_url}/api/v1/deploy",
        files={"package": ("agent.tar.gz", tarball, "application/gzip")},
        data={
            "project_name": project_name,
            "entrypoint": "agent.py",
            "secrets": secrets,
        },
        headers=auth_headers,
        timeout=300,  # Deploy can take several minutes
    )
    assert response.status_code == 200, f"Deploy failed: {response.text}"

    result = response.json()
    deployment_id = result.get("id")
    url = result.get("url")

    print(f"Deployment ID: {deployment_id}")
    print("Waiting for running", end="")
    wait_for_running(api_url, deployment_id, auth_headers)

    print(f"\n\n{'='*60}")
    print("AGENT DEPLOYED!")
    print(f"{'='*60}")
    print(f"URL: {url}")
    print(f"ID:  {deployment_id}")
    print(f"\nTest commands:")
    print(f"  curl {url}/health")
    print(f'  curl -X POST {url}/chat -H "Content-Type: application/json" -d \'{{"message": "what is 5*5?"}}\'')
    print(f"\nTo delete:")
    print(f"  curl -X DELETE {api_url}/api/v1/deploy/{deployment_id} -H 'Authorization: ...'")
    print(f"{'='*60}\n")


def test_deploy_and_cleanup(api_url):
    """Full E2E: deploy → verify → delete → verify gone."""
    # Get auth token - this is also the OPENONION_API_KEY
    auth_token = get_auth_token(api_url)
    auth_headers = {"Authorization": f"Bearer {auth_token}"}

    project_name = f"e2e-test-{uuid.uuid4().hex[:8]}"
    tarball = create_agent_tarball()
    deployment_id = None

    # Pass auth token as OPENONION_API_KEY for the deployed container
    secrets = f"OPENONION_API_KEY={auth_token}"

    # 1. Deploy
    print(f"\n1. Deploying {project_name}...")
    response = requests.post(
        f"{api_url}/api/v1/deploy",
        files={"package": ("agent.tar.gz", tarball, "application/gzip")},
        data={
            "project_name": project_name,
            "entrypoint": "agent.py",
            "secrets": secrets,
        },
        headers=auth_headers,
        timeout=300,
    )
    assert response.status_code == 200, f"Deploy failed: {response.text}"

    result = response.json()
    deployment_id = result.get("id")
    url = result.get("url")
    print(f"   ID: {deployment_id}")
    print(f"   URL: {url}")

    # 2. Wait for running
    print("2. Waiting for running", end="")
    wait_for_running(api_url, deployment_id, auth_headers)
    print(" OK")

    # 3. Delete
    print("3. Deleting...")
    response = requests.delete(
        f"{api_url}/api/v1/deploy/{deployment_id}",
        headers=auth_headers,
        timeout=30,
    )
    assert response.status_code == 200, f"Delete failed: {response.text}"
    print("   Deleted")

    # 4. Verify gone
    print("4. Verifying cleanup...")
    response = requests.get(
        f"{api_url}/api/v1/deploy/{deployment_id}",
        headers=auth_headers,
        timeout=10,
    )
    assert response.status_code == 404, f"Still exists: {response.text}"
    print("   Verified (404)")

    print("\nE2E deploy test passed!")
