'use client'

import { useState, useEffect } from 'react'
import { CommandBlock } from '../../../components/CommandBlock'
import { CodeWithResult } from '../../../components/CodeWithResult'
import { PageCopyButton } from '../../../components/PageCopyButton'
import {
  Globe, Zap, Code, BookOpen, TrendingUp, Users, Star,
  ArrowRight, Sparkles, CheckCircle, XCircle, AlertTriangle,
  Timer, DollarSign, Rocket, Award, Target, ChevronRight
} from 'lucide-react'

const translations = {
  en: {
    formula: 'AI Agent = Prompt + Function',
    subtitle: 'Read time: 1 minute. Build your first AI Agent: 30 seconds.',
    truth: 'The Truth About Those $199 Courses',
    selling: 'People are selling courses right now:',
    dontWant: 'Here\'s what they don\'t want you to know:',
    entireCourse: 'That\'s it. That\'s the entire course.',
    whyBuilt: 'Why I Built ConnectOnion',
    disgusted: 'I was building a project with LangChain and got disgusted:',
    required100: 'Simple agent required 100+ lines of code',
    abstractions: 'Too many unnecessary abstractions',
    couldntExplain: 'Couldn\'t explain it even to experienced developers',
    seeDifference: 'See the Difference',
    started30Seconds: 'Get Started in 30 Seconds',
    thatsIt: 'That\'s It!',
    noComplexSetup: 'No complex setup',
    noConfusingAbstractions: 'No confusing abstractions',
    justWrite: 'Just write code',
    nextSteps: 'Ready to Build?',
    quickStart: 'Quick Start Guide',
    buildFirst: 'Build your first intelligent agent',
    examples: 'Browse Examples',
    realWorld: 'Real-world applications and patterns'
  },
  zh: {
    formula: 'AI Agent = 提示词 + 函数',
    subtitle: '阅读时间：1分钟。构建你的第一个AI Agent：30秒。',
    truth: '那些199美元课程的真相',
    selling: '现在有人在卖这些课程：',
    dontWant: '他们不想让你知道的秘密：',
    entireCourse: '就这样。整个课程就这些。',
    whyBuilt: '我为什么要做ConnectOnion',
    disgusted: '我用LangChain做项目时感到恶心：',
    required100: '简单的Agent需要100多行代码',
    abstractions: '太多不必要的抽象',
    couldntExplain: '连资深开发者都解释不清',
    seeDifference: '看看区别',
    started30Seconds: '30秒快速开始',
    thatsIt: '就是这么简单！',
    noComplexSetup: '无需复杂设置',
    noConfusingAbstractions: '没有混乱的抽象',
    justWrite: '直接写代码',
    nextSteps: '准备开始了？',
    quickStart: '快速入门指南',
    buildFirst: '构建你的第一个智能代理',
    examples: '浏览示例',
    realWorld: '真实世界的应用和模式'
  },
  ja: {
    formula: 'AIエージェント = プロンプト + 関数',
    subtitle: '読了時間：1分。初めてのAIエージェント構築：30秒。',
    truth: '$199コースの真実',
    selling: '今、こんなコースが売られています：',
    dontWant: '彼らが教えたくない秘密：',
    entireCourse: 'これだけ。コース全体がこれだけです。',
    whyBuilt: 'なぜConnectOnionを作ったか',
    disgusted: 'LangChainでプロジェクトを作っていて嫌気がさしました：',
    required100: 'シンプルなエージェントに100行以上のコードが必要',
    abstractions: '不要な抽象化が多すぎる',
    couldntExplain: '経験豊富な開発者にも説明できない',
    seeDifference: '違いを見てください',
    started30Seconds: '30秒で始める',
    thatsIt: 'これだけです！',
    noComplexSetup: '複雑な設定不要',
    noConfusingAbstractions: '混乱する抽象化なし',
    justWrite: 'コードを書くだけ',
    nextSteps: '始める準備はできましたか？',
    quickStart: 'クイックスタートガイド',
    buildFirst: '最初のインテリジェントエージェントを構築',
    examples: '例を見る',
    realWorld: '実世界のアプリケーションとパターン'
  }
}

// Impressive code samples
const langchainCode = `from langchain.agents import Tool, AgentExecutor, LLMSingleActionAgent
from langchain.prompts import StringPromptTemplate
from langchain.chains import LLMChain
from langchain.schema import AgentAction, AgentFinish, OutputParserException
from langchain.chat_models import ChatOpenAI
from typing import List, Union
import re

# Define the tool
def get_weather(city: str) -> str:
    return f"The weather in {city} is sunny, 72°F"

weather_tool = Tool(
    name="Weather",
    func=get_weather,
    description="Get weather for a city"
)

tools = [weather_tool]

# Set up the prompt template
template = """You are a weather assistant.

You have access to the following tools:

{tools}

Use the following format:

Question: the input question you must answer
Thought: you should always think about what to do
Action: the action to take, should be one of [{tool_names}]
Action Input: the input to the action
Observation: the result of the action
... (this Thought/Action/Action Input/Observation can repeat N times)
Thought: I now know the final answer
Final Answer: the final answer to the original input question

Question: {input}
{agent_scratchpad}"""

class CustomPromptTemplate(StringPromptTemplate):
    template: str
    tools: List[Tool]

    def format(self, **kwargs) -> str:
        intermediate_steps = kwargs.pop("intermediate_steps")
        thoughts = ""
        for action, observation in intermediate_steps:
            thoughts += action.log
            thoughts += f"\\nObservation: {observation}\\nThought: "
        kwargs["agent_scratchpad"] = thoughts
        kwargs["tools"] = "\\n".join([f"{tool.name}: {tool.description}" for tool in self.tools])
        kwargs["tool_names"] = ", ".join([tool.name for tool in self.tools])
        return self.template.format(**kwargs)

prompt = CustomPromptTemplate(
    template=template,
    tools=tools,
    input_variables=["input", "intermediate_steps"]
)

# Output parser
class CustomOutputParser:
    def parse(self, llm_output: str) -> Union[AgentAction, AgentFinish]:
        if "Final Answer:" in llm_output:
            return AgentFinish(
                return_values={"output": llm_output.split("Final Answer:")[-1].strip()},
                log=llm_output,
            )
        # Parse out the action and action input
        regex = r"Action\\s*\\d*\\s*:(.*?)\\nAction\\s*\\d*\\s*Input\\s*\\d*\\s*:[\\s]*(.*)"
        match = re.search(regex, llm_output, re.DOTALL)
        if not match:
            raise OutputParserException(f"Could not parse LLM output: \`{llm_output}\`")
        action = match.group(1).strip()
        action_input = match.group(2)
        return AgentAction(tool=action, tool_input=action_input.strip(" ").strip('"'), log=llm_output)

# Create everything
llm = ChatOpenAI(temperature=0)
llm_chain = LLMChain(llm=llm, prompt=prompt)
tool_names = [tool.name for tool in tools]
agent = LLMSingleActionAgent(
    llm_chain=llm_chain,
    output_parser=CustomOutputParser(),
    stop=["\\nObservation:"],
    allowed_tools=tool_names
)
agent_executor = AgentExecutor.from_agent_and_tools(agent=agent, tools=tools, verbose=True)

# Finally use it (after 67 lines)
result = agent_executor.run("What's the weather in San Francisco?")`

const connectonionCode = `from connectonion import Agent

def get_weather(city: str) -> str:
    return f"The weather in {city} is sunny, 72°F"

agent = Agent("weather_bot", tools=[get_weather])
result = agent.input("What's the weather in San Francisco?")`

export default function Tutorial001Page() {
  const [language, setLanguage] = useState<'en' | 'zh' | 'ja'>('en')
  const [isVisible, setIsVisible] = useState(false)
  const [codeHovered, setCodeHovered] = useState<'langchain' | 'connectonion' | null>(null)
  const t = translations[language]

  useEffect(() => {
    setIsVisible(true)
  }, [])

  return (
    <div className="max-w-5xl mx-auto p-4 sm:p-6 lg:p-8">
      <style jsx global>{`
        @keyframes gradient {
          0% { background-position: 0% 50%; }
          50% { background-position: 100% 50%; }
          100% { background-position: 0% 50%; }
        }
        .animate-gradient {
          background-size: 200% 200%;
          animation: gradient 3s ease infinite;
        }
        @keyframes pulse-glow {
          0%, 100% { opacity: 0.5; }
          50% { opacity: 1; }
        }
        .pulse-glow {
          animation: pulse-glow 2s ease-in-out infinite;
        }
      `}</style>

      {/* Hero Header */}
      <div className={`mb-16 transition-all duration-1000 ${isVisible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-8'}`}>
        <div className="flex items-center justify-between mb-8">
          <div className="inline-flex items-center gap-2 px-5 py-2.5 bg-gradient-to-r from-purple-600/25 to-pink-600/25 rounded-full border border-purple-500/40 backdrop-blur-sm">
            <Sparkles className="w-5 h-5 text-purple-300 animate-pulse" />
            <span className="text-purple-200 font-medium">Tutorial 001</span>
            <div className="flex items-center gap-1 ml-2">
              {[...Array(5)].map((_, i) => (
                <Star key={i} className="w-3 h-3 fill-yellow-500 text-yellow-500" />
              ))}
            </div>
          </div>

          <div className="flex items-center gap-3">
            {/* Language Switcher - More Premium Design */}
            <div className="p-1 bg-gray-800/60 backdrop-blur-sm rounded-2xl border border-gray-700/50">
              {(['en', 'zh', 'ja'] as const).map((lang) => (
                <button
                  key={lang}
                  onClick={() => setLanguage(lang)}
                  className={`px-5 py-2 rounded-xl text-sm font-medium transition-all duration-300 ${
                    language === lang
                      ? 'bg-gradient-to-r from-purple-600 to-pink-600 text-white shadow-lg shadow-purple-600/25'
                      : 'text-gray-400 hover:text-white hover:bg-gray-700/50'
                  }`}
                >
                  {lang === 'en' ? 'English' : lang === 'zh' ? '中文' : '日本語'}
                </button>
              ))}
            </div>
            <PageCopyButton />
          </div>
        </div>

        {/* Animated Title */}
        <h1 className="text-5xl sm:text-6xl lg:text-7xl font-bold mb-6">
          <span className="bg-gradient-to-r from-purple-300 via-pink-300 to-purple-300 text-transparent bg-clip-text animate-gradient">
            {t.formula}
          </span>
        </h1>

        <div className="flex items-center gap-6 text-gray-400">
          <div className="flex items-center gap-2">
            <Timer className="w-5 h-5" />
            <span>{t.subtitle}</span>
          </div>
          <div className="flex items-center gap-2">
            <Users className="w-5 h-5" />
            <span>10K+ developers</span>
          </div>
        </div>
      </div>

      {/* The Truth Section - Card Style */}
      <section className={`mb-20 transition-all duration-1000 delay-200 ${isVisible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-8'}`}>
        <div className="relative">
          <div className="absolute -left-8 top-0 w-1.5 h-full bg-gradient-to-b from-red-500 via-orange-500 to-yellow-500 rounded-full" />

          <h2 className="text-4xl sm:text-5xl font-bold mb-10 flex items-center gap-4">
            <div className="p-3 bg-red-500/10 rounded-2xl border border-red-500/30">
              <AlertTriangle className="w-8 h-8 text-red-400" />
            </div>
            <span className="bg-gradient-to-r from-red-400 to-orange-400 text-transparent bg-clip-text">
              {t.truth}
            </span>
          </h2>
        </div>

        <p className="text-xl text-gray-300 mb-8">{t.selling}</p>

        {/* Course Cards with Hover Effects */}
        <div className="grid gap-5 mb-10">
          {[
            { name: '"Master LangChain in 30 Days!"', price: '$199', rating: 2.8, students: '12K', color: 'red' },
            { name: '"AutoGen Expert Certification"', price: '$299', rating: 2.5, students: '8K', color: 'orange' },
            { name: '"Complete CrewAI Bootcamp"', price: '$499', rating: 2.2, students: '3K', color: 'yellow' }
          ].map((course, i) => (
            <div
              key={i}
              className="group relative overflow-hidden bg-gradient-to-r from-gray-800/70 to-gray-800/30 rounded-2xl p-6 border border-gray-700 hover:border-red-500/40 transition-all duration-500 hover:scale-[1.02] hover:shadow-xl hover:shadow-red-500/10"
            >
              <div className="absolute top-0 right-0 w-40 h-40 bg-gradient-to-br from-red-600/10 to-orange-600/10 rounded-full blur-3xl group-hover:scale-150 transition-transform duration-700" />

              <div className="relative flex items-center justify-between">
                <div>
                  <h3 className="text-xl font-semibold text-gray-200 mb-3">{course.name}</h3>
                  <div className="flex items-center gap-6 text-sm">
                    <div className="flex items-center gap-2 text-gray-500">
                      <Users className="w-4 h-4" />
                      <span>{course.students} enrolled</span>
                    </div>
                    <div className="flex items-center gap-1">
                      {[...Array(5)].map((_, j) => (
                        <Star
                          key={j}
                          className={`w-4 h-4 ${j < Math.floor(course.rating) ? 'fill-yellow-500 text-yellow-500' : 'text-gray-600'}`}
                        />
                      ))}
                      <span className="text-gray-500 ml-1">{course.rating}</span>
                    </div>
                  </div>
                </div>
                <div className="text-3xl font-bold bg-gradient-to-r from-red-400 to-orange-400 text-transparent bg-clip-text">
                  {course.price}
                </div>
              </div>
            </div>
          ))}
        </div>

        {/* Warning Box */}
        <div className="relative overflow-hidden bg-gradient-to-r from-orange-900/30 to-red-900/30 rounded-2xl p-8 border border-orange-500/40">
          <div className="absolute inset-0 bg-gradient-to-r from-orange-600/5 to-red-600/5 pulse-glow" />
          <p className="relative text-xl font-semibold text-orange-200 flex items-center gap-3">
            <AlertTriangle className="w-6 h-6 animate-pulse" />
            {t.dontWant}
          </p>
        </div>
      </section>

      {/* The Formula - Hero Style */}
      <section className={`mb-20 transition-all duration-1000 delay-400 ${isVisible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-8'}`}>
        <div className="relative">
          <div className="absolute inset-0 bg-gradient-to-r from-purple-600/20 via-pink-600/20 to-purple-600/20 blur-3xl pulse-glow" />

          <div className="relative bg-gradient-to-r from-purple-900/50 to-pink-900/50 rounded-3xl p-12 border border-purple-500/50 backdrop-blur-xl">
            <div className="flex items-center justify-center mb-8 gap-6">
              <div className="p-4 bg-purple-600/20 rounded-2xl border border-purple-500/50 backdrop-blur-sm">
                <Zap className="w-12 h-12 text-purple-300" />
              </div>
              <span className="text-5xl font-bold text-gray-300">+</span>
              <div className="p-4 bg-pink-600/20 rounded-2xl border border-pink-500/50 backdrop-blur-sm">
                <Code className="w-12 h-12 text-pink-300" />
              </div>
            </div>

            <h3 className="text-4xl sm:text-5xl lg:text-6xl font-bold text-center mb-6">
              <span className="bg-gradient-to-r from-purple-300 via-pink-300 to-purple-300 text-transparent bg-clip-text animate-gradient">
                {t.formula}
              </span>
            </h3>

            <div className="flex items-center justify-center gap-3">
              <CheckCircle className="w-6 h-6 text-green-400" />
              <span className="text-xl text-purple-200 font-medium">{t.entireCourse}</span>
            </div>
          </div>
        </div>
      </section>

      {/* Why I Built This - Story Card */}
      <section className={`mb-20 transition-all duration-1000 delay-600 ${isVisible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-8'}`}>
        <div className="relative">
          <div className="absolute -left-8 top-0 w-1.5 h-full bg-gradient-to-b from-purple-500 to-blue-500 rounded-full" />

          <h2 className="text-4xl sm:text-5xl font-bold mb-3">
            <span className="bg-gradient-to-r from-purple-400 to-blue-400 text-transparent bg-clip-text">
              {t.whyBuilt}
            </span>
          </h2>
          <p className="text-gray-500 mb-10 text-lg">A developer's frustration turned into a solution</p>
        </div>

        <div className="bg-gray-800/40 rounded-2xl p-8 mb-10 border border-gray-700/50 backdrop-blur-sm">
          <p className="text-xl text-gray-300 leading-relaxed">{t.disgusted}</p>
        </div>

        <div className="grid gap-4">
          {[
            { icon: XCircle, text: t.required100, color: 'from-red-500 to-orange-500' },
            { icon: XCircle, text: t.abstractions, color: 'from-orange-500 to-yellow-500' },
            { icon: XCircle, text: t.couldntExplain, color: 'from-yellow-500 to-green-500' }
          ].map((item, i) => (
            <div
              key={i}
              className="group flex items-center gap-5 p-5 rounded-xl hover:bg-gray-800/30 transition-all duration-300"
            >
              <div className={`p-3 rounded-xl bg-gradient-to-r ${item.color} opacity-10 group-hover:opacity-20 transition-opacity`}>
                <item.icon className="w-6 h-6 text-red-400" />
              </div>
              <span className="text-lg text-gray-300">{item.text}</span>
            </div>
          ))}
        </div>
      </section>

      {/* Code Comparison - Side by Side */}
      <section className={`mb-20 transition-all duration-1000 delay-800 ${isVisible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-8'}`}>
        <div className="text-center mb-12">
          <h2 className="text-4xl sm:text-5xl font-bold mb-4">
            <span className="bg-gradient-to-r from-green-400 to-blue-400 text-transparent bg-clip-text">
              {t.seeDifference}
            </span>
          </h2>
          <p className="text-xl text-gray-400">Same result, different philosophy</p>
        </div>

        <div className="grid lg:grid-cols-2 gap-8">
          {/* LangChain Card */}
          <div
            className="relative group"
            onMouseEnter={() => setCodeHovered('langchain')}
            onMouseLeave={() => setCodeHovered(null)}
          >
            <div className={`absolute -inset-1 bg-gradient-to-r from-red-600 to-orange-600 rounded-2xl blur-lg opacity-20 transition-opacity duration-500 ${codeHovered === 'langchain' ? 'opacity-40' : ''}`} />

            <div className="relative bg-gray-900/90 rounded-2xl overflow-hidden border border-gray-700">
              <div className="p-6 bg-gradient-to-r from-red-900/30 to-orange-900/30 border-b border-gray-700">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <h3 className="text-2xl font-bold text-red-400">LangChain</h3>
                    <span className="px-3 py-1 bg-red-500/20 text-red-300 text-sm rounded-full border border-red-500/30">
                      67 lines
                    </span>
                  </div>
                  <div className="flex items-center gap-2 text-red-400">
                    <TrendingUp className="w-5 h-5" />
                    <span className="text-sm">Complex</span>
                  </div>
                </div>
              </div>

              <div className="p-6">
                <CodeWithResult
                  code={langchainCode}
                  result="Getting weather for San Francisco...
The weather in San Francisco is sunny, 72°F"
                  language="python"
                />
              </div>
            </div>
          </div>

          {/* ConnectOnion Card */}
          <div
            className="relative group"
            onMouseEnter={() => setCodeHovered('connectonion')}
            onMouseLeave={() => setCodeHovered(null)}
          >
            <div className={`absolute -inset-1 bg-gradient-to-r from-green-600 to-emerald-600 rounded-2xl blur-lg opacity-20 transition-opacity duration-500 ${codeHovered === 'connectonion' ? 'opacity-40' : ''}`} />

            <div className="relative bg-gray-900/90 rounded-2xl overflow-hidden border border-gray-700">
              <div className="p-6 bg-gradient-to-r from-green-900/30 to-emerald-900/30 border-b border-gray-700">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <h3 className="text-2xl font-bold text-green-400">ConnectOnion</h3>
                    <span className="px-3 py-1 bg-green-500/20 text-green-300 text-sm rounded-full border border-green-500/30">
                      5 lines
                    </span>
                  </div>
                  <div className="flex items-center gap-2 text-green-400">
                    <Sparkles className="w-5 h-5" />
                    <span className="text-sm">Simple</span>
                  </div>
                </div>
              </div>

              <div className="p-6">
                <CodeWithResult
                  code={connectonionCode}
                  result="Getting weather for San Francisco...
The weather in San Francisco is sunny, 72°F"
                  language="python"
                />
              </div>
            </div>
          </div>
        </div>

        {/* Stats Comparison */}
        <div className="mt-12 grid grid-cols-3 gap-6">
          <div className="text-center p-6 bg-gradient-to-br from-purple-900/20 to-purple-800/10 rounded-2xl border border-purple-500/30">
            <div className="text-5xl font-bold bg-gradient-to-r from-purple-400 to-pink-400 text-transparent bg-clip-text mb-2">
              93%
            </div>
            <div className="text-gray-400">Less Code</div>
          </div>
          <div className="text-center p-6 bg-gradient-to-br from-green-900/20 to-green-800/10 rounded-2xl border border-green-500/30">
            <div className="text-5xl font-bold bg-gradient-to-r from-green-400 to-emerald-400 text-transparent bg-clip-text mb-2">
              10x
            </div>
            <div className="text-gray-400">Faster Setup</div>
          </div>
          <div className="text-center p-6 bg-gradient-to-br from-blue-900/20 to-blue-800/10 rounded-2xl border border-blue-500/30">
            <div className="text-5xl font-bold bg-gradient-to-r from-blue-400 to-cyan-400 text-transparent bg-clip-text mb-2">
              0
            </div>
            <div className="text-gray-400">Abstractions</div>
          </div>
        </div>
      </section>

      {/* Getting Started - CTA Section */}
      <section className={`mb-20 transition-all duration-1000 delay-1000 ${isVisible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-8'}`}>
        <div className="relative overflow-hidden bg-gradient-to-r from-purple-900/30 to-blue-900/30 rounded-3xl p-10 border border-purple-500/40">
          <div className="absolute inset-0 bg-gradient-to-br from-purple-600/10 to-blue-600/10 pulse-glow" />

          <div className="relative text-center mb-10">
            <h2 className="text-4xl sm:text-5xl font-bold mb-4">
              <span className="bg-gradient-to-r from-purple-400 to-blue-400 text-transparent bg-clip-text">
                {t.started30Seconds}
              </span>
            </h2>
            <p className="text-xl text-gray-400">No configuration. No boilerplate. Just code.</p>
          </div>

          <div className="relative space-y-8">
            {/* Step 1 */}
            <div className="flex items-start gap-4">
              <div className="flex-shrink-0 w-12 h-12 bg-gradient-to-r from-purple-600 to-pink-600 rounded-full flex items-center justify-center text-white font-bold text-lg">
                1
              </div>
              <div className="flex-1">
                <p className="text-gray-400 mb-3">Install the package</p>
                <CommandBlock commands={['pip install connectonion']} />
              </div>
            </div>

            {/* Step 2 */}
            <div className="flex items-start gap-4">
              <div className="flex-shrink-0 w-12 h-12 bg-gradient-to-r from-purple-600 to-pink-600 rounded-full flex items-center justify-center text-white font-bold text-lg">
                2
              </div>
              <div className="flex-1">
                <p className="text-gray-400 mb-3">Write your first agent</p>
                <CodeWithResult
                  code={`from connectonion import Agent

agent = Agent("My Assistant")
result = agent.input("What's 2+2?")
print(result)  # 4`}
                  result="4"
                  language="python"
                />
              </div>
            </div>
          </div>

          <div className="relative mt-10 flex justify-center">
            <button className="group flex items-center gap-3 px-8 py-4 bg-gradient-to-r from-purple-600 to-pink-600 text-white font-semibold text-lg rounded-2xl hover:shadow-2xl hover:shadow-purple-600/30 hover:scale-105 transition-all duration-300">
              <Rocket className="w-6 h-6" />
              <span>Start Building Now</span>
              <ArrowRight className="w-6 h-6 group-hover:translate-x-2 transition-transform" />
            </button>
          </div>
        </div>
      </section>

      {/* Success Message */}
      <section className={`mb-20 transition-all duration-1000 delay-1200 ${isVisible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-8'}`}>
        <div className="relative">
          <div className="absolute inset-0 bg-gradient-to-r from-green-600/10 to-emerald-600/10 blur-3xl" />

          <div className="relative bg-gradient-to-r from-green-900/40 to-emerald-900/40 rounded-3xl p-10 border border-green-500/50">
            <div className="flex justify-center mb-8">
              <div className="p-5 bg-green-600/20 rounded-full border border-green-500/50">
                <CheckCircle className="w-16 h-16 text-green-400" />
              </div>
            </div>

            <h3 className="text-3xl sm:text-4xl font-bold text-center mb-8 text-white">
              {t.thatsIt}
            </h3>

            <div className="grid sm:grid-cols-3 gap-6">
              {[
                { icon: '🚀', text: t.noComplexSetup },
                { icon: '✨', text: t.noConfusingAbstractions },
                { icon: '💡', text: t.justWrite }
              ].map((item, i) => (
                <div key={i} className="text-center p-6 bg-gray-800/40 rounded-2xl border border-gray-700/50 backdrop-blur-sm">
                  <div className="text-4xl mb-3">{item.icon}</div>
                  <p className="text-gray-300">{item.text}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* Next Steps - Premium Cards */}
      <section className={`transition-all duration-1000 delay-1400 ${isVisible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-8'}`}>
        <h2 className="text-4xl font-bold text-center mb-12">
          <span className="bg-gradient-to-r from-blue-400 to-purple-400 text-transparent bg-clip-text">
            {t.nextSteps}
          </span>
        </h2>

        <div className="grid sm:grid-cols-2 gap-8">
          <a
            href="/quickstart"
            className="group relative overflow-hidden block p-8 bg-gradient-to-br from-gray-800/60 to-gray-800/30 rounded-2xl border border-gray-700 hover:border-purple-500/50 transition-all duration-500 hover:scale-[1.02] hover:shadow-2xl hover:shadow-purple-600/20"
          >
            <div className="absolute top-0 right-0 w-32 h-32 bg-purple-600/20 rounded-full blur-3xl group-hover:scale-150 transition-transform duration-700" />

            <div className="relative">
              <div className="flex items-center gap-4 mb-4">
                <div className="p-3 bg-purple-600/20 rounded-xl border border-purple-500/40">
                  <Target className="w-7 h-7 text-purple-400" />
                </div>
                <h3 className="text-2xl font-bold text-white">{t.quickStart}</h3>
              </div>
              <p className="text-gray-400 mb-4">{t.buildFirst}</p>
              <div className="flex items-center gap-2 text-purple-400">
                <span>Get started</span>
                <ChevronRight className="w-5 h-5 group-hover:translate-x-2 transition-transform" />
              </div>
            </div>
          </a>

          <a
            href="/examples"
            className="group relative overflow-hidden block p-8 bg-gradient-to-br from-gray-800/60 to-gray-800/30 rounded-2xl border border-gray-700 hover:border-blue-500/50 transition-all duration-500 hover:scale-[1.02] hover:shadow-2xl hover:shadow-blue-600/20"
          >
            <div className="absolute top-0 right-0 w-32 h-32 bg-blue-600/20 rounded-full blur-3xl group-hover:scale-150 transition-transform duration-700" />

            <div className="relative">
              <div className="flex items-center gap-4 mb-4">
                <div className="p-3 bg-blue-600/20 rounded-xl border border-blue-500/40">
                  <BookOpen className="w-7 h-7 text-blue-400" />
                </div>
                <h3 className="text-2xl font-bold text-white">{t.examples}</h3>
              </div>
              <p className="text-gray-400 mb-4">{t.realWorld}</p>
              <div className="flex items-center gap-2 text-blue-400">
                <span>Browse examples</span>
                <ChevronRight className="w-5 h-5 group-hover:translate-x-2 transition-transform" />
              </div>
            </div>
          </a>
        </div>
      </section>
    </div>
  )
}