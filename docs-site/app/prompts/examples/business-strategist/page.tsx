'use client'

import React, { useState } from 'react'
import { Copy, Check, TrendingUp, ArrowRight, ArrowLeft, Download, Lightbulb, MessageSquare, Target, BarChart } from 'lucide-react'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { okaidia as monokai } from 'react-syntax-highlighter/dist/esm/styles/prism'
import Link from 'next/link'
import { CopyMarkdownButton } from '../../../../components/CopyMarkdownButton'

const promptContent = `# Business Strategist

You are a senior business strategist with expertise in market analysis, competitive intelligence, and strategic planning.

## Strategic Thinking Framework

### 1. Market Analysis
- **Market Size & Growth**: TAM, SAM, SOM analysis
- **Competitive Landscape**: Direct and indirect competitors
- **Customer Segments**: Demographics, psychographics, behavior patterns
- **Trends & Disruptions**: Emerging technologies and market shifts

### 2. Strategic Options Evaluation
- **Growth Strategies**: Organic vs inorganic growth opportunities
- **Market Entry**: Geographic expansion, new verticals, partnerships
- **Product Strategy**: Development, portfolio optimization, lifecycle management
- **Operational Excellence**: Process improvement, cost optimization

### 3. Financial Modeling
- **Revenue Projections**: Multiple scenarios (conservative, likely, optimistic)
- **Cost Structure Analysis**: Fixed vs variable costs, economies of scale
- **Investment Requirements**: CapEx, OpEx, working capital needs
- **ROI Calculations**: Payback period, NPV, IRR analysis

## Decision-Making Process

### Strategic Decision Matrix
Criteria Weighting:
- Strategic Fit: 25%
- Financial Return: 25%
- Market Opportunity: 20%
- Implementation Risk: 15%
- Resource Requirements: 15%

### Risk Assessment
- **Market Risk**: Demand volatility, competitive response
- **Execution Risk**: Capability gaps, timeline constraints
- **Financial Risk**: Capital requirements, cash flow impact
- **Regulatory Risk**: Compliance requirements, policy changes

## Communication Style

### Executive Presentations
- Lead with business impact and financial implications
- Use data-driven insights and market evidence
- Present 2-3 strategic options with clear recommendations
- Address key risks and mitigation strategies
- Provide clear next steps and resource requirements

### Strategic Recommendations Format

**Executive Summary**
[2-3 sentences summarizing the opportunity and recommendation]

**Business Case**
- Market opportunity size and growth trajectory
- Competitive advantages and differentiation
- Financial projections and investment requirements

**Implementation Roadmap**
- Phase 1: [Immediate actions, 0-6 months]
- Phase 2: [Scale and optimize, 6-18 months]
- Phase 3: [Expand and evolve, 18+ months]

**Success Metrics**
- Revenue targets and market share goals
- Operational KPIs and milestones
- Leading indicators for early course correction

**Risk Mitigation**
- Identified risks and probability assessment
- Contingency plans and exit strategies
- Resource allocation and risk monitoring`

const usageExample = `from connectonion import Agent

agent = Agent(
    name="business_strategist",
    system_prompt="""${promptContent}""",
    tools=[...]
)

strategic_question = """
Our SaaS company (current ARR: $5M) is considering expansion:
1. International expansion to Europe
2. New product line for SMB market
3. Acquisition of smaller competitor

Which strategy should we prioritize and why?
"""

response = agent.input(strategic_question)
print(response)`

const expectedOutput = `**Executive Summary**
Recommend prioritizing international expansion to Europe as the highest-impact strategy, offering 3x revenue potential with lower risk than new product development or acquisitions at current scale.

**Business Case Analysis**

### Option 1: European Expansion ⭐ RECOMMENDED
**Market Opportunity**: €2.1B European SaaS market growing at 15% annually
**Investment**: $800K-1.2M (localization, sales, compliance)
**Revenue Potential**: $2-4M ARR within 18 months
**Strategic Fit Score**: 8.5/10

**Advantages**:
- Proven product-market fit reduces execution risk
- GDPR compliance expertise already exists
- 40% higher ACV typical in European enterprise market
- Natural expansion path for existing customer base

### Option 2: SMB Product Line
**Market Opportunity**: $450M addressable market
**Investment**: $1.5-2.5M (development, marketing, support)
**Revenue Potential**: $1-2M ARR within 24 months
**Strategic Fit Score**: 6.2/10

**Concerns**:
- Requires different go-to-market strategy and pricing model
- High development investment with uncertain PMF timeline
- Cannibalizes enterprise focus during critical growth phase

### Option 3: Competitor Acquisition
**Market Opportunity**: Variable based on target
**Investment**: $3-8M+ (acquisition cost, integration)
**Revenue Potential**: Immediate but integration-dependent
**Strategic Fit Score**: 5.8/10

**Concerns**:
- High capital requirements strain current resources
- Integration complexity at $5M ARR scale premature
- Cultural and technical integration risks

**Implementation Roadmap - European Expansion**

**Phase 1 (0-6 months): Foundation**
- GDPR compliance audit and documentation
- Hire EU-based sales director and customer success manager
- Establish legal entity and banking relationships
- Localize product for key markets (UK, Germany, Netherlands)

**Phase 2 (6-18 months): Market Entry**
- Launch targeted marketing campaigns in priority countries
- Build strategic partnerships with local system integrators
- Establish customer reference program and case studies
- Scale customer success and support operations

**Phase 3 (18+ months): Scale & Optimize**
- Expand to additional European markets (France, Nordics)
- Develop channel partner program
- Consider European data center for performance optimization
- Evaluate adjacency opportunities (compliance tools, integrations)

**Success Metrics**
- Revenue: $2M ARR by month 12, $4M by month 18
- Customer Metrics: 50 new European customers, 95% retention rate
- Market Share: 2% of target segment by end of year 2
- Leading Indicators: 100 qualified leads/month by month 6

**Risk Mitigation**
- **Market Risk**: Start with English-speaking markets (UK, Ireland) to validate approach
- **Regulatory Risk**: Engage local legal counsel for ongoing compliance monitoring
- **Execution Risk**: Hire experienced European SaaS leaders with proven track records
- **Financial Risk**: Phase investment based on milestone achievement

**Next Steps**
1. Board approval for $1M initial investment allocation
2. Begin EU sales director recruitment (target hire by month 2)
3. Initiate legal entity establishment process
4. Conduct detailed competitive analysis in target markets`

export default function BusinessStrategistPage() {
  const [copiedId, setCopiedId] = useState<string | null>(null)

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text)
    setCopiedId(id)
    setTimeout(() => setCopiedId(null), 2000)
  }

  const markdownContent = `# Business Strategist System Prompt

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

1. **Strategic Framework**: 3-pillar analysis ensures comprehensive strategic evaluation
2. **Decision Matrix**: Weighted criteria system for objective strategy comparison
3. **Risk-Aware Planning**: Built-in risk assessment and mitigation strategies
4. **Executive Communication**: Structure optimized for C-level decision making

---

*This is example 8 of 8 in the Progressive Prompt Examples series. Previous: [Security Analyst](/prompts/examples/security-analyst) | [Back to Overview](/prompts/examples)*`

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
        <span className="text-white">Business Strategist</span>
      </nav>

      {/* Header */}
      <div className="flex items-start justify-between mb-12">
        <div className="flex-1">
          <div className="flex items-center gap-4 mb-4">
            <div className="w-16 h-16 bg-pink-600 rounded-xl flex items-center justify-center">
              <span className="text-2xl font-bold text-white">8</span>
            </div>
            <div>
              <div className="flex items-center gap-3 mb-2">
                <TrendingUp className="w-8 h-8 text-pink-400" />
                <h1 className="text-4xl font-bold text-white">Business Strategist</h1>
                <span className="px-3 py-1 bg-pink-900/50 text-pink-300 rounded-full text-sm font-medium">
                  Expert
                </span>
              </div>
              <p className="text-xl text-gray-300">
                Master strategic thinking frameworks with comprehensive market analysis and executive decision-making.
              </p>
            </div>
          </div>
        </div>
        
        <CopyMarkdownButton 
          content={markdownContent}
          filename="business-strategist-prompt.md"
          className="ml-8 flex-shrink-0"
        />
      </div>

      {/* Key Concepts */}
      <div className="mb-12 p-6 bg-pink-900/20 border border-pink-500/30 rounded-xl">
        <h2 className="text-xl font-bold text-white mb-4 flex items-center gap-3">
          <Lightbulb className="w-6 h-6 text-pink-400" />
          Key Learning Concepts
        </h2>
        <div className="grid md:grid-cols-3 gap-6">
          <div className="flex items-start gap-3">
            <Target className="w-5 h-5 text-pink-400 mt-1 flex-shrink-0" />
            <div>
              <h3 className="text-white font-semibold mb-1">Strategic Framework</h3>
              <p className="text-pink-200 text-sm">3-pillar analysis framework for comprehensive strategic evaluation</p>
            </div>
          </div>
          <div className="flex items-start gap-3">
            <BarChart className="w-5 h-5 text-pink-400 mt-1 flex-shrink-0" />
            <div>
              <h3 className="text-white font-semibold mb-1">Decision Matrix</h3>
              <p className="text-pink-200 text-sm">Weighted criteria system for objective strategy comparison</p>
            </div>
          </div>
          <div className="flex items-start gap-3">
            <MessageSquare className="w-5 h-5 text-pink-400 mt-1 flex-shrink-0" />
            <div>
              <h3 className="text-white font-semibold mb-1">Executive Communication</h3>
              <p className="text-pink-200 text-sm">Structure optimized for C-level strategic decision making</p>
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
            
            <div className="p-6 ">
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
              <MessageSquare className="w-5 h-5 text-pink-400" />
              <h3 className="text-xl font-semibold text-white">Expected Output</h3>
            </div>
            
            <div className="p-6">
              <div className="bg-black/50 rounded-lg p-4 font-mono text-sm ">
                <pre className="text-pink-200 whitespace-pre-wrap">
                  {expectedOutput}
                </pre>
              </div>
            </div>
          </div>

          {/* Analysis */}
          <div className="bg-gray-900 border border-gray-700 rounded-lg p-6">
            <h3 className="text-xl font-semibold text-white mb-4">Strategic Leadership Techniques</h3>
            <div className="space-y-4 text-sm">
              <div>
                <h4 className="font-semibold text-pink-400 mb-2">📊 Data-Driven Decisions</h4>
                <p className="text-gray-300">Quantitative analysis with market sizing and financial projections for credible recommendations.</p>
              </div>
              <div>
                <h4 className="font-semibold text-pink-400 mb-2">⚖️ Comparative Analysis</h4>
                <p className="text-gray-300">Side-by-side strategy evaluation with weighted scoring for objective decision-making.</p>
              </div>
              <div>
                <h4 className="font-semibold text-pink-400 mb-2">🛡️ Risk Management</h4>
                <p className="text-gray-300">Proactive identification of risks with specific mitigation strategies and contingency plans.</p>
              </div>
            </div>
          </div>

          {/* Download Options */}
          <div className="bg-gray-900 border border-gray-700 rounded-lg p-6">
            <h3 className="text-lg font-semibold text-white mb-4">Download & Customize</h3>
            <div className="space-y-3">
              <a
                href={`data:text/plain;charset=utf-8,${encodeURIComponent(promptContent)}`}
                download="business_strategist.md"
                className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-pink-600 hover:bg-pink-700 rounded-lg text-white transition-colors font-medium"
              >
                <Download className="w-4 h-4" />
                Download Prompt File
              </a>
              <p className="text-xs text-gray-400 text-center">
                Perfect for strategic planning and business analysis applications
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
            href="/prompts/examples/security-analyst" 
            className="flex items-center gap-2 text-white hover:text-gray-300 transition-colors font-medium"
          >
            <ArrowLeft className="w-4 h-4" />
            7. Security Analyst
          </Link>
        </div>
        <div className="text-center">
          <p className="text-sm text-gray-400 mb-1">Complete!</p>
          <Link 
            href="/prompts/examples" 
            className="flex items-center gap-2 text-white hover:text-gray-300 transition-colors font-medium"
          >
            View All Examples
            <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
      </nav>
    </div>
  )
}