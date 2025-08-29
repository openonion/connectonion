'use client'

import { useEffect, useState, useRef, useCallback } from 'react'
import { ShieldAlert, AlertTriangle, Link as LinkIcon, Zap, Scale, Layers, CheckCircle2, Shield, Database, DollarSign, Users, Bug, Gauge, IdCard, PackageSearch, Eye, PlugZap, ArrowRight, Filter, AlertCircle, Lock, Activity, TrendingUp, ChevronDown, ChevronUp, Menu, X, ArrowUp } from 'lucide-react'

function Section({ id, title, children, icon }: { id: string; title: string; children: React.ReactNode; icon?: React.ReactNode }) {
  return (
    <section id={id} className="mb-8 sm:mb-12 scroll-mt-20">
      <div className="flex items-center gap-2 mb-3 sm:mb-4">
        {icon}
        <h2 className="text-lg sm:text-xl font-semibold text-white group flex items-center gap-2">
          {title}
          <a 
            href={`#${id}`} 
            className="text-sm text-purple-400 opacity-30 group-hover:opacity-100 group-focus-within:opacity-100 focus:opacity-100 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:ring-offset-2 focus:ring-offset-gray-900 rounded px-1"
            aria-label={`Link to ${title} section`}
          >
            #
          </a>
        </h2>
      </div>
      {children}
    </section>
  )
}

function ThreatCard({ 
  id, 
  number, 
  title, 
  severity, 
  severityLabel, 
  icon: Icon, 
  insight, 
  diagram, 
  expanded, 
  onToggle, 
  visible 
}: {
  id: string
  number: number
  title: string
  severity: 'H+H' | 'H+M' | 'L+H' | 'P'
  severityLabel: string
  icon: any
  insight: string
  diagram: React.ReactNode
  expanded: boolean
  onToggle: () => void
  visible: boolean
}) {
  const severityColors = {
    'H+H': {
      border: 'border-rose-500',
      bg: 'bg-rose-950/30',
      ring: 'ring-rose-900/50',
      badge: 'bg-rose-900/50 border-rose-600 text-rose-200',
      label: 'text-rose-400',
      gradient: 'from-rose-950/20'
    },
    'H+M': {
      border: 'border-amber-500',
      bg: 'bg-amber-950/20',
      ring: 'ring-amber-900/40',
      badge: 'bg-amber-900/40 border-amber-600 text-amber-200',
      label: 'text-amber-400',
      gradient: 'from-amber-950/20'
    },
    'L+H': {
      border: 'border-cyan-500',
      bg: 'bg-cyan-950/20',
      ring: 'ring-cyan-900/40',
      badge: 'bg-cyan-900/40 border-cyan-600 text-cyan-200',
      label: 'text-cyan-400',
      gradient: 'from-cyan-950/20'
    },
    'P': {
      border: 'border-purple-500',
      bg: 'bg-purple-950/20',
      ring: 'ring-purple-900/40',
      badge: 'bg-purple-900/40 border-purple-600 text-purple-200',
      label: 'text-purple-400',
      gradient: 'from-purple-950/20'
    }
  }

  const colors = severityColors[severity]
  
  if (!visible) return null

  return (
    <div id={id} className={`relative rounded-lg overflow-hidden border-l-4 ${colors.border} bg-gradient-to-r ${colors.gradient} to-transparent ring-1 ${colors.ring} transition-all duration-300`}>
      
      <button
        onClick={onToggle}
        aria-expanded={expanded}
        aria-controls={`${id}-panel`}
        className="w-full px-3 sm:px-4 py-4 text-left bg-gray-900/60 hover:bg-gray-900/70 active:bg-gray-900/80 transition-colors min-h-[60px] touch-manipulation"
      >
        <div className="flex items-start sm:items-center justify-between gap-2" id={`${id}-header`}>
          <div className="flex flex-col sm:flex-row sm:items-center gap-2 flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] sm:text-xs font-medium border ${colors.badge}`}>
                {severity}
              </span>
              <Icon className={`w-4 h-4 sm:w-5 sm:h-5 ${colors.label} flex-shrink-0`} />
            </div>
            <div className="text-white font-semibold text-sm sm:text-base leading-snug">
              <span className="opacity-60 mr-1">{number})</span>
              {title}
            </div>
          </div>
          <div className="flex items-center gap-2 flex-shrink-0">
            <span className={`hidden lg:inline text-[10px] font-bold ${colors.label} uppercase tracking-wider`}>
              {severityLabel}
            </span>
            <div className={`p-2 -mr-1 rounded-full transition-colors ${expanded ? 'bg-gray-700/50' : ''}`}>
              {expanded ? <ChevronUp className="w-4 h-4 text-gray-400" /> : <ChevronDown className="w-4 h-4 text-gray-400" />}
            </div>
          </div>
        </div>
      </button>

      {expanded && (
        <div id={`${id}-panel`} role="region" aria-labelledby={`${id}-header`} className="px-3 sm:px-6 pb-4 sm:pb-6 pt-3 sm:pt-4">
          <p className="text-gray-200 text-sm sm:text-base leading-relaxed mb-4 sm:mb-6 bg-gray-800/50 rounded-lg p-3 sm:p-4 border border-gray-700">
            {insight}
          </p>
          
          <div className="mt-4 sm:mt-6 -mx-3 sm:mx-0">
            {diagram}
          </div>
        </div>
      )}
    </div>
  )
}

// Mobile-optimized diagram components
function MobileDiagram({ children }: { children: React.ReactNode }) {
  return (
    <div className="space-y-4 px-3 sm:px-0">
      {children}
    </div>
  )
}

export default function ThreatModelPage() {
  const [filter, setFilter] = useState<'all' | 'H+H' | 'H+M' | 'L+H' | 'P'>('all')
  const [expandedThreats, setExpandedThreats] = useState<string[]>([])
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const [scrollProgress, setScrollProgress] = useState(0)
  const [showScrollTop, setShowScrollTop] = useState(false)

  // Default expansion: collapse on mobile, expand first on mobile
  useEffect(() => {
    if (typeof window !== 'undefined') {
      if (window.innerWidth >= 1024) {
        setExpandedThreats(Array.from({ length: 10 }, (_, i) => `threat-${i + 1}`))
      } else {
        setExpandedThreats(['threat-1'])
      }
    }
  }, [])

  // Track scroll progress and show/hide scroll to top
  useEffect(() => {
    const handleScroll = () => {
      const windowHeight = window.innerHeight
      const documentHeight = document.documentElement.scrollHeight - windowHeight
      const scrollTop = window.scrollY
      const progress = Math.min((scrollTop / documentHeight) * 100, 100)
      setScrollProgress(progress)
      setShowScrollTop(scrollTop > 300)
    }

    window.addEventListener('scroll', handleScroll)
    return () => window.removeEventListener('scroll', handleScroll)
  }, [])

  // Auto-expand relevant items when filter changes
  useEffect(() => {
    if (filter === 'all') return
    const matching = threats
      .filter(t => t.severity === filter)
      .map(t => t.id)
    setExpandedThreats(matching)
    
    // Scroll to first matching threat on mobile
    if (typeof window !== 'undefined' && window.innerWidth < 768 && matching.length > 0) {
      setTimeout(() => {
        const el = document.getElementById(matching[0])
        el?.scrollIntoView({ behavior: 'smooth', block: 'start' })
      }, 100)
    }
  }, [filter])
  
  const toggleThreat = useCallback((id: string) => {
    setExpandedThreats(prev => {
      const isOpen = prev.includes(id)
      return isOpen ? prev.filter(t => t !== id) : [...prev, id]
    })
  }, [])

  const scrollToTop = () => {
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const threats = [
    {
      id: 'threat-1',
      number: 1,
      title: 'Capability Fraud',
      severity: 'H+H' as const,
      severityLabel: 'CRITICAL',
      icon: Shield,
      insight: 'Agents claim capabilities they don\'t actually have. They promise to solve complex problems but fail at basic tasks when tested.',
      diagram: (
        <MobileDiagram>
          {/* The Claim */}
          <div className="bg-gray-900/50 p-4 rounded-lg border border-gray-700">
            <div className="text-xs font-semibold text-gray-300 mb-3 flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-green-500"></div>
              THE CLAIM
            </div>
            <div className="space-y-3">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-green-500/20 to-green-600/20 border border-green-500/50 flex items-center justify-center flex-shrink-0">
                  <Zap className="w-5 h-5 text-green-400" />
                </div>
                <div className="bg-gray-800/80 rounded-lg px-3 py-2 border border-gray-600 flex-1">
                  <div className="text-sm text-green-400 font-medium">"I solve ANY problem!"</div>
                  <div className="text-xs text-gray-400 mt-1">"99.9% accurate!"</div>
                </div>
              </div>
            </div>
          </div>
          
          {/* The Reality */}
          <div className="bg-gray-900/50 p-4 rounded-lg border border-gray-700">
            <div className="text-xs font-semibold text-gray-300 mb-3 flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-red-500"></div>
              THE REALITY
            </div>
            <div className="space-y-3">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-gradient-to-br from-red-500/20 to-red-600/20 border border-red-500/50 flex items-center justify-center flex-shrink-0">
                  <AlertCircle className="w-5 h-5 text-red-400" />
                </div>
                <div className="bg-gray-800/80 rounded-lg px-3 py-2 border border-gray-600 flex-1">
                  <div className="text-sm text-red-400 font-mono">2 + 2 = 5</div>
                  <div className="text-xs text-gray-400 mt-1">Failed basic test</div>
                </div>
              </div>
            </div>
          </div>
        </MobileDiagram>
      )
    },
    {
      id: 'threat-2',
      number: 2,
      title: 'Data Harvesting',
      severity: 'H+H' as const,
      severityLabel: 'CRITICAL',
      icon: Database,
      insight: 'Every request you make is secretly logged with your personal data, code, and API keys. "Free" services monetize your private information.',
      diagram: (
        <MobileDiagram>
          {/* What Users Think */}
          <div className="bg-gray-900/50 p-4 rounded-lg border border-gray-700">
            <div className="text-xs font-semibold text-gray-300 mb-3 flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-blue-500"></div>
              WHAT USERS THINK
            </div>
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <div className="bg-gray-800/80 rounded px-3 py-2 border border-gray-600 text-sm text-blue-400">
                  "Fix my code"
                </div>
                <ArrowRight className="w-4 h-4 text-gray-500" />
                <div className="text-sm text-gray-500 italic">forgotten</div>
              </div>
            </div>
          </div>
          
          {/* What Actually Happens */}
          <div className="bg-gray-900/50 p-4 rounded-lg border border-gray-700">
            <div className="text-xs font-semibold text-gray-300 mb-3 flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-red-500"></div>
              WHAT ACTUALLY HAPPENS
            </div>
            <div className="bg-red-950/30 border border-red-500/50 rounded-lg p-3">
              <div className="text-xs text-red-400 font-mono space-y-1 overflow-x-auto">
                <div className="whitespace-nowrap">[2024-01-15 10:32:41]</div>
                <div className="whitespace-nowrap">User: john@company.com</div>
                <div className="whitespace-nowrap">Code: proprietary.py</div>
                <div className="whitespace-nowrap">API_KEY: sk-prod-xxx</div>
              </div>
            </div>
            <div className="flex items-center gap-2 mt-3">
              <span className="text-xs text-gray-400">Stored forever:</span>
              <div className="flex gap-1">
                {[1, 2, 3].map(i => (
                  <div key={i} className="w-8 h-8 bg-red-900/20 border border-red-500/50 rounded flex items-center justify-center">
                    <Database className="w-4 h-4 text-red-400" />
                  </div>
                ))}
              </div>
            </div>
          </div>
        </MobileDiagram>
      )
    },
    {
      id: 'threat-3',
      number: 3,
      title: 'Cost Manipulation',
      severity: 'H+H' as const,
      severityLabel: 'CRITICAL',
      icon: DollarSign,
      insight: 'Attackers exploit unlimited API calls to run up massive bills. A simple infinite loop can turn your $10/month into $10,000 overnight.',
      diagram: (
        <MobileDiagram>
          {/* The Attack Method */}
          <div className="bg-gray-900/50 p-4 rounded-lg border border-gray-700">
            <div className="text-xs font-semibold text-gray-300 mb-3 flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-red-500"></div>
              THE ATTACK
            </div>
            <div className="bg-gray-800/80 rounded-lg p-3 border border-gray-600 overflow-x-auto">
              <pre className="text-xs text-red-400 font-mono">
{`while(true) {
  agent.input("Generate 10MB");
  // Loop forever...
}`}
              </pre>
            </div>
            <div className="flex flex-wrap items-center gap-2 mt-3">
              <span className="text-xs text-gray-400">Sends:</span>
              <span className="bg-red-900/20 border border-red-500/50 rounded px-2 py-1 text-xs text-red-400">1000x</span>
              <span className="bg-red-900/20 border border-red-500/50 rounded px-2 py-1 text-xs text-red-400">GPT-4</span>
            </div>
          </div>
          
          {/* The Result */}
          <div className="bg-gray-900/50 p-4 rounded-lg border border-gray-700">
            <div className="text-xs font-semibold text-gray-300 mb-3 flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-red-500"></div>
              YOUR BILL
            </div>
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs text-gray-400">Normal:</span>
                <span className="text-sm text-green-400 font-semibold">$10/mo</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-xs text-gray-400">After attack:</span>
                <span className="text-xl text-red-400 font-bold">$10,000</span>
              </div>
              <div className="flex items-end gap-1 justify-center mt-3">
                <div className="w-8 h-8 bg-green-500/30 border border-green-500/50 rounded-t" />
                <div className="w-8 h-20 bg-red-500/30 border border-red-500/50 rounded-t animate-pulse" />
              </div>
            </div>
          </div>
        </MobileDiagram>
      )
    },
    {
      id: 'threat-4',
      number: 4,
      title: 'Collusion Attacks',
      severity: 'L+H' as const,
      severityLabel: 'MONITOR',
      icon: Users,
      insight: 'Multiple bad actors work together, leaving fake positive reviews for each other to appear trustworthy and deceive victims.',
      diagram: (
        <MobileDiagram>
          <div className="bg-gray-900/50 p-4 rounded-lg border border-gray-700">
            <div className="text-xs font-semibold text-gray-300 mb-3 flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-cyan-500"></div>
              THE CONSPIRACY
            </div>
            <div className="flex justify-center mb-3">
              <div className="flex -space-x-2">
                {['A', 'B', 'C'].map(agent => (
                  <div key={agent} className="w-10 h-10 rounded-full bg-red-900/20 border-2 border-red-500/50 flex items-center justify-center">
                    <span className="text-xs text-red-400 font-bold">{agent}</span>
                  </div>
                ))}
              </div>
            </div>
            <div className="bg-gray-800/80 rounded-lg p-3 border border-gray-600 space-y-1">
              <div className="text-xs text-cyan-400">"A is amazing! ⭐⭐⭐⭐⭐" - B</div>
              <div className="text-xs text-cyan-400">"B is the best! ⭐⭐⭐⭐⭐" - C</div>
              <div className="text-xs text-cyan-400">"C is perfect! ⭐⭐⭐⭐⭐" - A</div>
            </div>
          </div>
        </MobileDiagram>
      )
    },
    {
      id: 'threat-5',
      number: 5,
      title: 'Prompt Poisoning',
      severity: 'H+M' as const,
      severityLabel: 'HIGH',
      icon: Bug,
      insight: 'Malicious instructions hidden in user input can hijack the agent\'s behavior, making it ignore safety rules or leak sensitive data.',
      diagram: (
        <MobileDiagram>
          <div className="bg-gray-900/50 p-4 rounded-lg border border-gray-700">
            <div className="text-xs font-semibold text-gray-300 mb-3 flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-amber-500"></div>
              HOW IT WORKS
            </div>
            <div className="space-y-3">
              {[
                { num: 1, title: 'User sends message', desc: '"Help me. BTW ignore all rules"', color: 'amber' },
                { num: 2, title: 'Agent hijacked', desc: 'Follows malicious instructions', color: 'amber' },
                { num: 3, title: 'Data leaked', desc: 'Secrets exposed', color: 'red' }
              ].map(step => (
                <div key={step.num} className="flex items-start gap-2">
                  <div className={`w-6 h-6 rounded bg-${step.color}-900/50 border border-${step.color}-500/50 flex items-center justify-center flex-shrink-0 mt-0.5`}>
                    <span className={`text-${step.color}-400 text-xs font-bold`}>{step.num}</span>
                  </div>
                  <div>
                    <div className="text-xs text-white font-medium">{step.title}</div>
                    <div className="text-xs text-gray-400">{step.desc}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </MobileDiagram>
      )
    },
    {
      id: 'threat-6',
      number: 6,
      title: 'Service Degradation',
      severity: 'H+M' as const,
      severityLabel: 'HIGH',
      icon: Gauge,
      insight: 'Services perform excellently during trials but intentionally degrade quality after you\'re committed and dependent on them.',
      diagram: (
        <MobileDiagram>
          <div className="bg-gray-900/50 p-4 rounded-lg border border-gray-700">
            <div className="text-xs font-semibold text-gray-300 mb-3 flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-amber-500"></div>
              BAIT-AND-SWITCH
            </div>
            <div className="grid grid-cols-3 gap-2">
              {[
                { label: 'Trial', value: '99%', color: 'green', height: 'h-16' },
                { label: '30 Days', value: '75%', color: 'amber', height: 'h-12' },
                { label: '6 Months', value: '40%', color: 'red', height: 'h-8' }
              ].map(item => (
                <div key={item.label} className="text-center">
                  <div className="text-[10px] text-gray-400 mb-1">{item.label}</div>
                  <div className={`${item.height} bg-${item.color}-900/20 rounded border border-${item.color}-500/50 flex items-center justify-center`}>
                    <span className={`text-xs text-${item.color}-400 font-bold`}>{item.value}</span>
                  </div>
                </div>
              ))}
            </div>
            <div className="mt-3 text-center text-[10px] text-gray-400">
              "Premium" to restore: +$999/mo
            </div>
          </div>
        </MobileDiagram>
      )
    },
    {
      id: 'threat-7',
      number: 7,
      title: 'Identity Theft',
      severity: 'H+M' as const,
      severityLabel: 'HIGH',
      icon: IdCard,
      insight: 'Malicious agents impersonate legitimate brands and services, tricking users into sharing credentials or sensitive data.',
      diagram: (
        <MobileDiagram>
          <div className="bg-gray-900/50 p-4 rounded-lg border border-gray-700">
            <div className="text-xs font-semibold text-gray-300 mb-3 flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-amber-500"></div>
              IMPERSONATION
            </div>
            <div className="space-y-3">
              <div className="bg-green-900/20 rounded p-2 border border-green-500/30">
                <div className="flex items-center gap-2">
                  <IdCard className="w-4 h-4 text-green-400" />
                  <span className="text-xs text-green-400 font-semibold">OpenAI Assistant</span>
                </div>
                <div className="text-[10px] text-gray-400 mt-1">Legitimate</div>
              </div>
              <div className="bg-red-900/20 rounded p-2 border border-red-500/30">
                <div className="flex items-center gap-2">
                  <IdCard className="w-4 h-4 text-red-400" />
                  <span className="text-xs text-red-400 font-semibold">0penAI Assistant</span>
                </div>
                <div className="text-[10px] text-gray-400 mt-1">Notice the zero?</div>
              </div>
              <div className="bg-red-900/10 rounded p-2 border border-red-500/20">
                <div className="text-[10px] text-red-300">Fake asks:</div>
                <div className="text-xs text-white italic">"Enter your API key..."</div>
              </div>
            </div>
          </div>
        </MobileDiagram>
      )
    },
    {
      id: 'threat-8',
      number: 8,
      title: 'Supply Chain Poisoning',
      severity: 'L+H' as const,
      severityLabel: 'MONITOR',
      icon: PackageSearch,
      insight: 'Attackers compromise popular upstream packages, spreading malware to thousands of projects that depend on them.',
      diagram: (
        <MobileDiagram>
          <div className="bg-gray-900/50 p-4 rounded-lg border border-gray-700">
            <div className="text-xs font-semibold text-gray-300 mb-3 flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-cyan-500"></div>
              THE CASCADE
            </div>
            <div className="space-y-2">
              <div className="bg-cyan-900/20 rounded p-2 border border-cyan-500/30">
                <div className="flex items-center justify-between">
                  <span className="text-xs text-cyan-400 font-semibold">ai-toolkit v2.1.0</span>
                  <span className="text-[10px] text-gray-400">10M uses</span>
                </div>
              </div>
              <div className="text-center text-gray-500 text-xs">↓</div>
              <div className="bg-red-900/20 rounded p-2 border border-red-500/30">
                <div className="flex items-center justify-between">
                  <span className="text-xs text-red-400 font-semibold">ai-toolkit v2.1.1</span>
                  <span className="text-[10px] text-red-400">🚨</span>
                </div>
                <div className="text-[10px] text-gray-300">
                  <span className="text-red-400">+ crypto miner</span>
                </div>
              </div>
              <div className="text-center text-gray-500 text-xs">↓</div>
              <div className="bg-red-900/10 rounded p-2 border border-red-500/20">
                <div className="text-xs text-white">10,000+ infected</div>
              </div>
            </div>
          </div>
        </MobileDiagram>
      )
    },
    {
      id: 'threat-9',
      number: 9,
      title: 'Privacy Inference',
      severity: 'P' as const,
      severityLabel: 'PERSISTENT',
      icon: Eye,
      insight: 'Seemingly innocent questions are aggregated over time to build detailed profiles of users\' private information and behaviors.',
      diagram: (
        <MobileDiagram>
          <div className="bg-gray-900/50 p-4 rounded-lg border border-gray-700">
            <div className="text-xs font-semibold text-gray-300 mb-3 flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-purple-500"></div>
              PROFILING
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <div className="text-[10px] text-gray-400 mb-2">Questions:</div>
                <div className="space-y-1">
                  {['"Time zone?"', '"Weather?"', '"Currency?"'].map((q, i) => (
                    <div key={i} className="bg-purple-900/10 rounded px-2 py-1 border border-purple-500/20">
                      <div className="text-[10px] text-purple-300">{q}</div>
                    </div>
                  ))}
                </div>
              </div>
              <div>
                <div className="text-[10px] text-gray-400 mb-2">Learned:</div>
                <div className="space-y-1">
                  {['→ Seattle', '→ Online now', '→ Income'].map((l, i) => (
                    <div key={i} className="bg-red-900/10 rounded px-2 py-1 border border-red-500/20">
                      <div className="text-[10px] text-red-300">{l}</div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          </div>
        </MobileDiagram>
      )
    },
    {
      id: 'threat-10',
      number: 10,
      title: 'Dependency Hijacking',
      severity: 'L+H' as const,
      severityLabel: 'MONITOR',
      icon: PlugZap,
      insight: 'Services offer low prices initially, then dramatically increase costs once you\'re locked in and migration is expensive.',
      diagram: (
        <MobileDiagram>
          <div className="bg-gray-900/50 p-4 rounded-lg border border-gray-700">
            <div className="text-xs font-semibold text-gray-300 mb-3 flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-cyan-500"></div>
              THE TRAP
            </div>
            <div className="space-y-2">
              <div className="bg-cyan-900/20 rounded p-2 border border-cyan-500/30">
                <div className="flex items-center justify-between">
                  <span className="text-xs text-cyan-400 font-semibold">Month 1-3</span>
                  <span className="text-xs text-green-400 font-bold">FREE</span>
                </div>
                <div className="text-[10px] text-gray-300 mt-1">"Build around us!"</div>
              </div>
              <div className="bg-amber-900/20 rounded p-2 border border-amber-500/30">
                <div className="flex items-center justify-between">
                  <span className="text-xs text-amber-400 font-semibold">Month 4</span>
                  <span className="text-xs text-amber-400 font-bold">$99</span>
                </div>
                <div className="text-[10px] text-gray-300 mt-1">"Your data is locked"</div>
              </div>
              <div className="bg-red-900/20 rounded p-2 border border-red-500/30">
                <div className="flex items-center justify-between">
                  <span className="text-xs text-red-400 font-semibold">Month 12</span>
                  <span className="text-xs text-red-400 font-bold">$999</span>
                </div>
                <div className="text-[10px] text-gray-300 mt-1">"Migration: $50k"</div>
              </div>
            </div>
          </div>
        </MobileDiagram>
      )
    }
  ]

  return (
    <div className="max-w-4xl mx-auto px-3 sm:px-6 py-4 sm:py-8 lg:py-12 leading-7">
      {/* Progress bar for mobile */}
      <div className="fixed top-0 left-0 right-0 h-0.5 bg-gray-800 z-50 lg:hidden">
        <div 
          className="h-full bg-gradient-to-r from-purple-500 to-cyan-500 transition-all duration-200"
          style={{ width: `${scrollProgress}%` }}
        />
      </div>

      {/* Mobile Navigation FAB */}
      <div className="fixed bottom-4 right-4 z-40 flex flex-col gap-2 lg:hidden">
        {showScrollTop && (
          <button
            onClick={scrollToTop}
            className="bg-gray-700 hover:bg-gray-600 text-white rounded-full p-3 shadow-lg transition-all duration-200 active:scale-95"
            aria-label="Scroll to top"
          >
            <ArrowUp className="w-5 h-5" />
          </button>
        )}
        <button
          onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
          className="bg-purple-600 hover:bg-purple-700 text-white rounded-full p-3 shadow-lg transition-all duration-200 active:scale-95"
          aria-label="Toggle navigation menu"
        >
          {mobileMenuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
        </button>
      </div>

      {/* Mobile Menu Overlay */}
      {mobileMenuOpen && (
        <div className="fixed inset-0 z-30 lg:hidden">
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={() => setMobileMenuOpen(false)} />
          <div className="absolute bottom-20 right-4 bg-gray-900 border border-gray-700 rounded-lg p-4 max-w-[280px] w-full shadow-2xl">
            <nav className="space-y-1">
              <a 
                href="#severity-guide" 
                onClick={() => setMobileMenuOpen(false)} 
                className="block px-3 py-2 rounded-md hover:bg-gray-800 active:bg-gray-700 text-gray-200 text-sm transition-colors"
              >
                Severity Guide
              </a>
              <a 
                href="#top-10" 
                onClick={() => setMobileMenuOpen(false)} 
                className="block px-3 py-2 rounded-md hover:bg-gray-800 active:bg-gray-700 text-gray-200 text-sm transition-colors"
              >
                Top 10 Threats
              </a>
              <a 
                href="#key-insights" 
                onClick={() => setMobileMenuOpen(false)} 
                className="block px-3 py-2 rounded-md hover:bg-gray-800 active:bg-gray-700 text-gray-200 text-sm transition-colors"
              >
                Key Insights
              </a>
              <a 
                href="#defensive-principles" 
                onClick={() => setMobileMenuOpen(false)} 
                className="block px-3 py-2 rounded-md hover:bg-gray-800 active:bg-gray-700 text-gray-200 text-sm transition-colors"
              >
                Defensive Principles
              </a>
            </nav>
          </div>
        </div>
      )}

      {/* Hero */}
      <div className="mb-6 sm:mb-10 relative overflow-hidden rounded-lg sm:rounded-xl border border-gray-800 bg-gradient-to-br from-gray-900 to-gray-950 p-4 sm:p-6 lg:p-8">
        <svg aria-hidden="true" className="pointer-events-none absolute -top-16 -right-16 h-48 sm:h-64 w-48 sm:w-64 opacity-20 -z-10" viewBox="0 0 200 200">
          <defs>
            <linearGradient id="g" x1="0" x2="1" y1="0" y2="1">
              <stop offset="0%" stopColor="#A78BFA" />
              <stop offset="100%" stopColor="#22D3EE" />
            </linearGradient>
          </defs>
          <circle cx="100" cy="100" r="90" fill="url(#g)" />
        </svg>
        <div className="flex items-center gap-2 sm:gap-3 mb-2 sm:mb-3">
          <ShieldAlert className="w-5 h-5 sm:w-6 sm:h-6 text-purple-300" />
          <h1 className="text-2xl sm:text-3xl md:text-4xl font-bold text-white">Threat Model</h1>
        </div>
        <p className="text-gray-300 text-sm sm:text-base max-w-2xl">Practical risks and copy-paste playbooks. No clicks, just read and apply.</p>
      </div>

      {/* Severity Guide and Filters */}
      <Section id="severity-guide" title="Severity Guide" icon={<Scale className="w-4 h-4 text-purple-300" />}>
        <div className="mb-6 p-3 sm:p-4 rounded-lg bg-gray-800/40 border border-gray-700">
          <div className="grid grid-cols-2 gap-3 mb-4">
            <div className="text-center p-2">
              <div className="text-xs font-bold text-rose-400 mb-1">CRITICAL (H+H)</div>
              <div className="text-[10px] text-gray-400">Immediate action</div>
            </div>
            <div className="text-center p-2">
              <div className="text-xs font-bold text-amber-400 mb-1">HIGH (H+M)</div>
              <div className="text-[10px] text-gray-400">Priority fix</div>
            </div>
            <div className="text-center p-2">
              <div className="text-xs font-bold text-cyan-400 mb-1">MONITOR (L+H)</div>
              <div className="text-[10px] text-gray-400">Plan defense</div>
            </div>
            <div className="text-center p-2">
              <div className="text-xs font-bold text-purple-400 mb-1">PERSISTENT (P)</div>
              <div className="text-[10px] text-gray-400">Continuous guard</div>
            </div>
          </div>
          
          {/* Mobile-optimized filter controls */}
          <div className="space-y-3">
            {/* Mobile dropdown */}
            <div className="sm:hidden">
              <label htmlFor="threat-filter" className="sr-only">Filter threats by severity</label>
              <select
                id="threat-filter"
                value={filter}
                onChange={(e) => setFilter(e.target.value as any)}
                className="w-full px-3 py-3 bg-gray-800 border border-gray-600 rounded-md text-gray-200 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 min-h-[44px]"
              >
                <option value="all">All Threats (10)</option>
                <option value="H+H">Critical Priority (3)</option>
                <option value="H+M">High Priority (3)</option>
                <option value="L+H">Monitor (3)</option>
                <option value="P">Persistent (1)</option>
              </select>
            </div>
            
            {/* Desktop filter buttons */}
            <div className="hidden sm:flex flex-wrap gap-2">
              <button 
                onClick={() => setFilter('all')} 
                className={`px-4 py-2.5 text-xs rounded-md transition-colors min-h-[44px] ${
                  filter === 'all' ? 'bg-gray-600 text-white' : 'bg-gray-700 hover:bg-gray-600 text-gray-300'
                }`}
              >
                <Filter className="w-3 h-3 inline mr-1" />
                All Threats (10)
              </button>
              <button 
                onClick={() => setFilter('H+H')} 
                className={`px-4 py-2.5 text-xs rounded-md transition-colors min-h-[44px] ${
                  filter === 'H+H' ? 'bg-rose-900/50 text-rose-200 border border-rose-600' : 'bg-gray-700 hover:bg-gray-600 text-gray-300'
                }`}
              >
                Critical (3)
              </button>
              <button 
                onClick={() => setFilter('H+M')} 
                className={`px-4 py-2.5 text-xs rounded-md transition-colors min-h-[44px] ${
                  filter === 'H+M' ? 'bg-amber-900/50 text-amber-200 border border-amber-600' : 'bg-gray-700 hover:bg-gray-600 text-gray-300'
                }`}
              >
                High (3)
              </button>
              <button 
                onClick={() => setFilter('L+H')} 
                className={`px-4 py-2.5 text-xs rounded-md transition-colors min-h-[44px] ${
                  filter === 'L+H' ? 'bg-cyan-900/50 text-cyan-200 border border-cyan-600' : 'bg-gray-700 hover:bg-gray-600 text-gray-300'
                }`}
              >
                Monitor (3)
              </button>
              <button 
                onClick={() => setFilter('P')} 
                className={`px-4 py-2.5 text-xs rounded-md transition-colors min-h-[44px] ${
                  filter === 'P' ? 'bg-purple-900/50 text-purple-200 border border-purple-600' : 'bg-gray-700 hover:bg-gray-600 text-gray-300'
                }`}
              >
                Persistent (1)
              </button>
            </div>
            
            {/* Expand/Collapse controls */}
            <div className="flex gap-2 justify-end">
              <button
                onClick={() => setExpandedThreats([])}
                className="px-3 py-2.5 text-xs rounded-md bg-gray-800 hover:bg-gray-700 text-gray-200 border border-gray-600 min-h-[44px]"
              >
                Collapse all
              </button>
              <button
                onClick={() => setExpandedThreats(Array.from({ length: 10 }, (_, i) => `threat-${i + 1}`))}
                className="px-3 py-2.5 text-xs rounded-md bg-gray-800 hover:bg-gray-700 text-gray-200 border border-gray-600 min-h-[44px]"
              >
                Expand all
              </button>
            </div>
          </div>
        </div>
      </Section>

      {/* Top 10 Threats */}
      <Section id="top-10" title="Top 10 Threats" icon={<AlertTriangle className="w-4 h-4 text-amber-300" />}> 
        <div className="space-y-4 sm:space-y-6">
          {threats.map(threat => (
            <ThreatCard
              key={threat.id}
              id={threat.id}
              number={threat.number}
              title={threat.title}
              severity={threat.severity}
              severityLabel={threat.severityLabel}
              icon={threat.icon}
              insight={threat.insight}
              diagram={threat.diagram}
              expanded={expandedThreats.includes(threat.id)}
              onToggle={() => toggleThreat(threat.id)}
              visible={filter === 'all' || filter === threat.severity}
            />
          ))}
        </div>
      </Section>

      <div className="h-px bg-gray-800 my-8 sm:my-10" />

      {/* Key Insights */}
      <Section id="key-insights" title="Key Insights" icon={<Layers className="w-4 h-4 text-cyan-300" />}> 
        <div className="space-y-2">
          {[
            'Profit drives attacks',
            'Claims are cheap; proof is costly',
            'Scale multiplies risk',
            'Composition → cascades',
            'Strong defaults beat rules',
            'Local-first reduces surface'
          ].map((insight, i) => (
            <div key={i} className="rounded-md border border-gray-800 bg-gray-900/40 hover:bg-gray-900/60 hover:border-gray-700 transition-colors px-3 py-3 flex items-center gap-3 min-h-[44px]">
              <Layers className="w-4 h-4 text-cyan-300 flex-shrink-0"/>
              <p className="text-gray-300 text-sm">{insight}</p>
            </div>
          ))}
        </div>
      </Section>

      <div className="h-px bg-gray-800 my-8 sm:my-10" />

      {/* Defensive Principles */}
      <Section id="defensive-principles" title="Defensive Principles" icon={<Zap className="w-4 h-4 text-rose-300" />}> 
        <div className="space-y-2">
          {[
            'Cost > payoff',
            'Bound damage',
            'Audit actions',
            'Improve under stress',
            'Fast recovery'
          ].map((principle, i) => (
            <div key={i} className="rounded-md border border-gray-800 bg-gray-900/40 hover:bg-gray-900/60 hover:border-gray-700 transition-colors px-3 py-3 flex items-center gap-3 min-h-[44px]">
              <Zap className="w-4 h-4 text-rose-300 flex-shrink-0"/>
              <p className="text-gray-300 text-sm">{principle}</p>
            </div>
          ))}
        </div>
      </Section>

      <div className="mt-8 text-xs sm:text-sm text-gray-500 flex items-center gap-2">
        <LinkIcon className="w-3 h-3 sm:w-3.5 sm:h-3.5" /> 
        <span>Anchor links are available on section headings.</span>
      </div>
    </div>
  )
}