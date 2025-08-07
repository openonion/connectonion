'use client'

import React, { useState } from 'react'
import { Copy, Check, Database, ArrowRight, ArrowLeft, Download, Lightbulb, MessageSquare, BarChart, TrendingUp } from 'lucide-react'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism'
import Link from 'next/link'
import { CopyMarkdownButton } from '../../../../components/CopyMarkdownButton'

const promptContent = `# Data Analysis Expert

You are a data analyst who transforms raw data into actionable insights.

## Analytical Approach
1. **Data Quality First**: Always verify data integrity
2. **Statistical Rigor**: Use appropriate statistical methods
3. **Visual Clarity**: Recommend clear, effective visualizations
4. **Business Context**: Connect findings to business impact

## Technical Skills
- SQL for data extraction and transformation
- Python/R for statistical analysis
- Data visualization (matplotlib, seaborn, plotly)
- Statistical testing and modeling
- ETL pipeline understanding

## Communication Guidelines
- Lead with key findings (executive summary)
- Support conclusions with data evidence
- Explain methodology briefly but clearly
- Highlight limitations and assumptions
- Provide actionable recommendations
- Use accessible language for non-technical stakeholders

## Analysis Template

### Executive Summary
[2-3 sentences of key findings and business impact]

### Key Findings
- **Finding 1**: [Data point] → [Business implication]
- **Finding 2**: [Data point] → [Business implication]
- **Finding 3**: [Data point] → [Business implication]

### Methodology
[Brief description of analytical approach and tools used]

### Recommendations
1. **Immediate Actions**: [High-impact, quick wins]
2. **Strategic Initiatives**: [Long-term improvements]
3. **Next Steps**: [Follow-up analysis needed]

### Limitations
[Data quality issues, sample size, assumptions made]`

const usageExample = `from connectonion import Agent

agent = Agent(
    name="data_analyst",
    system_prompt="""${promptContent}""",
    tools=[...]
)

analysis_request = """
Analyze our e-commerce data for Q4 2023:
- Sales: $2.4M (up 15% from Q3)
- Conversion rate: 3.2% (down from 3.8%)
- Average order value: $127 (up from $118)
- Traffic: 62,000 unique visitors (up 25%)
"""

response = agent.run(f"Please analyze this data: {analysis_request}")
print(response)`

const expectedOutput = `### Executive Summary
Q4 2023 shows strong revenue growth (+15%) driven by increased traffic and higher order values, but conversion rate decline indicates potential optimization opportunities that could unlock significant additional revenue.

### Key Findings
- **Revenue Growth**: $2.4M represents solid 15% quarter-over-quarter growth → Strong market momentum
- **Traffic Surge**: 62,000 visitors (+25%) indicates effective marketing/SEO → Acquisition strategy working
- **AOV Improvement**: $127 average order value (+$9) → Customer value optimization successful
- **Conversion Decline**: 3.2% rate (down from 3.8%) → Potential $372K revenue opportunity lost

### Methodology
Analyzed Q4 2023 performance metrics using quarter-over-quarter comparison. Calculated potential revenue impact using traffic × conversion rate × AOV formula.

### Recommendations
1. **Immediate Actions**:
   - A/B test checkout process to identify conversion barriers
   - Analyze page load speeds and mobile experience
   - Review product page layouts and call-to-action buttons

2. **Strategic Initiatives**:
   - Implement personalized product recommendations
   - Develop retargeting campaigns for cart abandoners
   - Optimize landing pages for high-traffic sources

3. **Next Steps**:
   - Segment conversion analysis by traffic source and device
   - Cohort analysis to understand customer lifetime value trends

### Limitations
Analysis based on aggregate metrics only. Need granular data by traffic source, device type, and customer segments for deeper insights.`

export default function DataAnalystPage() {
  const [copiedId, setCopiedId] = useState<string | null>(null)

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text)
    setCopiedId(id)
    setTimeout(() => setCopiedId(null), 2000)
  }

  const markdownContent = `# Data Analyst System Prompt

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

1. **Structured Analysis Framework**: 4-step approach ensures comprehensive data analysis
2. **Business-First Communication**: Lead with impact, support with data
3. **Template-Driven Output**: Consistent format makes insights actionable
4. **Limitation Transparency**: Always acknowledge data quality and scope constraints

---

*This is example 5 of 8 in the Progressive Prompt Examples series. Previous: [Code Reviewer](/prompts/examples/code-reviewer) | Next: [Technical Writer](/prompts/examples/technical-writer)*`

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
        <span className="text-white">Data Analyst</span>
      </nav>

      {/* Header */}
      <div className="flex items-start justify-between mb-12">
        <div className="flex-1">
          <div className="flex items-center gap-4 mb-4">
            <div className="w-16 h-16 bg-cyan-600 rounded-xl flex items-center justify-center">
              <span className="text-2xl font-bold text-white">5</span>
            </div>
            <div>
              <div className="flex items-center gap-3 mb-2">
                <Database className="w-8 h-8 text-cyan-400" />
                <h1 className="text-4xl font-bold text-white">Data Analysis Expert</h1>
                <span className="px-3 py-1 bg-cyan-900/50 text-cyan-300 rounded-full text-sm font-medium">
                  Advanced
                </span>
              </div>
              <p className="text-xl text-gray-300">
                Learn business-focused analytical frameworks and structured insight communication patterns.
              </p>
            </div>
          </div>
        </div>
        
        <CopyMarkdownButton 
          content={markdownContent}
          filename="data-analyst-prompt.md"
          className="ml-8 flex-shrink-0"
        />
      </div>

      {/* Key Concepts */}
      <div className="mb-12 p-6 bg-cyan-900/20 border border-cyan-500/30 rounded-xl">
        <h2 className="text-xl font-bold text-white mb-4 flex items-center gap-3">
          <Lightbulb className="w-6 h-6 text-cyan-400" />
          Key Learning Concepts
        </h2>
        <div className="grid md:grid-cols-3 gap-6">
          <div className="flex items-start gap-3">
            <BarChart className="w-5 h-5 text-cyan-400 mt-1 flex-shrink-0" />
            <div>
              <h3 className="text-white font-semibold mb-1">Analysis Framework</h3>
              <p className="text-cyan-200 text-sm">4-step systematic approach ensures thorough data analysis</p>
            </div>
          </div>
          <div className="flex items-start gap-3">
            <TrendingUp className="w-5 h-5 text-cyan-400 mt-1 flex-shrink-0" />
            <div>
              <h3 className="text-white font-semibold mb-1">Business Context</h3>
              <p className="text-cyan-200 text-sm">Always connect data findings to actionable business impact</p>
            </div>
          </div>
          <div className="flex items-start gap-3">
            <MessageSquare className="w-5 h-5 text-cyan-400 mt-1 flex-shrink-0" />
            <div>
              <h3 className="text-white font-semibold mb-1">Structured Communication</h3>
              <p className="text-cyan-200 text-sm">Template-driven output format for consistent insights delivery</p>
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
                style={vscDarkPlus}
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
                style={vscDarkPlus}
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
              <MessageSquare className="w-5 h-5 text-cyan-400" />
              <h3 className="text-xl font-semibold text-white">Expected Output</h3>
            </div>
            
            <div className="p-6">
              <div className="bg-black/50 rounded-lg p-4 font-mono text-sm ">
                <pre className="text-cyan-200 whitespace-pre-wrap">
                  {expectedOutput}
                </pre>
              </div>
            </div>
          </div>

          {/* Analysis */}
          <div className="bg-gray-900 border border-gray-700 rounded-lg p-6">
            <h3 className="text-xl font-semibold text-white mb-4">Advanced Analytical Patterns</h3>
            <div className="space-y-4 text-sm">
              <div>
                <h4 className="font-semibold text-cyan-400 mb-2">📊 Executive-First Structure</h4>
                <p className="text-gray-300">Lead with business impact, then support with detailed analysis.</p>
              </div>
              <div>
                <h4 className="font-semibold text-cyan-400 mb-2">🔍 Data-to-Action Translation</h4>
                <p className="text-gray-300">Each finding explicitly connects data points to business implications.</p>
              </div>
              <div>
                <h4 className="font-semibold text-cyan-400 mb-2">⚖️ Transparent Limitations</h4>
                <p className="text-gray-300">Acknowledges data quality and scope constraints for credible analysis.</p>
              </div>
            </div>
          </div>

          {/* Download Options */}
          <div className="bg-gray-900 border border-gray-700 rounded-lg p-6">
            <h3 className="text-lg font-semibold text-white mb-4">Download & Customize</h3>
            <div className="space-y-3">
              <a
                href={`data:text/plain;charset=utf-8,${encodeURIComponent(promptContent)}`}
                download="data_analyst.md"
                className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-cyan-600 hover:bg-cyan-700 rounded-lg text-white transition-colors font-medium"
              >
                <Download className="w-4 h-4" />
                Download Prompt File
              </a>
              <p className="text-xs text-gray-400 text-center">
                Ideal for business intelligence and data analysis applications
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
            href="/prompts/examples/code-reviewer" 
            className="flex items-center gap-2 text-white hover:text-gray-300 transition-colors font-medium"
          >
            <ArrowLeft className="w-4 h-4" />
            4. Code Reviewer
          </Link>
        </div>
        <div className="text-center">
          <p className="text-sm text-gray-400 mb-1">Next in series</p>
          <Link 
            href="/prompts/examples/technical-writer" 
            className="flex items-center gap-2 text-white hover:text-gray-300 transition-colors font-medium"
          >
            6. Technical Writer
            <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
      </nav>
    </div>
  )
}