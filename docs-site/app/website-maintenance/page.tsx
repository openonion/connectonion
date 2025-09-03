import { ArrowLeft, FileText, Code, Search, GitBranch, CheckCircle, AlertCircle } from 'lucide-react'
import Link from 'next/link'
import { CommandBlock } from '../../components/CommandBlock'
import { ContentNavigation } from '../../components/ContentNavigation'

export default function WebsiteMaintenancePage() {
  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      <Link href="/" className="inline-flex items-center text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 mb-8 transition-colors">
        <ArrowLeft className="mr-2 h-4 w-4" />
        Back to Home
      </Link>
      
      <h1 className="text-4xl font-bold mb-4 bg-gradient-to-r from-blue-500 to-purple-600 bg-clip-text text-transparent">
        Website Maintenance Guide
      </h1>
      <p className="text-xl text-gray-600 dark:text-gray-400 mb-12">
        Learn how to add new features, pages, and content to the documentation website.
      </p>

      <div className="space-y-12">
        {/* Overview */}
        <section>
          <h2 className="text-2xl font-semibold mb-4 flex items-center">
            <FileText className="mr-2 h-6 w-6 text-blue-500" />
            Three-Step Process
          </h2>
          <div className="bg-gradient-to-r from-blue-50 to-purple-50 dark:from-gray-800 dark:to-gray-800 p-6 rounded-lg border border-blue-200 dark:border-gray-700">
            <ol className="space-y-3">
              <li className="flex items-start">
                <span className="bg-blue-500 text-white rounded-full w-6 h-6 flex items-center justify-center text-sm font-bold mr-3 mt-0.5">1</span>
                <div>
                  <strong>Create Tutorial</strong> - Write markdown in <code className="bg-gray-100 dark:bg-gray-700 px-2 py-0.5 rounded">/tutorials/</code>
                </div>
              </li>
              <li className="flex items-start">
                <span className="bg-purple-500 text-white rounded-full w-6 h-6 flex items-center justify-center text-sm font-bold mr-3 mt-0.5">2</span>
                <div>
                  <strong>Create Page</strong> - Add component in <code className="bg-gray-100 dark:bg-gray-700 px-2 py-0.5 rounded">/app/</code>
                </div>
              </li>
              <li className="flex items-start">
                <span className="bg-green-500 text-white rounded-full w-6 h-6 flex items-center justify-center text-sm font-bold mr-3 mt-0.5">3</span>
                <div>
                  <strong>Update Navigation</strong> - Add to sidebar and search
                </div>
              </li>
            </ol>
          </div>
        </section>

        {/* Step 1: Create Tutorial */}
        <section>
          <h2 className="text-2xl font-semibold mb-4">Step 1: Create Tutorial Content</h2>
          <p className="text-gray-600 dark:text-gray-400 mb-4">
            Start by writing your documentation as a markdown file:
          </p>
          <CommandBlock commands={['touch docs-site/public/tutorials/your-feature.md']} />
          
          <div className="mt-6">
            <h3 className="text-lg font-medium mb-3">Markdown Structure</h3>
            <pre className="bg-gray-900 text-gray-100 p-4 rounded-lg overflow-x-auto">
              <code>{`# Feature Title

## Overview
What the feature does and why it's useful.

## Basic Usage
\`\`\`python
agent = Agent("assistant")
result = agent.input("Hello!")
\`\`\`

## Advanced Usage
Complex examples and edge cases.

## API Reference
Detailed technical documentation.`}</code>
            </pre>
          </div>
        </section>

        {/* Step 2: Create Page */}
        <section>
          <h2 className="text-2xl font-semibold mb-4">Step 2: Create Page Component</h2>
          <p className="text-gray-600 dark:text-gray-400 mb-4">
            Create a Next.js page for your feature:
          </p>
          <CommandBlock commands={[
            'mkdir -p docs-site/app/your-feature',
            'touch docs-site/app/your-feature/page.tsx'
          ]} />
          
          <div className="mt-6">
            <h3 className="text-lg font-medium mb-3">Page Template</h3>
            <pre className="bg-gray-900 text-gray-100 p-4 rounded-lg overflow-x-auto text-sm">
              <code>{`import { ArrowLeft } from 'lucide-react'
import Link from 'next/link'

export default function YourFeaturePage() {
  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      <Link href="/" className="inline-flex items-center mb-8">
        <ArrowLeft className="mr-2 h-4 w-4" />
        Back to Home
      </Link>
      
      <h1 className="text-4xl font-bold mb-8">
        Your Feature
      </h1>
      
      {/* Your content */}
    </div>
  )
}`}</code>
            </pre>
          </div>
        </section>

        {/* Step 3: Update Navigation */}
        <section>
          <h2 className="text-2xl font-semibold mb-4">Step 3: Update Navigation</h2>
          
          <div className="space-y-6">
            <div>
              <h3 className="text-lg font-medium mb-3">Add to Sidebar</h3>
              <p className="text-gray-600 dark:text-gray-400 mb-3">
                Edit <code className="bg-gray-100 dark:bg-gray-700 px-2 py-0.5 rounded">DocsSidebar.tsx</code>:
              </p>
              <pre className="bg-gray-900 text-gray-100 p-4 rounded-lg overflow-x-auto text-sm">
                <code>{`const navigation = [
  {
    title: 'Your Section',
    items: [
      { 
        title: 'Your Feature', 
        href: '/your-feature',
        icon: YourIcon,
        keywords: ['keyword1', 'keyword2']
      }
    ]
  }
]`}</code>
              </pre>
            </div>

            <div>
              <h3 className="text-lg font-medium mb-3">Update Search Mapping</h3>
              <p className="text-gray-600 dark:text-gray-400 mb-3">
                Edit <code className="bg-gray-100 dark:bg-gray-700 px-2 py-0.5 rounded">markdownLoader.ts</code>:
              </p>
              <pre className="bg-gray-900 text-gray-100 p-4 rounded-lg overflow-x-auto text-sm">
                <code>{`const MARKDOWN_TO_PAGE_MAP = {
  'your-feature.md': { 
    href: '/your-feature',
    section: 'Your Section',
    title: 'Your Feature' 
  }
}`}</code>
              </pre>
            </div>
          </div>
        </section>

        {/* Testing */}
        <section>
          <h2 className="text-2xl font-semibold mb-4 flex items-center">
            <Code className="mr-2 h-6 w-6 text-green-500" />
            Testing Your Changes
          </h2>
          
          <div className="space-y-4">
            <CommandBlock commands={[
              'cd docs-site',
              'npm run dev'
            ]} />
            
            <div className="bg-yellow-50 dark:bg-yellow-900/20 p-4 rounded-lg border border-yellow-200 dark:border-yellow-800">
              <h3 className="font-medium mb-2 flex items-center">
                <AlertCircle className="mr-2 h-5 w-5 text-yellow-600" />
                Test Checklist
              </h3>
              <ul className="space-y-1 text-sm">
                <li>✓ Search finds your content</li>
                <li>✓ Sidebar link works</li>
                <li>✓ Page displays correctly</li>
                <li>✓ Mobile responsive</li>
                <li>✓ Build succeeds</li>
              </ul>
            </div>
          </div>
        </section>

        {/* Quick Reference */}
        <section>
          <h2 className="text-2xl font-semibold mb-4 flex items-center">
            <GitBranch className="mr-2 h-6 w-6 text-purple-500" />
            Directory Structure
          </h2>
          
          <pre className="bg-gray-900 text-gray-100 p-4 rounded-lg overflow-x-auto text-sm">
            <code>{`docs-site/
├── app/                    # Next.js pages
│   └── your-feature/      
│       └── page.tsx
├── components/            # Reusable components
│   └── DocsSidebar.tsx   
├── public/
│   └── tutorials/        # Markdown docs
│       └── your-feature.md
└── utils/
    └── markdownLoader.ts # Search index`}</code>
          </pre>
        </section>

        {/* Final Checklist */}
        <section className="bg-gradient-to-r from-green-50 to-blue-50 dark:from-gray-800 dark:to-gray-800 p-6 rounded-lg border border-green-200 dark:border-gray-700">
          <h2 className="text-2xl font-semibold mb-4 flex items-center">
            <CheckCircle className="mr-2 h-6 w-6 text-green-500" />
            Final Checklist
          </h2>
          
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <label className="flex items-center space-x-2">
              <input type="checkbox" className="rounded" />
              <span>Created tutorial markdown</span>
            </label>
            <label className="flex items-center space-x-2">
              <input type="checkbox" className="rounded" />
              <span>Created page component</span>
            </label>
            <label className="flex items-center space-x-2">
              <input type="checkbox" className="rounded" />
              <span>Added to sidebar</span>
            </label>
            <label className="flex items-center space-x-2">
              <input type="checkbox" className="rounded" />
              <span>Updated search mapping</span>
            </label>
            <label className="flex items-center space-x-2">
              <input type="checkbox" className="rounded" />
              <span>Added keywords</span>
            </label>
            <label className="flex items-center space-x-2">
              <input type="checkbox" className="rounded" />
              <span>Tested search</span>
            </label>
            <label className="flex items-center space-x-2">
              <input type="checkbox" className="rounded" />
              <span>Verified responsive</span>
            </label>
            <label className="flex items-center space-x-2">
              <input type="checkbox" className="rounded" />
              <span>Build successful</span>
            </label>
          </div>
        </section>

        {/* Navigation */}
        <ContentNavigation />
      </div>
    </div>
  )
}