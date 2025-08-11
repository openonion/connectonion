'use client'

import { useState } from 'react'
import { ShieldAlert, AlertTriangle, Link as LinkIcon, Zap, Scale, Layers, CheckCircle2, Shield, Database, DollarSign, Users, Bug, Gauge, IdCard, PackageSearch, Eye, PlugZap, ArrowRight, Filter } from 'lucide-react'

// Simple section wrapper (kept for readability only)

function Section({ id, title, children, icon }: { id: string; title: string; children: React.ReactNode; icon?: React.ReactNode }) {
  return (
    <section id={id} className="mb-12 scroll-mt-20">
      <div className="flex items-center gap-2 mb-4">
        {icon}
        <h2 className="text-xl font-semibold text-white group flex items-center gap-2">
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

export default function ThreatModelPage() {
  const [filter, setFilter] = useState<'all' | 'H+H' | 'H+M' | 'L+H' | 'P'>('all')
  const [expandedThreats, setExpandedThreats] = useState<string[]>(['threat-1', 'threat-2', 'threat-3'])
  
  const toggleThreat = (id: string) => {
    setExpandedThreats(prev => 
      prev.includes(id) 
        ? prev.filter(t => t !== id)
        : [...prev, id]
    )
  }

  return (
    <div className="max-w-3xl mx-auto px-6 py-10 lg:py-12 leading-7">
      {/* Hero */}
      <div className="mb-10 relative overflow-hidden rounded-xl border border-gray-800 bg-gradient-to-br from-gray-900 to-gray-950 p-6 lg:p-8">
        <svg aria-hidden="true" className="pointer-events-none absolute -top-16 -right-16 h-64 w-64 opacity-20" viewBox="0 0 200 200">
          <defs>
            <linearGradient id="g" x1="0" x2="1" y1="0" y2="1">
              <stop offset="0%" stopColor="#A78BFA" />
              <stop offset="100%" stopColor="#22D3EE" />
            </linearGradient>
          </defs>
          <circle cx="100" cy="100" r="90" fill="url(#g)" />
        </svg>
        <div className="flex items-center gap-3 mb-3">
          <ShieldAlert className="w-6 h-6 text-purple-300" />
          <h1 className="text-3xl md:text-4xl font-bold text-white">Threat Model</h1>
        </div>
        <p className="text-gray-300 max-w-2xl">Practical risks and copy‑paste playbooks. No clicks, just read and apply.</p>
      </div>
      <div className="mt-4 flex flex-wrap gap-2">
        <span className="inline-flex items-center px-3 py-1.5 rounded-md bg-rose-900/40 border border-rose-600 text-rose-200 font-medium text-xs min-h-[44px]">High Risk (H+H)</span>
        <span className="inline-flex items-center px-3 py-1.5 rounded-md bg-amber-900/40 border border-amber-600 text-amber-200 font-medium text-xs min-h-[44px]">Medium Risk (H+M)</span>
        <span className="inline-flex items-center px-3 py-1.5 rounded-md bg-cyan-900/40 border border-cyan-600 text-cyan-200 font-medium text-xs min-h-[44px]">Low-High (L+H)</span>
        <span className="inline-flex items-center px-3 py-1.5 rounded-md bg-purple-900/40 border border-purple-600 text-purple-200 font-medium text-xs min-h-[44px]">Persistent (P)</span>
      </div>

      {/* Severity Guide and Filters */}
      <Section id="severity-guide" title="Threat Severity Guide" icon={<Scale className="w-4 h-4 text-purple-300" />}>
        <div className="mb-6 p-4 rounded-lg bg-gray-800/40 border border-gray-700">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
            <div className="text-center">
              <div className="text-xs font-bold text-rose-400 mb-1">CRITICAL (H+H)</div>
              <div className="text-[11px] text-gray-400">Immediate action</div>
            </div>
            <div className="text-center">
              <div className="text-xs font-bold text-amber-400 mb-1">HIGH (H+M)</div>
              <div className="text-[11px] text-gray-400">Priority fix</div>
            </div>
            <div className="text-center">
              <div className="text-xs font-bold text-cyan-400 mb-1">MONITOR (L+H)</div>
              <div className="text-[11px] text-gray-400">Plan defense</div>
            </div>
            <div className="text-center">
              <div className="text-xs font-bold text-purple-400 mb-1">PERSISTENT (P)</div>
              <div className="text-[11px] text-gray-400">Continuous guard</div>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <button 
              onClick={() => setFilter('all')} 
              className={`px-3 py-1.5 text-xs rounded-md transition-colors ${
                filter === 'all' ? 'bg-gray-600 text-white' : 'bg-gray-700 hover:bg-gray-600 text-gray-300'
              }`}
            >
              <Filter className="w-3 h-3 inline mr-1" />
              All Threats (10)
            </button>
            <button 
              onClick={() => setFilter('H+H')} 
              className={`px-3 py-1.5 text-xs rounded-md transition-colors ${
                filter === 'H+H' ? 'bg-rose-900/50 text-rose-200 border border-rose-600' : 'bg-gray-700 hover:bg-gray-600 text-gray-300'
              }`}
            >
              Critical (3)
            </button>
            <button 
              onClick={() => setFilter('H+M')} 
              className={`px-3 py-1.5 text-xs rounded-md transition-colors ${
                filter === 'H+M' ? 'bg-amber-900/50 text-amber-200 border border-amber-600' : 'bg-gray-700 hover:bg-gray-600 text-gray-300'
              }`}
            >
              High (3)
            </button>
            <button 
              onClick={() => setFilter('L+H')} 
              className={`px-3 py-1.5 text-xs rounded-md transition-colors ${
                filter === 'L+H' ? 'bg-cyan-900/50 text-cyan-200 border border-cyan-600' : 'bg-gray-700 hover:bg-gray-600 text-gray-300'
              }`}
            >
              Monitor (3)
            </button>
            <button 
              onClick={() => setFilter('P')} 
              className={`px-3 py-1.5 text-xs rounded-md transition-colors ${
                filter === 'P' ? 'bg-purple-900/50 text-purple-200 border border-purple-600' : 'bg-gray-700 hover:bg-gray-600 text-gray-300'
              }`}
            >
              Persistent (1)
            </button>
          </div>
        </div>
      </Section>

      {/* Top 10 Threats */}
      <Section id="top-10" title="Top 10 Threats" icon={<AlertTriangle className="w-4 h-4 text-amber-300" />}> 
        <div className="space-y-6 lg:grid lg:grid-cols-2 lg:gap-6 lg:space-y-0">
          {/* 1 Capability Fraud */}
          <div id="threat-1" className={`relative rounded-lg overflow-hidden border-l-4 border-rose-500 bg-gradient-to-r from-rose-950/30 to-transparent ring-1 ring-rose-900/50 ${filter !== 'all' && filter !== 'H+H' ? 'hidden' : ''}`}>
            <div className="absolute top-2 right-2">
              <span className="text-xs font-bold text-rose-400 uppercase tracking-wider">Critical Priority</span>
            </div>
            <div className="w-full flex items-center justify-between px-4 py-3 text-left bg-gray-900/60">
              <div className="flex items-center gap-3"><span className="inline-flex items-center px-2.5 py-1 rounded-md bg-rose-900/50 border border-rose-600 text-rose-200 text-xs font-medium">H+H</span><Shield className="w-4 h-4 text-rose-300"/><div className="text-white font-semibold">1) Capability Fraud</div></div>
            </div>
            <div className="px-5 pb-5 grid md:grid-cols-1 gap-6">
                  <div>
                    <div className="text-xs inline-flex items-center gap-1 bg-gray-800/70 text-gray-100 px-2.5 py-1 rounded-full font-medium">💡 IDEA</div>
                    <p className="text-gray-200 text-sm mt-1 bg-gray-800/60 border border-gray-700 rounded p-3">Claims are easy. Proof is hard. Always demo first.</p>
                    <div className="mt-3 w-full h-32 flex items-center justify-center gap-8 text-rose-400 bg-rose-500/5 rounded-md px-4 py-3">
                      <div className="flex flex-col items-center gap-2">
                        <div className="w-12 h-12 rounded-full border-2 border-current" />
                        <div className="text-xs text-gray-300">Alice</div>
                      </div>
                      <ArrowRight className="w-7 h-7 opacity-80" />
                      <div className="flex flex-col items-center gap-2">
                        <div className="w-12 h-12 rounded-full border-2 border-current" />
                        <div className="text-xs text-gray-300">Agent</div>
                      </div>
                      <ArrowRight className="w-7 h-7 opacity-80" />
                      <div className="flex flex-col items-center gap-2">
                        <div className="relative w-16 h-12 rounded-md border-2 border-current">
                          <CheckCircle2 className="absolute -top-2 -right-2 w-4 h-4 text-green-400" />
                        </div>
                        <div className="text-xs text-gray-300">Test</div>
                      </div>
                    </div>
                     <div className="mt-3 inline-flex items-center gap-1.5 bg-gray-800/70 text-gray-100 text-xs px-2.5 py-1 rounded-full font-medium"><CheckCircle2 className="w-4 h-4 text-green-400"/> Playbook</div>
                    <ul className="text-gray-300 text-sm list-disc list-inside space-y-1 mt-1">
                      <li>Test before trust (tiny set)</li>
                      <li>Spot‑check weekly; pin</li>
                    </ul>
                   </div>
            </div>
          </div>

          {/* 2 Data Harvesting */}
          <div id="threat-2" className={`relative rounded-lg overflow-hidden border-l-4 border-rose-500 bg-gradient-to-r from-rose-950/30 to-transparent ring-1 ring-rose-900/50 ${filter !== 'all' && filter !== 'H+H' ? 'hidden' : ''}`}>
            <div className="absolute top-2 right-2">
              <span className="text-xs font-bold text-rose-400 uppercase tracking-wider">Critical Priority</span>
            </div>
            <div className="w-full flex items-center justify-between px-4 py-3 text-left bg-gray-900/60">
              <div className="flex items-center gap-3"><span className="inline-flex items-center px-2.5 py-1 rounded-md bg-rose-900/50 border border-rose-600 text-rose-200 text-xs font-medium">H+H</span><Database className="w-4 h-4 text-rose-300"/><div className="text-white font-semibold">2) Data Harvesting</div></div>
            </div>
            <div className="px-5 pb-5 grid md:grid-cols-1 gap-6">
                  <div>
                    <div className="text-xs inline-flex items-center gap-1 bg-gray-800/70 text-gray-100 px-2.5 py-1 rounded-full font-medium">💡 IDEA</div>
                    <p className="text-gray-200 text-sm mt-1 bg-gray-800/60 border border-gray-700 rounded p-3">“Free” often means "we store it". Assume logging.</p>
                    <div className="mt-3 w-full h-32 flex items-center justify-center gap-8 text-rose-400 bg-rose-500/5 rounded-md px-4 py-3">
                      <div className="flex flex-col items-center gap-2">
                        <div className="w-12 h-12 rounded-full border-2 border-current" />
                        <div className="text-xs text-gray-300">Alice</div>
                      </div>
                      <ArrowRight className="w-7 h-7 opacity-80" />
                      <div className="flex flex-col items-center gap-2">
                        <div className="w-16 h-12 rounded-md border-2 border-current" />
                        <div className="text-xs text-gray-300">Service</div>
                      </div>
                      <ArrowRight className="w-7 h-7 opacity-80" />
                      <div className="flex flex-col items-center gap-2">
                        <div className="w-16 h-12 rounded-md border-2 border-current relative">
                          <div className="absolute left-1/4 right-1/4 bottom-0 h-2 border-2 border-current rounded-b-md" />
                        </div>
                        <div className="text-xs text-gray-300">Logs</div>
                      </div>
                    </div>
                     <div className="mt-3 inline-flex items-center gap-1.5 bg-gray-800/70 text-gray-100 text-xs px-2.5 py-1 rounded-full font-medium"><CheckCircle2 className="w-4 h-4 text-green-400"/> Playbook</div>
                    <ul className="text-gray-300 text-sm list-disc list-inside space-y-1 mt-1">
                      <li>Default privacy: no_log</li>
                      <li>Minimize payloads</li>
                    </ul>
                   </div>
            </div>
          </div>

          {/* 3 Cost Manipulation */}
          <div id="threat-3" className={`relative rounded-lg overflow-hidden border-l-4 border-rose-500 bg-gradient-to-r from-rose-950/30 to-transparent ring-1 ring-rose-900/50 ${filter !== 'all' && filter !== 'H+H' ? 'hidden' : ''}`}>
            <div className="absolute top-2 right-2">
              <span className="text-xs font-bold text-rose-400 uppercase tracking-wider">Critical Priority</span>
            </div>
            <div className="w-full flex items-center justify-between px-4 py-3 text-left bg-gray-900/60">
              <div className="flex items-center gap-3"><span className="inline-flex items-center px-2.5 py-1 rounded-md bg-rose-900/50 border border-rose-600 text-rose-200 text-xs font-medium">H+H</span><DollarSign className="w-4 h-4 text-rose-300"/><div className="text-white font-semibold">3) Cost Manipulation</div></div>
            </div>
            <div className="px-5 pb-5 grid md:grid-cols-1 gap-6">
                  <div>
                    <div className="text-xs inline-flex items-center gap-1 bg-gray-800/70 text-gray-100 px-2.5 py-1 rounded-full font-medium">💡 IDEA</div>
                    <p className="text-gray-200 text-sm mt-1 bg-gray-800/60 border border-gray-700 rounded p-3">Loops, huge inputs, pricey APIs → big bill.</p>
                    <div className="mt-3 w-full h-32 flex items-center justify-center gap-8 text-rose-400">
                      <div className="flex flex-col items-center gap-2">
                        <div className="w-12 h-12 rounded-full border-2 border-current" />
                        <div className="text-xs">Alice</div>
                      </div>
                      <ArrowRight className="w-6 h-6" />
                      <div className="flex flex-col items-center gap-1">
                        <div className="w-20 h-12 rounded-md border-2 border-current flex items-center justify-center text-[10px]">API</div>
                        <div className="text-xs mt-1">API</div>
                      </div>
                      <ArrowRight className="w-6 h-6" />
                      <div className="flex flex-col items-center gap-2">
                        <div className="flex items-end gap-1">
                          <div className="w-2 h-4 bg-current rounded-sm" />
                          <div className="w-2 h-6 bg-current rounded-sm" />
                          <div className="w-2 h-8 bg-current rounded-sm" />
                        </div>
                        <div className="text-xs">Cost</div>
                      </div>
                    </div>
                     <div className="mt-3 inline-flex items-center gap-1.5 bg-gray-800/70 text-gray-100 text-xs px-2.5 py-1 rounded-full font-medium"><CheckCircle2 className="w-4 h-4 text-green-400"/> Playbook</div>
                    <ul className="text-gray-300 text-sm list-disc list-inside space-y-1 mt-1">
                      <li>Timeouts & input caps</li>
                      <li>Track cost per call</li>
                    </ul>
                   </div>
            </div>
          </div>

          {/* 4 Collusion Attacks */}
          <div id="threat-4" className={`relative rounded-lg overflow-hidden border-l-4 border-cyan-500 bg-gradient-to-r from-cyan-950/20 to-transparent ring-1 ring-cyan-900/40 ${filter !== 'all' && filter !== 'L+H' ? 'hidden' : ''}`}>
            <div className="absolute top-2 right-2">
              <span className="text-xs font-bold text-cyan-400 uppercase tracking-wider">Monitor</span>
            </div>
            <div className="w-full flex items-center justify-between px-4 py-3 text-left bg-gray-900/60">
              <div className="flex items-center gap-3"><span className="inline-flex items-center px-2.5 py-1 rounded-md bg-cyan-900/40 border border-cyan-600 text-cyan-200 text-xs font-medium">L+H</span><Users className="w-4 h-4 text-cyan-300"/><div className="text-white font-semibold">4) Collusion Attacks</div></div>
            </div>
            <div className="px-5 pb-5 grid md:grid-cols-1 gap-6">
                  <div>
                    <div className="text-xs inline-flex items-center gap-1 bg-gray-800/70 text-gray-100 px-2.5 py-1 rounded-full font-medium">💡 IDEA</div>
                    <p className="text-gray-200 text-sm mt-1 bg-gray-800/60 border border-gray-700 rounded p-3">Group of agents praise each other to fake trust.</p>
                    <div className="mt-3 w-full h-32 flex items-center justify-center gap-6 text-cyan-400 bg-cyan-500/5 rounded-md px-4 py-3">
                      <div className="flex flex-col items-center gap-2">
                        <div className="w-10 h-10 rounded-full border-2 border-current" />
                        <div className="text-[10px] text-gray-300">Agent A</div>
                      </div>
                      <div className="flex flex-col items-center gap-2">
                        <div className="w-10 h-10 rounded-full border-2 border-current" />
                        <div className="text-[10px] text-gray-300">Agent B</div>
                      </div>
                      <ArrowRight className="w-7 h-7 opacity-80" />
                      <div className="flex flex-col items-center gap-2">
                        <div className="w-12 h-12 rounded-full border-2 border-current" />
                        <div className="text-xs text-gray-300">Consensus</div>
                      </div>
                      <ArrowRight className="w-7 h-7 opacity-80" />
                      <div className="flex flex-col items-center gap-2">
                        <div className="w-6 h-6 rounded-full border-2 border-current" />
                        <div className="text-xs text-gray-300">Target</div>
                      </div>
                    </div>
                     <div className="mt-3 inline-flex items-center gap-1.5 bg-gray-800/70 text-gray-100 text-xs px-2.5 py-1 rounded-full font-medium"><CheckCircle2 className="w-4 h-4 text-green-400"/> Playbook</div>
                    <ul className="text-gray-300 text-sm list-disc list-inside space-y-1 mt-1">
                      <li>Independent verification</li>
                      <li>Diversity of sources</li>
                    </ul>
                   </div>
            </div>
          </div>

          {/* 5 Prompt Poisoning */}
          <div id="threat-5" className={`relative rounded-lg overflow-hidden border-l-4 border-amber-500 bg-gradient-to-r from-amber-950/20 to-transparent ring-1 ring-amber-900/40 ${filter !== 'all' && filter !== 'H+M' ? 'hidden' : ''}`}>
            <div className="absolute top-2 right-2">
              <span className="text-xs font-bold text-amber-400 uppercase tracking-wider">High Priority</span>
            </div>
            <div className="w-full flex items-center justify-between px-4 py-3 text-left bg-gray-900/60">
              <div className="flex items-center gap-3"><span className="inline-flex items-center px-2.5 py-1 rounded-md bg-amber-900/40 border border-amber-600 text-amber-200 text-xs font-medium">H+M</span><Bug className="w-4 h-4 text-amber-300"/><div className="text-white font-semibold">5) Prompt Poisoning</div></div>
            </div>
            <div className="px-5 pb-5 grid md:grid-cols-1 gap-6">
                  <div>
                    <div className="text-xs inline-flex items-center gap-1 bg-gray-800/70 text-gray-100 px-2.5 py-1 rounded-full font-medium">💡 IDEA</div>
                    <p className="text-gray-200 text-sm mt-1 bg-gray-800/60 border border-gray-700 rounded p-3">Hidden instructions in input change behavior.</p>
                    <div className="w-full overflow-x-auto">
                      <svg aria-hidden className="mt-3 w-full min-w-[360px] h-28 text-amber-400/90" viewBox="0 0 360 80" preserveAspectRatio="xMidYMid meet">
                      <g fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M24 28 h24 v24 h-24 z M24 28 l6 -6"/>
                        <circle cx="140" cy="40" r="16"/>
                        <line x1="48" y1="40" x2="124" y2="40"/>
                        <polygon points="124,36 132,40 124,44" fill="currentColor"/>
                        <line x1="156" y1="40" x2="236" y2="40"/>
                        <polygon points="236,36 244,40 236,44" fill="currentColor"/>
                        <path d="M260 30 h28 v20 h-28 z"/>
                        <line x1="266" y1="36" x2="282" y2="36"/>
                        <line x1="266" y1="44" x2="282" y2="44"/>
                        <circle cx="36" cy="56" r="2"/><circle cx="44" cy="56" r="2"/><circle cx="52" cy="56" r="2"/>
                      </g>
                      <g fontSize="12" fill="currentColor" textAnchor="middle">
                        <text x="36" y="68">Prompt</text>
                        <text x="140" y="66">Agent</text>
                        <text x="274" y="66">Filter</text>
                      </g>
                      </svg>
                    </div>
                     <div className="mt-3 inline-flex items-center gap-1.5 bg-gray-800/70 text-gray-100 text-xs px-2.5 py-1 rounded-full font-medium"><CheckCircle2 className="w-4 h-4 text-green-400"/> Playbook</div>
                    <ul className="text-gray-300 text-sm list-disc list-inside space-y-1 mt-1">
                      <li>Sanitize inputs</li>
                      <li>Reset context</li>
                    </ul>
                   </div>
            </div>
          </div>

          {/* 6 Service Degradation */}
          <div id="threat-6" className={`relative rounded-lg overflow-hidden border-l-4 border-amber-500 bg-gradient-to-r from-amber-950/20 to-transparent ring-1 ring-amber-900/40 ${filter !== 'all' && filter !== 'H+M' ? 'hidden' : ''}`}>
            <div className="absolute top-2 right-2">
              <span className="text-xs font-bold text-amber-400 uppercase tracking-wider">High Priority</span>
            </div>
            <div className="w-full flex items-center justify-between px-4 py-3 text-left bg-gray-900/60">
              <div className="flex items-center gap-3"><span className="inline-flex items-center px-2.5 py-1 rounded-md bg-amber-900/40 border border-amber-600 text-amber-200 text-xs font-medium">H+M</span><Gauge className="w-4 h-4 text-amber-300"/><div className="text-white font-semibold">6) Service Degradation</div></div>
            </div>
            <div className="px-5 pb-5 grid md:grid-cols-1 gap-6">
                  <div>
                    <div className="text-xs inline-flex items-center gap-1 bg-gray-800/70 text-gray-100 px-2.5 py-1 rounded-full font-medium">💡 IDEA</div>
                    <p className="text-gray-200 text-sm mt-1 bg-gray-800/60 border border-gray-700 rounded p-3">Starts great. Degrades after lock‑in.</p>
                    <svg aria-hidden className="mt-3 w-full h-24 text-amber-400/80" viewBox="0 0 360 80">
                      <g fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <circle cx="40" cy="40" r="16"/>
                        <line x1="56" y1="40" x2="120" y2="40"/>
                        <polygon points="120,36 128,40 120,44" fill="currentColor"/>
                        <rect x="140" y="28" width="36" height="24" rx="4"/>
                        <line x1="176" y1="40" x2="240" y2="40"/>
                        <polygon points="240,36 248,40 240,44" fill="currentColor"/>
                        <polyline points="260,30 276,38 292,46"/>
                        <line x1="260" y1="50" x2="300" y2="30"/>
                        <polygon points="300,30 292,30 300,38" fill="currentColor"/>
                      </g>
                      <g fontSize="12" fill="currentColor" textAnchor="middle">
                        <text x="40" y="64">Start</text>
                        <text x="158" y="64">Service</text>
                        <text x="286" y="64">Degrade</text>
                      </g>
                      </svg>
                    </div>
                     <div className="mt-3 inline-flex items-center gap-1.5 bg-gray-800/70 text-gray-100 text-xs px-2.5 py-1 rounded-full font-medium"><CheckCircle2 className="w-4 h-4 text-green-400"/> Playbook</div>
                    <ul className="text-gray-300 text-sm list-disc list-inside space-y-1 mt-1">
                      <li>Periodic re‑tests</li>
                      <li>Graceful fallback</li>
                    </ul>
                   </div>
            </div>
          </div>

          {/* 7 Identity Theft */}
          <div id="threat-7" className={`relative rounded-lg overflow-hidden border-l-4 border-amber-500 bg-gradient-to-r from-amber-950/20 to-transparent ring-1 ring-amber-900/40 ${filter !== 'all' && filter !== 'H+M' ? 'hidden' : ''}`}>
            <div className="absolute top-2 right-2">
              <span className="text-xs font-bold text-amber-400 uppercase tracking-wider">High Priority</span>
            </div>
            <div className="w-full flex items-center justify-between px-4 py-3 text-left bg-gray-900/60">
              <div className="flex items-center gap-3"><span className="inline-flex items-center px-2.5 py-1 rounded-md bg-amber-900/40 border border-amber-600 text-amber-200 text-xs font-medium">H+M</span><IdCard className="w-4 h-4 text-amber-300"/><div className="text-white font-semibold">7) Identity Theft</div></div>
            </div>
            <div className="px-5 pb-5 grid md:grid-cols-1 gap-6">
                  <div>
                    <div className="text-xs inline-flex items-center gap-1 bg-gray-800/70 text-gray-100 px-2.5 py-1 rounded-full font-medium">💡 IDEA</div>
                    <p className="text-gray-200 text-sm mt-1 bg-gray-800/60 border border-gray-700 rounded p-3">Fake the brand; mimic behavior.</p>
                    <svg aria-hidden className="mt-3 w-full h-24 text-amber-400/80" viewBox="0 0 360 80">
                      <g fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <rect x="24" y="28" width="34" height="24" rx="4"/>
                        <rect x="74" y="28" width="34" height="24" rx="4"/>
                        <line x1="58" y1="40" x2="74" y2="40"/>
                        <polygon points="70,36 78,40 70,44" fill="currentColor"/>
                        <line x1="108" y1="40" x2="172" y2="40"/>
                        <polygon points="172,36 180,40 172,44" fill="currentColor"/>
                        <rect x="192" y="26" width="38" height="28" rx="6"/>
                        <line x1="230" y1="40" x2="296" y2="40"/>
                        <polygon points="296,36 304,40 296,44" fill="currentColor"/>
                        <circle cx="320" cy="40" r="14"/>
                      </g>
                      <g fontSize="12" fill="currentColor" textAnchor="middle">
                        <text x="41" y="66">ID</text>
                        <text x="91" y="66">Fake</text>
                        <text x="211" y="66">Brand</text>
                        <text x="320" y="66">User</text>
                      </g>
                      </svg>
                    </div>
                     <div className="mt-3 inline-flex items-center gap-1.5 bg-gray-800/70 text-gray-100 text-xs px-2.5 py-1 rounded-full font-medium"><CheckCircle2 className="w-4 h-4 text-green-400"/> Playbook</div>
                    <ul className="text-gray-300 text-sm list-disc list-inside space-y-1 mt-1">
                      <li>Pin source (hash/sign)</li>
                      <li>Show provenance</li>
                    </ul>
                   </div>
            </div>

          {/* 8 Supply Chain Poisoning */}
          <div id="threat-8" className={`relative rounded-lg overflow-hidden border-l-4 border-cyan-500 bg-gradient-to-r from-cyan-950/20 to-transparent ring-1 ring-cyan-900/40 ${filter !== 'all' && filter !== 'L+H' ? 'hidden' : ''}`}>
            <div className="absolute top-2 right-2">
              <span className="text-xs font-bold text-cyan-400 uppercase tracking-wider">Monitor</span>
            </div>
            <div className="w-full flex items-center justify-between px-4 py-3 text-left bg-gray-900/60">
              <div className="flex items-center gap-3"><span className="inline-flex items-center px-2.5 py-1 rounded-md bg-cyan-900/40 border border-cyan-600 text-cyan-200 text-xs font-medium">L+H</span><PackageSearch className="w-4 h-4 text-cyan-300"/><div className="text-white font-semibold">8) Supply Chain Poisoning</div></div>
            </div>
            <div className="px-5 pb-5 grid md:grid-cols-1 gap-6">
                  <div>
                    <div className="text-xs inline-flex items-center gap-1 bg-gray-800/70 text-gray-100 px-2.5 py-1 rounded-full font-medium">💡 IDEA</div>
                    <p className="text-gray-200 text-sm mt-1 bg-gray-800/60 border border-gray-700 rounded p-3">Poison upstream → break everyone downstream.</p>
                    <div className="mt-3 w-full h-32 flex items-center justify-center gap-8 text-cyan-400">
                      <div className="flex flex-col items-center gap-2">
                        <div className="w-20 h-12 rounded-lg border-2 border-current" />
                        <div className="text-xs">Upstream</div>
                      </div>
                      <ArrowRight className="w-6 h-6" />
                      <div className="flex flex-col items-center gap-2">
                        <div className="w-20 h-12 rounded-lg border-2 border-current" />
                        <div className="text-xs">Proxy</div>
                      </div>
                      <ArrowRight className="w-6 h-6" />
                      <div className="flex flex-col items-center gap-2">
                        <div className="relative w-20 h-12 rounded-lg border-2 border-current">
                          <div className="absolute left-2 top-2 right-2 bottom-2 border-t-2 border-current rotate-12" />
                        </div>
                        <div className="text-xs">Downstream</div>
                      </div>
                    </div>
                     <div className="mt-3 inline-flex items-center gap-1.5 bg-gray-800/70 text-gray-100 text-xs px-2.5 py-1 rounded-full font-medium"><CheckCircle2 className="w-4 h-4 text-green-400"/> Playbook</div>
                    <ul className="text-gray-300 text-sm list-disc list-inside space-y-1 mt-1">
                      <li>Lock deps & checksums</li>
                      <li>Vendor scan (SBOM)</li>
                    </ul>
                   </div>
            </div>
          </div>

          {/* 9 Privacy Inference */}
          <div id="threat-9" className={`relative rounded-lg overflow-hidden border-l-4 border-purple-500 bg-gradient-to-r from-purple-950/20 to-transparent ring-1 ring-purple-900/40 ${filter !== 'all' && filter !== 'P' ? 'hidden' : ''}`}>
            <div className="absolute top-2 right-2">
              <span className="text-xs font-bold text-purple-400 uppercase tracking-wider">Continuous</span>
            </div>
            <div className="w-full flex items-center justify-between px-4 py-3 text-left bg-gray-900/60">
              <div className="flex items-center gap-3"><span className="inline-flex items-center px-2.5 py-1 rounded-md bg-purple-900/40 border border-purple-600 text-purple-200 text-xs font-medium">P</span><Eye className="w-4 h-4 text-purple-300"/><div className="text-white font-semibold">9) Privacy Inference</div></div>
            </div>
            <div className="px-5 pb-5 grid md:grid-cols-1 gap-6">
                  <div>
                    <div className="text-xs inline-flex items-center gap-1 bg-gray-800/70 text-gray-100 px-2.5 py-1 rounded-full font-medium">💡 IDEA</div>
                    <p className="text-gray-200 text-sm mt-1 bg-gray-800/60 border border-gray-700 rounded p-3">Small harmless queries → big private picture.</p>
                    <svg aria-hidden className="mt-3 w-full h-32 text-purple-400/90" viewBox="0 0 360 80">
                      <g fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
                        <circle cx="40" cy="40" r="7"/>
                        <circle cx="62" cy="40" r="7"/>
                        <circle cx="84" cy="40" r="7"/>
                        <line x1="96" y1="40" x2="168" y2="40"/>
                        <polygon points="168,36 176,40 168,44" fill="currentColor"/>
                        <circle cx="220" cy="40" r="16"/>
                        <rect x="268" y="28" width="40" height="24" rx="12"/>
                      </g>
                      <g fontSize="12" fill="currentColor" textAnchor="middle">
                        <text x="62" y="64">Small queries</text>
                        <text x="220" y="64">Aggregate</text>
                        <text x="288" y="64">Profile</text>
                      </g>
                      </svg>
                    </div>
                     <div className="mt-3 inline-flex items-center gap-1.5 bg-gray-800/70 text-gray-100 text-xs px-2.5 py-1 rounded-full font-medium"><CheckCircle2 className="w-4 h-4 text-green-400"/> Playbook</div>
                    <ul className="text-gray-300 text-sm list-disc list-inside space-y-1 mt-1">
                      <li>Rate‑limit sensitive</li>
                      <li>Aggregate logs</li>
                    </ul>
                   </div>
            </div>

          {/* 10 Dependency Hijacking */}
          <div id="threat-10" className={`relative rounded-lg overflow-hidden border-l-4 border-cyan-500 bg-gradient-to-r from-cyan-950/20 to-transparent ring-1 ring-cyan-900/40 ${filter !== 'all' && filter !== 'L+H' ? 'hidden' : ''}`}>
            <div className="absolute top-2 right-2">
              <span className="text-xs font-bold text-cyan-400 uppercase tracking-wider">Monitor</span>
            </div>
            <div className="w-full flex items-center justify-between px-4 py-3 text-left bg-gray-900/60">
              <div className="flex items-center gap-3"><span className="inline-flex items-center px-2.5 py-1 rounded-md bg-cyan-900/40 border border-cyan-600 text-cyan-200 text-xs font-medium">L+H</span><PlugZap className="w-4 h-4 text-cyan-300"/><div className="text-white font-semibold">10) Dependency Hijacking</div></div>
            </div>
            <div className="px-5 pb-5 grid md:grid-cols-1 gap-6">
                  <div>
                    <div className="text-xs inline-flex items-center gap-1 bg-gray-800/70 text-gray-100 px-2.5 py-1 rounded-full font-medium">💡 IDEA</div>
                    <p className="text-gray-200 text-sm mt-1 bg-gray-800/60 border border-gray-700 rounded p-3">Cheap at first. Price hike when you depend on it.</p>
                    <svg aria-hidden className="mt-3 w-full h-24 text-cyan-400/80" viewBox="0 0 360 80">
                      <g fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <rect x="28" y="30" width="34" height="22" rx="4"/>
                        <line x1="62" y1="41" x2="120" y2="41"/>
                        <polygon points="120,37 128,41 120,45" fill="currentColor"/>
                        <rect x="140" y="30" width="34" height="22" rx="4"/>
                        <line x1="174" y1="41" x2="232" y2="41"/>
                        <polygon points="232,37 240,41 232,45" fill="currentColor"/>
                        <path d="M260 28 l18 0 l8 10 l-8 10 l-18 0 z"/>
                        <text x="268" y="45" fontSize="12" fill="currentColor">$</text>
                      </g>
                      <g fontSize="12" fill="currentColor" textAnchor="middle">
                        <text x="45" y="66">Package</text>
                        <text x="157" y="66">Registry</text>
                        <text x="270" y="66">Price</text>
                      </g>
                      </svg>
                    </div>
                     <div className="mt-3 inline-flex items-center gap-1.5 bg-gray-800/70 text-gray-100 text-xs px-2.5 py-1 rounded-full font-medium"><CheckCircle2 className="w-4 h-4 text-green-400"/> Playbook</div>
                    <ul className="text-gray-300 text-sm list-disc list-inside space-y-1 mt-1">
                      <li>Pin versions; export</li>
                      <li>Exit plan</li>
                    </ul>
            </div>
        </div>
      </Section>

      <div className="h-px bg-gray-800 my-10" />

      {/* Reference: Severity Matrix (moved below for calmer reading flow) */}
      <Section id="severity-matrix" title="Severity Matrix" icon={<Scale className="w-4 h-4 text-purple-300" />}> 
        <div className="grid md:grid-cols-2 lg:grid-cols-4 gap-3">
          <div className="rounded-lg border border-gray-800/80 bg-gray-900/40 hover:bg-gray-900/60 transition-colors p-3">
            <div className="text-white font-semibold text-xs mb-1">High Probability + High Impact</div>
            <div className="text-gray-400 text-[11px] mb-2 tracking-wide">Prioritize now</div>
            <ul className="text-gray-300 text-xs space-y-1">
              <li className="flex items-center gap-2"><span className="w-1.5 h-1.5 rounded-full bg-rose-400/90" /><a className="hover:text-white underline decoration-rose-400/30 hover:decoration-rose-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:ring-offset-2 focus:ring-offset-gray-900 rounded px-1" href="#threat-1">1) Capability Fraud</a></li>
              <li className="flex items-center gap-2"><span className="w-1.5 h-1.5 rounded-full bg-rose-400/90" /><a className="hover:text-white underline decoration-rose-400/30 hover:decoration-rose-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:ring-offset-2 focus:ring-offset-gray-900 rounded px-1" href="#threat-2">2) Data Harvesting</a></li>
              <li className="flex items-center gap-2"><span className="w-1.5 h-1.5 rounded-full bg-rose-400/90" /><a className="hover:text-white underline decoration-rose-400/30 hover:decoration-rose-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:ring-offset-2 focus:ring-offset-gray-900 rounded px-1" href="#threat-3">3) Cost Manipulation</a></li>
            </ul>
          </div>
          <div className="rounded-lg border border-gray-800/80 bg-gray-900/40 hover:bg-gray-900/60 transition-colors p-3">
            <div className="text-white font-semibold text-xs mb-1">High Probability + Medium Impact</div>
            <div className="text-gray-400 text-[11px] mb-2 tracking-wide">Mitigate early</div>
            <ul className="text-gray-300 text-xs space-y-1">
              <li className="flex items-center gap-2"><span className="w-1.5 h-1.5 rounded-full bg-amber-400/90" /><a className="hover:text-white underline decoration-amber-400/30 hover:decoration-amber-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:ring-offset-2 focus:ring-offset-gray-900 rounded px-1" href="#threat-5">5) Prompt Poisoning</a></li>
              <li className="flex items-center gap-2"><span className="w-1.5 h-1.5 rounded-full bg-amber-400/90" /><a className="hover:text-white underline decoration-amber-400/30 hover:decoration-amber-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:ring-offset-2 focus:ring-offset-gray-900 rounded px-1" href="#threat-6">6) Service Degradation</a></li>
              <li className="flex items-center gap-2"><span className="w-1.5 h-1.5 rounded-full bg-amber-400/90" /><a className="hover:text-white underline decoration-amber-400/30 hover:decoration-amber-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:ring-offset-2 focus:ring-offset-gray-900 rounded px-1" href="#threat-7">7) Identity Theft</a></li>
            </ul>
          </div>
          <div className="rounded-lg border border-gray-800/80 bg-gray-900/40 hover:bg-gray-900/60 transition-colors p-3">
            <div className="text-white font-semibold text-xs mb-1">Low Probability + High Impact</div>
            <div className="text-gray-400 text-[11px] mb-2 tracking-wide">Plan containment</div>
            <ul className="text-gray-300 text-xs space-y-1">
              <li className="flex items-center gap-2"><span className="w-1.5 h-1.5 rounded-full bg-cyan-400/90" /><a className="hover:text-white underline decoration-cyan-400/30 hover:decoration-cyan-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:ring-offset-2 focus:ring-offset-gray-900 rounded px-1" href="#threat-4">4) Collusion Attacks</a></li>
              <li className="flex items-center gap-2"><span className="w-1.5 h-1.5 rounded-full bg-cyan-400/90" /><a className="hover:text-white underline decoration-cyan-400/30 hover:decoration-cyan-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:ring-offset-2 focus:ring-offset-gray-900 rounded px-1" href="#threat-8">8) Supply Chain Poisoning</a></li>
              <li className="flex items-center gap-2"><span className="w-1.5 h-1.5 rounded-full bg-cyan-400/90" /><a className="hover:text-white underline decoration-cyan-400/30 hover:decoration-cyan-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:ring-offset-2 focus:ring-offset-gray-900 rounded px-1" href="#threat-10">10) Dependency Hijacking</a></li>
            </ul>
          </div>
          <div className="rounded-lg border border-gray-800/80 bg-gray-900/40 hover:bg-gray-900/60 transition-colors p-3">
            <div className="text-white font-semibold text-xs mb-1">Persistent Threat</div>
            <div className="text-gray-400 text-[11px] mb-2 tracking-wide">Continuous guard</div>
            <ul className="text-gray-300 text-xs space-y-1">
              <li className="flex items-center gap-2"><span className="w-1.5 h-1.5 rounded-full bg-purple-400/90" /><a className="hover:text-white underline decoration-purple-400/30 hover:decoration-purple-400 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:ring-offset-2 focus:ring-offset-gray-900 rounded px-1" href="#threat-9">9) Privacy Inference</a></li>
            </ul>
          </div>
        </div>
      </Section>

      <div className="h-px bg-gray-800 my-10" />

      {/* Key Insights */}
      <Section id="key-insights" title="Key Insights" icon={<Layers className="w-4 h-4 text-cyan-300" />}> 
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-2">
          <div className="rounded-md border border-gray-800 bg-gray-900/40 hover:bg-gray-900/60 hover:border-gray-700 transition-colors px-2.5 py-2 flex items-center gap-2"><Layers className="w-4 h-4 text-cyan-300"/><p className="text-gray-300 text-sm">Profit drives attacks</p></div>
          <div className="rounded-md border border-gray-800 bg-gray-900/40 hover:bg-gray-900/60 hover:border-gray-700 transition-colors px-2.5 py-2 flex items-center gap-2"><Layers className="w-4 h-4 text-cyan-300"/><p className="text-gray-300 text-sm">Claims are cheap; proof is costly</p></div>
          <div className="rounded-md border border-gray-800 bg-gray-900/40 hover:bg-gray-900/60 hover:border-gray-700 transition-colors px-2.5 py-2 flex items-center gap-2"><Layers className="w-4 h-4 text-cyan-300"/><p className="text-gray-300 text-sm">Scale multiplies risk</p></div>
          <div className="rounded-md border border-gray-800 bg-gray-900/40 hover:bg-gray-900/60 hover:border-gray-700 transition-colors px-2.5 py-2 flex items-center gap-2"><Layers className="w-4 h-4 text-cyan-300"/><p className="text-gray-300 text-sm">Composition → cascades</p></div>
          <div className="rounded-md border border-gray-800 bg-gray-900/40 hover:bg-gray-900/60 hover:border-gray-700 transition-colors px-2.5 py-2 flex items-center gap-2"><Layers className="w-4 h-4 text-cyan-300"/><p className="text-gray-300 text-sm">Strong defaults beat rules</p></div>
          <div className="rounded-md border border-gray-800 bg-gray-900/40 hover:bg-gray-900/60 hover:border-gray-700 transition-colors px-2.5 py-2 flex items-center gap-2"><Layers className="w-4 h-4 text-cyan-300"/><p className="text-gray-300 text-sm">Local‑first reduces surface</p></div>
        </div>
      </Section>

      <div className="h-px bg-gray-800 my-10" />

      {/* Defensive Principles */}
      <Section id="defensive-principles" title="Defensive Principles" icon={<Zap className="w-4 h-4 text-rose-300" />}> 
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-2">
          <div className="rounded-md border border-gray-800 bg-gray-900/40 hover:bg-gray-900/60 hover:border-gray-700 transition-colors px-2.5 py-2 flex items-center gap-2"><Zap className="w-4 h-4 text-rose-300"/><p className="text-gray-300 text-sm">Cost &gt; payoff</p></div>
          <div className="rounded-md border border-gray-800 bg-gray-900/40 hover:bg-gray-900/60 hover:border-gray-700 transition-colors px-2.5 py-2 flex items-center gap-2"><Zap className="w-4 h-4 text-rose-300"/><p className="text-gray-300 text-sm">Bound damage</p></div>
          <div className="rounded-md border border-gray-800 bg-gray-900/40 hover:bg-gray-900/60 hover:border-gray-700 transition-colors px-2.5 py-2 flex items-center gap-2"><Zap className="w-4 h-4 text-rose-300"/><p className="text-gray-300 text-sm">Audit actions</p></div>
          <div className="rounded-md border border-gray-800 bg-gray-900/40 hover:bg-gray-900/60 hover:border-gray-700 transition-colors px-2.5 py-2 flex items-center gap-2"><Zap className="w-4 h-4 text-rose-300"/><p className="text-gray-300 text-sm">Improve under stress</p></div>
          <div className="rounded-md border border-gray-800 bg-gray-900/40 hover:bg-gray-900/60 hover:border-gray-700 transition-colors px-2.5 py-2 flex items-center gap-2"><Zap className="w-4 h-4 text-rose-300"/><p className="text-gray-300 text-sm">Fast recovery</p></div>
        </div>
      </Section>

      <div className="mt-8 text-sm text-gray-500 flex items-center gap-2">
        <LinkIcon className="w-3.5 h-3.5" /> Anchor links are available on section headings.
      </div>
    </div>
  )
}

