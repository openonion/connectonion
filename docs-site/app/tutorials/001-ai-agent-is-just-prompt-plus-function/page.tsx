'use client'

import { useState } from 'react'
import Link from 'next/link'
import { CommandBlock } from '../../../components/CommandBlock'
import CodeWithResult from '../../../components/CodeWithResult'
import { PageCopyButton } from '../../../components/PageCopyButton'
import { ContentNavigation } from '../../../components/ContentNavigation'
import {
  ArrowRight, BookOpen, Code, AlertTriangle, Timer, CheckCircle,
  XCircle, Target, ChevronRight, Users, Star, TrendingDown
} from 'lucide-react'

const translations = {
  en: {
    title: 'AI Agent = Prompt + Function',
    subtitle: 'The truth about those $199 courses - and why you don\'t need them',
    readTime: '5 min read',
    formula: 'AI Agent = Prompt + Function',
    truth: 'The Truth About Those $199 Courses',
    selling: 'People are selling expensive courses for what\'s essentially a simple concept:',
    secretFormula: 'The "Secret" Formula',
    entireCourse: 'That\'s it. That\'s the entire course. Let me show you why.',
    whyBuilt: 'Why I Built ConnectOnion',
    myStory: 'I was building a project with LangChain and got frustrated:',
    seeDifference: 'See the Difference',
    langchainTitle: 'LangChain: 67 lines of complexity',
    connectonionTitle: 'ConnectOnion: 5 lines of simplicity',
    sameResult: 'Same result. 93% less code.',
    getStarted: 'Get Started in 30 Seconds',
    step1: 'Install the package',
    step2: 'Write your first agent',
    whatYouLearn: 'What You\'ll Learn',
    lesson1: 'AI agents are just ChatGPT that can call functions',
    lesson2: 'You don\'t need complex abstractions',
    lesson3: 'Simple solutions are often the best solutions',
    nextSteps: 'Ready to Build?',
    quickStart: 'Quick Start Guide',
    examples: 'Browse Examples'
  },
  zh: {
    title: 'AI Agent = 提示词 + 函数',
    subtitle: '那些199美元课程的真相 - 以及为什么你不需要它们',
    readTime: '5分钟阅读',
    formula: 'AI Agent = 提示词 + 函数',
    truth: '那些199美元课程的真相',
    selling: '人们在为一个本质上简单的概念销售昂贵的课程：',
    secretFormula: '"秘密"公式',
    entireCourse: '就是这样。整个课程就是这些。让我告诉你为什么。',
    whyBuilt: '为什么我创建了ConnectOnion',
    myStory: '我在用LangChain做项目时感到沮丧：',
    seeDifference: '看看区别',
    langchainTitle: 'LangChain：67行的复杂性',
    connectonionTitle: 'ConnectOnion：5行的简单性',
    sameResult: '相同的结果。少93%的代码。',
    getStarted: '30秒开始',
    step1: '安装包',
    step2: '编写你的第一个代理',
    whatYouLearn: '你将学到什么',
    lesson1: 'AI代理只是可以调用函数的ChatGPT',
    lesson2: '你不需要复杂的抽象',
    lesson3: '简单的解决方案往往是最好的解决方案',
    nextSteps: '准备构建？',
    quickStart: '快速入门指南',
    examples: '浏览示例'
  },
  ja: {
    title: 'AIエージェント = プロンプト + 関数',
    subtitle: '$199コースの真実 - そしてなぜ必要ないのか',
    readTime: '5分で読める',
    formula: 'AIエージェント = プロンプト + 関数',
    truth: '$199コースの真実',
    selling: '人々は本質的にシンプルなコンセプトのために高価なコースを販売しています：',
    secretFormula: '"秘密"の公式',
    entireCourse: 'それだけです。それがコース全体です。なぜかお見せしましょう。',
    whyBuilt: 'なぜConnectOnionを作ったか',
    myStory: 'LangChainでプロジェクトを構築していてイライラしました：',
    seeDifference: '違いを見てください',
    langchainTitle: 'LangChain：67行の複雑さ',
    connectonionTitle: 'ConnectOnion：5行のシンプルさ',
    sameResult: '同じ結果。93%少ないコード。',
    getStarted: '30秒で始める',
    step1: 'パッケージをインストール',
    step2: '最初のエージェントを書く',
    whatYouLearn: '学べること',
    lesson1: 'AIエージェントは関数を呼び出せるChatGPTに過ぎない',
    lesson2: '複雑な抽象化は必要ない',
    lesson3: 'シンプルな解決策が最良の解決策であることが多い',
    nextSteps: '構築の準備はできましたか？',
    quickStart: 'クイックスタートガイド',
    examples: '例を見る'
  }
}

// Code samples
const langchainCode = `from langchain.agents import Tool, AgentExecutor, LLMSingleActionAgent
from langchain.prompts import StringPromptTemplate
from langchain.chains import LLMChain
from langchain.schema import AgentAction, AgentFinish
from langchain.chat_models import ChatOpenAI
# ... 20 more imports ...

class CustomPromptTemplate(StringPromptTemplate):
    # ... 30 lines of boilerplate ...

class CustomOutputParser:
    # ... 25 lines of parsing logic ...

# Finally create the agent (line 67)
agent_executor = AgentExecutor.from_agent_and_tools(...)
result = agent_executor.run("What's the weather in San Francisco?")`

const connectonionCode = `from connectonion import Agent

def get_weather(city: str) -> str:
    return f"The weather in {city} is sunny, 72°F"

agent = Agent("weather_bot", tools=[get_weather])
result = agent.input("What's the weather in San Francisco?")`

export default function Tutorial001Page() {
  const [language, setLanguage] = useState<'en' | 'zh' | 'ja'>('en')
  const t = translations[language]

  return (
    <div className="px-4 md:px-8 py-8 md:py-12">
      {/* Constrained content width for optimal reading */}
      <div className="max-w-4xl mx-auto">

        {/* Header Section */}
        <div className="mb-12">
          {/* Breadcrumb */}
          <nav className="flex items-center gap-2 text-sm text-gray-400 mb-6">
            <Link href="/" className="hover:text-white transition-colors">
              Home
            </Link>
            <ArrowRight className="w-4 h-4" />
            <Link href="/tutorials" className="hover:text-white transition-colors">
              Tutorials
            </Link>
            <ArrowRight className="w-4 h-4" />
            <span className="text-white">001: AI Agent = Prompt + Function</span>
          </nav>

          {/* Title and Meta */}
          <div className="flex items-start justify-between mb-6">
            <div className="flex-1">
              <div className="flex items-center gap-3 mb-4">
                <span className="inline-flex items-center gap-2 px-3 py-1 bg-purple-600/10 text-purple-400 rounded-full text-sm border border-purple-600/20">
                  <BookOpen className="w-4 h-4" />
                  Tutorial 001
                </span>
                <span className="text-sm text-gray-400 flex items-center gap-2">
                  <Timer className="w-4 h-4" />
                  {t.readTime}
                </span>
              </div>

              <h1 className="text-4xl md:text-5xl font-bold text-white mb-4">
                {t.title}
              </h1>

              <p className="text-lg text-gray-300">
                {t.subtitle}
              </p>
            </div>

            {/* Language Switcher and Copy Button */}
            <div className="flex items-center gap-2 ml-6">
              <select
                value={language}
                onChange={(e) => setLanguage(e.target.value as 'en' | 'zh' | 'ja')}
                className="px-3 py-1.5 bg-gray-800 border border-gray-700 rounded-lg text-sm text-white focus:border-purple-500 focus:outline-none"
              >
                <option value="en">English</option>
                <option value="zh">中文</option>
                <option value="ja">日本語</option>
              </select>
              <PageCopyButton />
            </div>
          </div>
        </div>

        {/* Main Content */}
        <article className="prose prose-invert prose-lg max-w-none">

          {/* Section 1: The Truth */}
          <section className="mb-16">
            <h2 className="text-2xl md:text-3xl font-bold text-white mb-6 flex items-center gap-3">
              <AlertTriangle className="w-6 h-6 text-orange-500" />
              {t.truth}
            </h2>

            <p className="text-gray-300 mb-6">
              {t.selling}
            </p>

            {/* Course Examples - Simplified */}
            <div className="space-y-3 mb-8">
              <div className="flex items-center justify-between p-4 bg-gray-800/50 rounded-lg border border-gray-700">
                <span className="text-gray-300">"Master LangChain in 30 Days!"</span>
                <span className="text-xl font-bold text-red-400">$199</span>
              </div>
              <div className="flex items-center justify-between p-4 bg-gray-800/50 rounded-lg border border-gray-700">
                <span className="text-gray-300">"AutoGen Expert Certification"</span>
                <span className="text-xl font-bold text-red-400">$299</span>
              </div>
              <div className="flex items-center justify-between p-4 bg-gray-800/50 rounded-lg border border-gray-700">
                <span className="text-gray-300">"Complete CrewAI Bootcamp"</span>
                <span className="text-xl font-bold text-red-400">$499</span>
              </div>
            </div>

            {/* The Formula - Simple and Clear */}
            <div className="bg-purple-900/10 border border-purple-600/20 rounded-xl p-8 text-center">
              <h3 className="text-lg text-purple-400 mb-4">{t.secretFormula}</h3>
              <p className="text-3xl md:text-4xl font-bold text-white mb-4">
                {t.formula}
              </p>
              <p className="text-gray-400">
                {t.entireCourse}
              </p>
            </div>
          </section>

          {/* Section 2: Why I Built This */}
          <section className="mb-16">
            <h2 className="text-2xl md:text-3xl font-bold text-white mb-6">
              {t.whyBuilt}
            </h2>

            <p className="text-gray-300 mb-6">
              {t.myStory}
            </p>

            <ul className="space-y-3 mb-8">
              <li className="flex items-start gap-3">
                <XCircle className="w-5 h-5 text-red-400 mt-1 flex-shrink-0" />
                <span className="text-gray-300">Simple agent required 100+ lines of code</span>
              </li>
              <li className="flex items-start gap-3">
                <XCircle className="w-5 h-5 text-red-400 mt-1 flex-shrink-0" />
                <span className="text-gray-300">Documentation was incomprehensible</span>
              </li>
              <li className="flex items-start gap-3">
                <XCircle className="w-5 h-5 text-red-400 mt-1 flex-shrink-0" />
                <span className="text-gray-300">Every update broke my code</span>
              </li>
            </ul>
          </section>

          {/* Section 3: Code Comparison - Stacked Vertically */}
          <section className="mb-16">
            <h2 className="text-2xl md:text-3xl font-bold text-white mb-8 text-center">
              {t.seeDifference}
            </h2>

            {/* LangChain Example */}
            <div className="mb-8">
              <h3 className="text-lg font-semibold text-red-400 mb-4 flex items-center gap-2">
                <TrendingDown className="w-5 h-5" />
                {t.langchainTitle}
              </h3>
              <CodeWithResult
                code={langchainCode}
                result="Getting weather for San Francisco...
The weather in San Francisco is sunny, 72°F"
                language="python"
              />
            </div>

            {/* ConnectOnion Example */}
            <div className="mb-8">
              <h3 className="text-lg font-semibold text-green-400 mb-4 flex items-center gap-2">
                <CheckCircle className="w-5 h-5" />
                {t.connectonionTitle}
              </h3>
              <CodeWithResult
                code={connectonionCode}
                result="Getting weather for San Francisco...
The weather in San Francisco is sunny, 72°F"
                language="python"
              />
            </div>

            {/* Comparison Stats */}
            <div className="bg-green-900/10 border border-green-600/20 rounded-lg p-6 text-center">
              <p className="text-xl font-semibold text-green-400">
                {t.sameResult}
              </p>
            </div>
          </section>

          {/* Section 4: Get Started */}
          <section className="mb-16">
            <h2 className="text-2xl md:text-3xl font-bold text-white mb-8">
              {t.getStarted}
            </h2>

            <div className="space-y-6">
              {/* Step 1 */}
              <div>
                <h3 className="text-lg font-semibold text-white mb-3 flex items-center gap-2">
                  <span className="flex items-center justify-center w-7 h-7 bg-purple-600/20 text-purple-400 rounded-full text-sm font-bold">1</span>
                  {t.step1}
                </h3>
                <CommandBlock commands={['pip install connectonion']} />
              </div>

              {/* Step 2 */}
              <div>
                <h3 className="text-lg font-semibold text-white mb-3 flex items-center gap-2">
                  <span className="flex items-center justify-center w-7 h-7 bg-purple-600/20 text-purple-400 rounded-full text-sm font-bold">2</span>
                  {t.step2}
                </h3>
                <CodeWithResult
                  code={`from connectonion import Agent

agent = Agent("assistant")
result = agent.input("What's 2+2?")
print(result)`}
                  result="4"
                  language="python"
                />
              </div>
            </div>
          </section>

          {/* Section 5: What You'll Learn */}
          <section className="mb-16">
            <h2 className="text-2xl md:text-3xl font-bold text-white mb-6">
              {t.whatYouLearn}
            </h2>

            <div className="space-y-3">
              <div className="flex items-start gap-3 p-4 bg-gray-800/30 rounded-lg">
                <CheckCircle className="w-5 h-5 text-green-400 mt-1 flex-shrink-0" />
                <span className="text-gray-300">{t.lesson1}</span>
              </div>
              <div className="flex items-start gap-3 p-4 bg-gray-800/30 rounded-lg">
                <CheckCircle className="w-5 h-5 text-green-400 mt-1 flex-shrink-0" />
                <span className="text-gray-300">{t.lesson2}</span>
              </div>
              <div className="flex items-start gap-3 p-4 bg-gray-800/30 rounded-lg">
                <CheckCircle className="w-5 h-5 text-green-400 mt-1 flex-shrink-0" />
                <span className="text-gray-300">{t.lesson3}</span>
              </div>
            </div>
          </section>

          {/* Call to Action */}
          <section className="mb-16">
            <h2 className="text-2xl md:text-3xl font-bold text-white mb-6 text-center">
              {t.nextSteps}
            </h2>

            <div className="grid md:grid-cols-2 gap-4">
              <Link
                href="/quickstart"
                className="group block p-6 bg-gray-800/50 rounded-lg border border-gray-700 hover:border-purple-500/50 transition-all"
              >
                <h3 className="text-lg font-semibold text-white mb-2 flex items-center gap-2">
                  <Target className="w-5 h-5 text-purple-400" />
                  {t.quickStart}
                </h3>
                <p className="text-gray-400">Build your first intelligent agent</p>
                <div className="mt-4 text-purple-400 flex items-center gap-1">
                  <span className="text-sm">Get started</span>
                  <ChevronRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
                </div>
              </Link>

              <Link
                href="/examples"
                className="group block p-6 bg-gray-800/50 rounded-lg border border-gray-700 hover:border-blue-500/50 transition-all"
              >
                <h3 className="text-lg font-semibold text-white mb-2 flex items-center gap-2">
                  <Code className="w-5 h-5 text-blue-400" />
                  {t.examples}
                </h3>
                <p className="text-gray-400">Real-world applications and patterns</p>
                <div className="mt-4 text-blue-400 flex items-center gap-1">
                  <span className="text-sm">Browse examples</span>
                  <ChevronRight className="w-4 h-4 group-hover:translate-x-1 transition-transform" />
                </div>
              </Link>
            </div>
          </section>
        </article>

        {/* Bottom Navigation */}
        <ContentNavigation />
      </div>
    </div>
  )
}