# AWS Lightsail Test Infrastructure

Automated remote testing infrastructure for ConnectOnion CLI on AWS Lightsail.

## Overview

This directory contains scripts to deploy and test ConnectOnion on a dedicated AWS Lightsail test server. The infrastructure enables:

- **Clean testing environment** - Fresh Ubuntu server without local artifacts
- **Production-like testing** - Same environment as production API server
- **Automated deployment** - One command to deploy latest code
- **Repeatable tests** - Consistent test execution every time

## Architecture

```
┌─────────────────────────────────────────────────┐
│  AWS Lightsail Test Server                      │
│  ────────────────────────                       │
│  • Ubuntu 20.04 LTS                             │
│  • Nano instance ($3.50/month)                  │
│  • ConnectOnion installed from source           │
│  • Test suite uploaded and executed             │
└─────────────────────────────────────────────────┘
         ↑ deploy-test.sh          ↓ results
┌─────────────────────────────────────────────────┐
│  Local Machine                                   │
│  ─────────────                                   │
│  • Build package                                 │
│  • Upload via SSH                                │
│  • Run tests remotely                            │
│  • Display results                               │
└─────────────────────────────────────────────────┘
```

## Files

- **config.sh.example** - Template configuration file
- **deploy-test.sh** - Deploy ConnectOnion to test server
- **run-remote-tests.sh** - Execute tests on remote server
- **README.md** - This file

## One-Time Setup

### Step 1: Create AWS Lightsail Instance

**Option A: Using AWS Console** (Recommended for first-time)
1. Go to [AWS Lightsail Console](https://lightsail.aws.amazon.com/)
2. Click "Create instance"
3. Select:
   - **Platform:** Linux/Unix
   - **Blueprint:** OS Only → Ubuntu 20.04 LTS
   - **Instance plan:** Nano ($3.50/month)
   - **Instance name:** `connectonion-test`
4. Click "Create instance"
5. Wait for instance to start (1-2 minutes)
6. Note the **Public IP address**

**Option B: Using AWS CLI**
```bash
# Install AWS CLI if needed
brew install awscli  # macOS
# or: pip install awscli

# Configure AWS credentials
aws configure

# Create instance
aws lightsail create-instances \
  --instance-names connectonion-test \
  --availability-zone ap-southeast-2a \
  --blueprint-id ubuntu_20_04 \
  --bundle-id nano_2_0

# Get instance IP
aws lightsail get-instance --instance-name connectonion-test \
  --query 'instance.publicIpAddress' --output text
```

### Step 2: Download SSH Key

**Option A: From AWS Console**
1. Go to Lightsail Console → Account page
2. Click "SSH Keys" tab
3. Download the default key for your region
4. Save as `tests/e2e/cli/aws/connectonion-test-key.pem`

**Option B: Using AWS CLI**
```bash
aws lightsail download-default-key-pair \
  --output text \
  > tests/e2e/cli/aws/connectonion-test-key.pem

chmod 600 tests/e2e/cli/aws/connectonion-test-key.pem
```

### Step 3: Create Configuration File

```bash
# Copy template
cp tests/e2e/cli/aws/config.sh.example tests/e2e/cli/aws/config.sh

# Edit with your server IP
# Change TEST_SERVER_IP="your.lightsail.ip.here" to your actual IP
nano tests/e2e/cli/aws/config.sh
```

### Step 4: Install Python on Server (One-time)

```bash
# Get your server IP from config.sh
SERVER_IP="your.lightsail.ip.here"

# SSH to server and install Python
ssh -i tests/e2e/cli/aws/connectonion-test-key.pem ubuntu@$SERVER_IP << 'EOF'
  sudo apt update
  sudo apt install -y python3 python3-pip python3-venv
  echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
  source ~/.bashrc
EOF
```

### Step 5: Verify Setup

```bash
# Test SSH connection
ssh -i tests/e2e/cli/aws/connectonion-test-key.pem ubuntu@$SERVER_IP \
  "python3 --version && pip3 --version"

# Should output Python and pip versions
```

## Usage

### Deploy Latest Code

```bash
cd /Users/changxing/project/OnCourse/platform/connectonion

# Deploy to test server
./tests/e2e/cli/aws/deploy-test.sh
```

**What it does:**
1. Builds ConnectOnion package from current code
2. Uploads package to test server
3. Uploads test suite (test_auth.sh, etc.)
4. Installs package on server
5. Sets execute permissions

### Run Tests

```bash
# Run automated tests on remote server
./tests/e2e/cli/aws/run-remote-tests.sh
```

**What it does:**
1. Cleans test environment (removes ~/.co and /tmp/connectonion-test)
2. Runs test_auth.sh on remote server
3. Captures output and exit codes
4. Displays results locally

### Complete Workflow

```bash
# Full test cycle
./tests/e2e/cli/aws/deploy-test.sh && ./tests/e2e/cli/aws/run-remote-tests.sh
```

## Expected Output

### Successful Deployment
```
🚀 Deploying ConnectOnion to test server...
   Server: 1.2.3.4

📦 Building ConnectOnion package...
   ✓ Built: connectonion-0.1.10.tar.gz

📁 Creating test directory on server...
   ✓ Directory created: /home/ubuntu/connectonion-test

📤 Uploading package to server...
   ✓ Package uploaded

📋 Uploading test suite...
   ✓ Test scripts uploaded

🔧 Installing ConnectOnion on server...
✓ ConnectOnion installed successfully

✅ Deployment complete!

Next step:
  ./tests/e2e/cli/aws/run-remote-tests.sh
```

### Successful Test Run
```
🧪 Running ConnectOnion tests on remote server...
   Server: 1.2.3.4

🧹 Cleaning test environment...
   Removing ~/.co
   Removing /tmp/connectonion-test
   ✓ Environment cleaned

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Running: test_auth.sh
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[test output here...]

✅ Test PASSED!
   No 'agent_email referenced before assignment' error detected
   Authentication completed successfully
   ✓ AGENT_EMAIL found in .env

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ Remote tests PASSED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✅ All tests passed on remote server!
```

## Troubleshooting

### SSH Connection Failed
```bash
# Check if server is running
aws lightsail get-instance --instance-name connectonion-test

# Check SSH key permissions
chmod 600 tests/e2e/cli/aws/connectonion-test-key.pem

# Test direct SSH
ssh -i tests/e2e/cli/aws/connectonion-test-key.pem ubuntu@<IP>
```

### Package Build Failed
```bash
# Install build dependencies
pip install build setuptools wheel

# Try building manually
cd /Users/changxing/project/OnCourse/platform/connectonion
python setup.py sdist
ls -la dist/
```

### 'co' Command Not Found
```bash
# Add ~/.local/bin to PATH on server
ssh -i tests/e2e/cli/aws/connectonion-test-key.pem ubuntu@<IP> << 'EOF'
  echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
  source ~/.bashrc
  co --version
EOF
```

### Tests Failing
```bash
# SSH to server to debug
ssh -i tests/e2e/cli/aws/connectonion-test-key.pem ubuntu@<IP>

# Check installation
which co
co --version

# Check test files
cd ~/connectonion-test
ls -la

# Run test manually
bash test_auth.sh

# Check .env file
cat ~/.co/keys.env
cat /tmp/connectonion-test/.env
```

## Cost Management

### Keep Server Running
- **Cost:** $3.50/month (Nano instance)
- **Benefit:** Instant testing, no setup delay
- **Recommended for:** Active development

### Stop Server When Not Needed
```bash
# Stop instance (keeps data, $0/month when stopped)
aws lightsail stop-instance --instance-name connectonion-test

# Start when needed
aws lightsail start-instance --instance-name connectonion-test

# Get new IP after starting (IP changes when stopped/started)
aws lightsail get-instance --instance-name connectonion-test \
  --query 'instance.publicIpAddress' --output text
```

### Delete Server
```bash
# Permanently delete instance
aws lightsail delete-instance --instance-name connectonion-test
```

## Security Notes

- **SSH keys** (*.pem, *.key) are gitignored - never commit them
- **config.sh** is gitignored - contains your server IP
- Use **config.sh.example** as template for new setups
- Server has minimal attack surface (only SSH port open)

## Additional Commands

```bash
# View server metrics
aws lightsail get-instance-metric-data \
  --instance-name connectonion-test \
  --metric-name CPUUtilization \
  --period 300 \
  --start-time 2025-10-07T00:00:00Z \
  --end-time 2025-10-07T23:59:59Z \
  --unit Percent \
  --statistics Average

# Create static IP (prevents IP changes)
aws lightsail allocate-static-ip --static-ip-name connectonion-test-ip
aws lightsail attach-static-ip \
  --static-ip-name connectonion-test-ip \
  --instance-name connectonion-test

# Take snapshot for backup
aws lightsail create-instance-snapshot \
  --instance-snapshot-name connectonion-test-backup \
  --instance-name connectonion-test
```

## Support

For issues with:
- **AWS Lightsail:** Check [AWS Lightsail Documentation](https://lightsail.aws.amazon.com/ls/docs)
- **ConnectOnion:** Open issue at https://github.com/openonion/connectonion/issues
- **Discord:** https://discord.gg/4xfD9k8AUF
