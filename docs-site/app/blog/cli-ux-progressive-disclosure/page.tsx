import Link from 'next/link'
import { ArrowLeft } from 'lucide-react'

export default function CLIProgressiveDisclosurePage() {
  return (
    <div className="max-w-4xl mx-auto px-4 py-12">
      <Link href="/blog" className="inline-flex items-center gap-2 text-purple-400 hover:text-purple-300 mb-8 transition-colors">
        <ArrowLeft className="w-4 h-4" />
        Back to Blog
      </Link>
      
      <article className="prose prose-invert max-w-none">
        <h1 className="text-4xl font-bold bg-gradient-to-r from-purple-400 to-pink-400 bg-clip-text text-transparent mb-4">
          Why We Choose Progressive Disclosure Over Configuration Questionnaires
        </h1>
        
        <div className="text-gray-400 mb-8">
          <time>September 4, 2025</time> • Design Decision
        </div>
        
        <div className="bg-purple-500/10 border border-purple-500/20 rounded-lg p-6 mb-8">
          <p className="text-lg text-gray-300 leading-relaxed m-0">
            Most framework CLIs bombard users with questions that don't matter yet. 
            We chose progressive disclosure: start fast, decide later, respect intelligence.
          </p>
        </div>

        <h2 className="text-2xl font-semibold text-white mt-12 mb-4">The Problem with Traditional CLIs</h2>
        
        <div className="bg-gray-800 rounded-lg p-6 mb-6">
          <p className="text-gray-400 mb-4">Typical framework initialization:</p>
          <ul className="space-y-2 text-gray-300">
            <li>• What's your project description? <span className="text-gray-500">(I don't know, I just started)</span></li>
            <li>• Choose your testing framework? <span className="text-gray-500">(Let me build something first)</span></li>
            <li>• Configure your linter settings? <span className="text-gray-500">(Please, just let me code)</span></li>
            <li>• Set up CI/CD pipeline? <span className="text-gray-500">(It's my first 5 seconds with this tool)</span></li>
          </ul>
        </div>
        
        <p className="text-gray-300 leading-relaxed">
          This approach assumes users know everything upfront. Reality: they don't, and they shouldn't have to.
        </p>

        <h2 className="text-2xl font-semibold text-white mt-8 mb-4">Our Philosophy: Progressive Disclosure</h2>
        
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
          <div className="bg-purple-500/10 border border-purple-500/20 rounded-lg p-4 text-center">
            <div className="text-3xl font-bold text-purple-400 mb-2">&lt; 30s</div>
            <p className="text-gray-300 text-sm">To working code</p>
          </div>
          <div className="bg-purple-500/10 border border-purple-500/20 rounded-lg p-4 text-center">
            <div className="text-3xl font-bold text-purple-400 mb-2">3</div>
            <p className="text-gray-300 text-sm">Questions maximum</p>
          </div>
          <div className="bg-purple-500/10 border border-purple-500/20 rounded-lg p-4 text-center">
            <div className="text-3xl font-bold text-purple-400 mb-2">0</div>
            <p className="text-gray-300 text-sm">Required configs</p>
          </div>
        </div>

        <h2 className="text-2xl font-semibold text-white mt-8 mb-4">The Two-Command Strategy</h2>
        
        <div className="bg-gray-800 rounded-lg p-4 font-mono text-sm mb-6">
          <span className="text-gray-500"># Outside a project</span><br/>
          co create my-agent&nbsp;&nbsp;<span className="text-green-400"># Creates new directory</span><br/>
          <br/>
          <span className="text-gray-500"># Inside a project</span><br/>
          co init&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;<span className="text-green-400"># Uses current directory</span>
        </div>
        
        <p className="text-gray-300 leading-relaxed mb-4">
          Why both? Because <strong className="text-white">context matters</strong>:
        </p>
        
        <ul className="space-y-2 text-gray-300 mb-6">
          <li>• Outside: Users want to create a new space</li>
          <li>• Inside: Users have already decided where to work</li>
        </ul>
        
        <p className="text-gray-300 leading-relaxed">
          This isn't redundancy; it's respecting user intent. Django does this, Rails does this, 
          and for good reason.
        </p>

        <h2 className="text-2xl font-semibold text-white mt-8 mb-4">Minimal Questions, Maximum Intelligence</h2>
        
        <div className="bg-purple-500/10 border border-purple-500/20 rounded-lg p-6 mb-6">
          <p className="text-purple-400 font-semibold mb-2">Our setup asks only what matters RIGHT NOW:</p>
          <ol className="space-y-2 text-gray-300">
            <li>1. <strong className="text-white">Enable AI?</strong> - Determines available templates</li>
            <li>2. <strong className="text-white">API key</strong> - Only if AI enabled, with auto-detection</li>
            <li>3. <strong className="text-white">Template</strong> - With previews so users know what they get</li>
          </ol>
          <p className="text-gray-400 text-sm mt-4">That's it. Three decisions max.</p>
        </div>
        
        <p className="text-gray-300 leading-relaxed">
          Compare to typical CLIs: Create-react-app (5+ questions), Vue CLI (10+ questions), 
          Yeoman generators (often 15+ questions).
        </p>

        <h2 className="text-2xl font-semibold text-white mt-8 mb-4">Smart API Key Detection</h2>
        
        <div className="bg-gray-800 rounded-lg p-4 font-mono text-sm mb-6">
          <span className="text-blue-400">if</span> api_key.startswith(<span className="text-green-400">'sk-proj-'</span>):<br/>
          &nbsp;&nbsp;<span className="text-gray-500"># OpenAI project key</span><br/>
          <span className="text-blue-400">elif</span> api_key.startswith(<span className="text-green-400">'sk-ant-'</span>):<br/>
          &nbsp;&nbsp;<span className="text-gray-500"># Anthropic</span><br/>
          <span className="text-blue-400">elif</span> api_key.startswith(<span className="text-green-400">'gsk_'</span>):<br/>
          &nbsp;&nbsp;<span className="text-gray-500"># Groq</span>
        </div>
        
        <p className="text-gray-300 leading-relaxed">
          The key format already tells us the provider. Why make users answer what we can infer?
        </p>

        <h2 className="text-2xl font-semibold text-white mt-8 mb-4">Template Preview, Not Template Guessing</h2>
        
        <div className="bg-gray-800 rounded-lg p-6 mb-6">
          <pre className="text-sm text-gray-300">
📦 Minimal - Simple starting point
  ├── agent.py (50 lines) - Basic agent with example tool
  ├── .env - API key configuration
  └── .co/ - Agent identity & metadata</pre>
        </div>
        
        <p className="text-gray-300 leading-relaxed">
          Users shouldn't have to guess. Show them, let them choose, move on.
        </p>

        <h2 className="text-2xl font-semibold text-white mt-8 mb-4">Silent Excellence</h2>
        
        <div className="bg-gray-800 rounded-lg p-4 font-mono text-sm mb-6">
          <span className="text-gray-500"># This happens silently during init</span><br/>
          addr_data = address.generate()<br/>
          address.save(addr_data, co_dir)
        </div>
        
        <p className="text-gray-300 leading-relaxed">
          We generate cryptographic keys automatically. No prompt, no explanation. 
          99% of users don't care about Ed25519 vs secp256k1. The 1% who do can read the docs.
        </p>

        <h2 className="text-2xl font-semibold text-white mt-8 mb-4">What We Don't Ask</h2>
        
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-8">
          <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-4">
            <h3 className="text-red-400 font-semibold mb-2">❌ We Skip</h3>
            <ul className="space-y-1 text-gray-400 text-sm">
              <li>• Project description</li>
              <li>• Author name</li>
              <li>• License type</li>
              <li>• Version number</li>
              <li>• Test framework</li>
              <li>• Package manager</li>
            </ul>
          </div>
          
          <div className="bg-green-500/10 border border-green-500/20 rounded-lg p-4">
            <h3 className="text-green-400 font-semibold mb-2">✅ We Do</h3>
            <ul className="space-y-1 text-gray-400 text-sm">
              <li>• Create working code immediately</li>
              <li>• Use sensible defaults everywhere</li>
              <li>• Show clear next steps</li>
              <li>• Get out of the way</li>
            </ul>
          </div>
        </div>

        <h2 className="text-2xl font-semibold text-white mt-8 mb-4">Beautiful by Default</h2>
        
        <div className="bg-gray-800 rounded-lg p-6 mb-6">
          <p className="text-gray-300 mb-4">We use colors and emojis for <strong className="text-white">clarity</strong>, not decoration:</p>
          <ul className="space-y-2">
            <li><span className="text-green-400">✅ Green</span> = Success</li>
            <li><span className="text-yellow-400">⚠️ Yellow</span> = Warning</li>
            <li><span className="text-red-400">❌ Red</span> = Error</li>
            <li>📁 Icons = Visual scanning</li>
          </ul>
        </div>
        
        <p className="text-gray-300 leading-relaxed">
          But we respect terminal preferences: works in non-color terminals, copy-paste friendly, 
          no ASCII art or unnecessary flair.
        </p>

        <h2 className="text-2xl font-semibold text-white mt-8 mb-4">Results: User Delight</h2>
        
        <div className="bg-gradient-to-r from-purple-500/10 to-pink-500/10 rounded-lg p-6 border border-purple-500/20">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-center">
            <div>
              <div className="text-2xl font-bold text-purple-400">30s</div>
              <p className="text-gray-400 text-sm">to running agent</p>
            </div>
            <div>
              <div className="text-2xl font-bold text-purple-400">3</div>
              <p className="text-gray-400 text-sm">questions max</p>
            </div>
            <div>
              <div className="text-2xl font-bold text-purple-400">0</div>
              <p className="text-gray-400 text-sm">required configs</p>
            </div>
            <div>
              <div className="text-2xl font-bold text-purple-400">1</div>
              <p className="text-gray-400 text-sm">command to start</p>
            </div>
          </div>
        </div>

        <h2 className="text-2xl font-semibold text-white mt-12 mb-4">Conclusion</h2>
        
        <div className="bg-purple-500/10 border border-purple-500/20 rounded-lg p-6">
          <p className="text-lg text-gray-300 leading-relaxed m-0">
            Good CLI UX isn't about asking fewer questions - it's about asking the 
            <strong className="text-white">RIGHT</strong> questions at the 
            <strong className="text-white">RIGHT</strong> time. Everything else should be 
            invisible, automatic, or optional.
          </p>
          <p className="text-gray-400 mt-4">
            The best tool is one you forget you're using. That's what we built.
          </p>
        </div>
      </article>
    </div>
  )
}