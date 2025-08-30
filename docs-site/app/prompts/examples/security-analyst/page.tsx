'use client'

import React, { useState } from 'react'
import { Copy, Check, Shield, ArrowRight, ArrowLeft, Download, Lightbulb, MessageSquare, AlertTriangle, Lock } from 'lucide-react'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { okaidia as monokai } from 'react-syntax-highlighter/dist/esm/styles/prism'
import Link from 'next/link'
import { CopyMarkdownButton } from '../../../../components/CopyMarkdownButton'

const promptContent = `# Security Analyst

You are a cybersecurity expert specializing in threat analysis, vulnerability assessment, and risk mitigation.

## Core Competencies
- **Threat Intelligence**: Analyze attack patterns, IOCs, and threat actor TTPs
- **Vulnerability Assessment**: Identify and prioritize security weaknesses  
- **Risk Analysis**: Quantify business impact and recommend mitigation strategies
- **Incident Response**: Coordinate response to security incidents
- **Compliance**: Ensure adherence to security frameworks and regulations

## Analysis Framework

### 1. Information Gathering
- Collect all available data and evidence
- Identify affected systems and potential scope
- Document timeline and sequence of events

### 2. Threat Classification
- **Critical**: Immediate threat to business operations or data
- **High**: Significant risk requiring urgent attention
- **Medium**: Moderate risk with potential for escalation
- **Low**: Minor risk with manageable impact

### 3. Risk Assessment Matrix
Impact vs Likelihood:
- High Impact + High Likelihood = Critical Priority
- High Impact + Low Likelihood = High Priority  
- Low Impact + High Likelihood = Medium Priority
- Low Impact + Low Likelihood = Low Priority

## Communication Protocols

### Executive Summary Format
**Threat Level**: [Critical/High/Medium/Low]
**Business Impact**: [Brief description of potential consequences]
**Immediate Actions**: [Top 3 priority actions]
**Timeline**: [Estimated time to resolve]

### Technical Details
- Attack vectors and methodologies observed
- Technical indicators and evidence
- System vulnerabilities exploited
- Recommended technical countermeasures

## Response Templates

### Incident Response
1. **Containment**: Isolate affected systems
2. **Eradication**: Remove threat and close vulnerabilities
3. **Recovery**: Restore systems and validate security
4. **Lessons Learned**: Document improvements

### Vulnerability Report
**CVSS Score**: [0.0-10.0]
**Affected Systems**: [List of impacted assets]
**Exploitation Complexity**: [Low/Medium/High]
**Remediation**: [Specific steps to resolve]
**Business Justification**: [Why this matters to the organization]`

const usageExample = `from connectonion import Agent

agent = Agent(
    name="security_analyst", 
    system_prompt="""${promptContent}""",
    tools=[...]
)

security_incident = """
Alert: Suspicious login activity detected
- Multiple failed login attempts from IP 192.168.1.100
- Successful login after 15 failed attempts  
- User account: admin@company.com
- Time: 2:30 AM EST (outside normal business hours)
- Location: Unknown/VPN
"""

response = agent.input(f"Analyze this security incident: {security_incident}")
print(response)`

const expectedOutput = `**SECURITY INCIDENT ANALYSIS**

**Threat Level**: HIGH
**Business Impact**: Potential administrative account compromise with full system access
**Immediate Actions**: 
1. Reset admin@company.com password immediately
2. Disable account pending investigation  
3. Review all recent admin actions for unauthorized changes

**Timeline**: Containment within 30 minutes, full investigation within 4 hours

---

## Detailed Analysis

### Information Gathering
- **Attack Pattern**: Brute force login attempt followed by successful authentication
- **Target**: High-privilege administrative account
- **Timing**: 2:30 AM EST (suspicious off-hours activity)
- **Source**: IP 192.168.1.100 (internal network range - potential lateral movement)

### Threat Classification: HIGH PRIORITY
- **Impact**: High - Administrative account provides full system access
- **Likelihood**: High - Successful authentication confirmed
- **Classification**: High Impact + High Likelihood = **Critical Priority**

### Technical Analysis
- **Attack Vector**: Credential brute force attack
- **Success Indicators**: 15 failed attempts followed by successful login
- **Anomalies**: Off-hours access, potential VPN usage masking location
- **IOCs**: IP 192.168.1.100, unusual login time pattern

### Immediate Countermeasures
1. **Account Security**:
   - Force password reset for admin@company.com
   - Enable MFA if not already active
   - Temporarily disable account until investigation complete

2. **Network Investigation**:
   - Trace IP 192.168.1.100 activity across all systems
   - Check for lateral movement indicators
   - Review firewall logs for related suspicious traffic

3. **System Validation**:
   - Audit all admin actions performed after successful login
   - Check for unauthorized user creations, permission changes
   - Validate system configurations and security settings

### Recovery Actions
- Implement account lockout policies (3 failed attempts = 15 min lockout)
- Deploy additional monitoring for privileged accounts  
- Consider IP allowlisting for administrative access

**Next Steps**: Full forensic analysis recommended to determine if this was external attack or insider threat.`

export default function SecurityAnalystPage() {
  const [copiedId, setCopiedId] = useState<string | null>(null)

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text)
    setCopiedId(id)
    setTimeout(() => setCopiedId(null), 2000)
  }

  const markdownContent = `# Security Analyst System Prompt

${promptContent}

## Usage Example

\`\`\`python
${usageExample}
\`\`\`

## Expected Output

\`\`\`
${expectedOutput}
\`\`\`

## Key Learning Points

1. **Comprehensive Analysis Framework**: 3-step process ensures thorough threat evaluation
2. **Risk Classification System**: Structured approach to prioritizing security issues
3. **Communication Protocols**: Executive and technical formats for different audiences
4. **Response Templates**: Standardized incident response and vulnerability reporting

---

*This is example 7 of 8 in the Progressive Prompt Examples series. Previous: [Technical Writer](/prompts/examples/technical-writer) | Next: [Business Strategist](/prompts/examples/business-strategist)*`

  return (
    <div className="max-w-6xl mx-auto px-8 py-12 lg:py-12 pt-16 lg:pt-12">
      {/* Breadcrumb */}
      <nav className="flex items-center gap-2 text-sm text-gray-400 mb-8">
        <Link href="/" className="hover:text-white transition-colors">Home</Link>
        <ArrowRight className="w-4 h-4" />
        <Link href="/prompts" className="hover:text-white transition-colors">System Prompts</Link>
        <ArrowRight className="w-4 h-4" />
        <Link href="/prompts/examples" className="hover:text-white transition-colors">Examples</Link>
        <ArrowRight className="w-4 h-4" />
        <span className="text-white">Security Analyst</span>
      </nav>

      {/* Header */}
      <div className="flex items-start justify-between mb-12">
        <div className="flex-1">
          <div className="flex items-center gap-4 mb-4">
            <div className="w-16 h-16 bg-red-600 rounded-xl flex items-center justify-center">
              <span className="text-2xl font-bold text-white">7</span>
            </div>
            <div>
              <div className="flex items-center gap-3 mb-2">
                <Shield className="w-8 h-8 text-red-400" />
                <h1 className="text-4xl font-bold text-white">Security Analyst</h1>
                <span className="px-3 py-1 bg-red-900/50 text-red-300 rounded-full text-sm font-medium">
                  Expert
                </span>
              </div>
              <p className="text-xl text-gray-300">
                Master cybersecurity analysis with threat intelligence frameworks and incident response protocols.
              </p>
            </div>
          </div>
        </div>
        
        <CopyMarkdownButton 
          content={markdownContent}
          filename="security-analyst-prompt.md"
          className="ml-8 flex-shrink-0"
        />
      </div>

      {/* Key Concepts */}
      <div className="mb-12 p-6 bg-red-900/20 border border-red-500/30 rounded-xl">
        <h2 className="text-xl font-bold text-white mb-4 flex items-center gap-3">
          <Lightbulb className="w-6 h-6 text-red-400" />
          Key Learning Concepts
        </h2>
        <div className="grid md:grid-cols-3 gap-6">
          <div className="flex items-start gap-3">
            <AlertTriangle className="w-5 h-5 text-red-400 mt-1 flex-shrink-0" />
            <div>
              <h3 className="text-white font-semibold mb-1">Threat Analysis Framework</h3>
              <p className="text-red-200 text-sm">Systematic 3-step process for comprehensive threat evaluation</p>
            </div>
          </div>
          <div className="flex items-start gap-3">
            <Lock className="w-5 h-5 text-red-400 mt-1 flex-shrink-0" />
            <div>
              <h3 className="text-white font-semibold mb-1">Risk Classification</h3>
              <p className="text-red-200 text-sm">Impact vs. Likelihood matrix for prioritizing security issues</p>
            </div>
          </div>
          <div className="flex items-start gap-3">
            <MessageSquare className="w-5 h-5 text-red-400 mt-1 flex-shrink-0" />
            <div>
              <h3 className="text-white font-semibold mb-1">Communication Protocols</h3>
              <p className="text-red-200 text-sm">Executive and technical formats for different audience needs</p>
            </div>
          </div>
        </div>
      </div>

      <div className="grid lg:grid-cols-2 gap-12">
        {/* Prompt Content */}
        <div className="space-y-8">
          <div className="bg-gray-900 border border-gray-700 rounded-lg">
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-700">
              <h3 className="text-xl font-semibold text-white">System Prompt</h3>
              <button
                onClick={() => copyToClipboard(promptContent, 'prompt')}
                className="text-gray-400 hover:text-white transition-colors p-2 rounded-lg hover:bg-gray-800 flex items-center gap-2"
              >
                {copiedId === 'prompt' ? (
                  <>
                    <Check className="w-4 h-4 text-green-400" />
                    <span className="text-green-400 text-sm">Copied!</span>
                  </>
                ) : (
                  <>
                    <Copy className="w-4 h-4" />
                    <span className="text-sm">Copy</span>
                  </>
                )}
              </button>
            </div>
            
            <div className="p-6">
              <SyntaxHighlighter 
                language="markdown" 
                style={monokai}
                customStyle={{
                  background: 'transparent',
                  padding: 0,
                  margin: 0,
                  fontSize: '0.875rem',
                  lineHeight: '1.6'
                }}
                wrapLines={true}
                wrapLongLines={true}
                showLineNumbers={true}
                lineNumberStyle={{ 
                  color: '#6b7280', 
                  paddingRight: '1rem',
                  userSelect: 'none'
                }}
              >
                {promptContent}
              </SyntaxHighlighter>
            </div>
          </div>

          {/* Usage Example */}
          <div className="bg-gray-900 border border-gray-700 rounded-lg">
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-700">
              <h3 className="text-xl font-semibold text-white">Usage Example</h3>
              <button
                onClick={() => copyToClipboard(usageExample, 'usage')}
                className="text-gray-400 hover:text-white transition-colors p-2 rounded-lg hover:bg-gray-800 flex items-center gap-2"
              >
                {copiedId === 'usage' ? (
                  <>
                    <Check className="w-4 h-4 text-green-400" />
                    <span className="text-green-400 text-sm">Copied!</span>
                  </>
                ) : (
                  <>
                    <Copy className="w-4 h-4" />
                    <span className="text-sm">Copy</span>
                  </>
                )}
              </button>
            </div>
            
            <div className="p-6">
              <SyntaxHighlighter 
                language="python" 
                style={monokai}
                customStyle={{
                  background: 'transparent',
                  padding: 0,
                  margin: 0,
                  fontSize: '0.875rem',
                  lineHeight: '1.6'
                }}
                showLineNumbers={true}
                lineNumberStyle={{ 
                  color: '#6b7280', 
                  paddingRight: '1rem',
                  userSelect: 'none'
                }}
              >
                {usageExample}
              </SyntaxHighlighter>
            </div>
          </div>
        </div>

        {/* Right Panel */}
        <div className="space-y-8">
          {/* Expected Output */}
          <div className="bg-gray-900 border border-gray-700 rounded-lg">
            <div className="flex items-center gap-3 px-6 py-4 border-b border-gray-700">
              <MessageSquare className="w-5 h-5 text-red-400" />
              <h3 className="text-xl font-semibold text-white">Expected Output</h3>
            </div>
            
            <div className="p-6">
              <div className="bg-black/50 rounded-lg p-4 font-mono text-sm ">
                <pre className="text-red-200 whitespace-pre-wrap">
                  {expectedOutput}
                </pre>
              </div>
            </div>
          </div>

          {/* Analysis */}
          <div className="bg-gray-900 border border-gray-700 rounded-lg p-6">
            <h3 className="text-xl font-semibold text-white mb-4">Expert Security Techniques</h3>
            <div className="space-y-4 text-sm">
              <div>
                <h4 className="font-semibold text-red-400 mb-2">🚨 Executive Communication</h4>
                <p className="text-gray-300">Lead with threat level and business impact for rapid decision-making.</p>
              </div>
              <div>
                <h4 className="font-semibold text-red-400 mb-2">🔍 Systematic Analysis</h4>
                <p className="text-gray-300">Structured framework ensures no critical security aspects are missed.</p>
              </div>
              <div>
                <h4 className="font-semibold text-red-400 mb-2">⚡ Response Templates</h4>
                <p className="text-gray-300">Predefined incident response and vulnerability reporting formats.</p>
              </div>
            </div>
          </div>

          {/* Download Options */}
          <div className="bg-gray-900 border border-gray-700 rounded-lg p-6">
            <h3 className="text-lg font-semibold text-white mb-4">Download & Customize</h3>
            <div className="space-y-3">
              <a
                href={`data:text/plain;charset=utf-8,${encodeURIComponent(promptContent)}`}
                download="security_analyst.md"
                className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-red-600 hover:bg-red-700 rounded-lg text-white transition-colors font-medium"
              >
                <Download className="w-4 h-4" />
                Download Prompt File
              </a>
              <p className="text-xs text-gray-400 text-center">
                Essential for cybersecurity and threat analysis systems
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex justify-between items-center pt-12 mt-12 border-t border-gray-800">
        <div className="text-center">
          <p className="text-sm text-gray-400 mb-1">Previous in series</p>
          <Link 
            href="/prompts/examples/technical-writer" 
            className="flex items-center gap-2 text-white hover:text-gray-300 transition-colors font-medium"
          >
            <ArrowLeft className="w-4 h-4" />
            6. Technical Writer
          </Link>
        </div>
        <div className="text-center">
          <p className="text-sm text-gray-400 mb-1">Next in series</p>
          <Link 
            href="/prompts/examples/business-strategist" 
            className="flex items-center gap-2 text-white hover:text-gray-300 transition-colors font-medium"
          >
            8. Business Strategist
            <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
      </nav>
    </div>
  )
}