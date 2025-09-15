'use client'

import { useState } from 'react'
import { CommandBlock } from '../../../components/CommandBlock'
import { PageCopyButton } from '../../../components/PageCopyButton'
import { Globe } from 'lucide-react'

const translations = {
  en: {
    langName: 'English',
    readTime: 'Read time: 1 minute. Build your first AI Agent: 30 seconds.',
    title: 'Tutorial 001: AI Agent = Prompt + Function',
    truthAboutCourses: 'The Truth About Those $199 Courses',
    coursesIntro: 'People are selling courses right now:',
    course1: '"Master LangChain in 30 Days!" - $199',
    course2: '"AutoGen Expert Certification" - $299',
    course3: '"Complete CrewAI Bootcamp" - $499',
    secretReveal: 'Here\'s what they don\'t want you to know:',
    formula: 'AI Agent = Prompt + Function',
    entireCourse: 'That\'s it. That\'s the entire course.',
    whyBuilt: 'Why I Built ConnectOnion',
    langchainPain: 'I was building a project with LangChain and got disgusted:',
    pain1: 'Simple agent required 100+ lines of code',
    pain2: 'Documentation was incomprehensible, too many abstractions',
    pain3: 'Debugging made me want to throw my laptop',
    pain4: 'Every version update broke my code',
    thought: 'I thought: Why can\'t this be simple?',
    builtSolution: 'So I built ConnectOnion. One design principle: Keep simple things simple.',
    seeDifference: 'See the Difference',
    langchainHell: 'LangChain Weather Agent: 67 lines of hell',
    myConnectonion: 'My ConnectOnion: 5 lines',
    sameResult: 'Same result. 92% less code.',
    howDidIt: 'How I Did It',
    foundEssence: 'Simple. I found the essence:',
    langchainMakes: 'LangChain: Makes simple problems complex to look professional',
    myInsight: 'My insight: AI Agent is just ChatGPT that can call functions',
    coreIs: 'So ConnectOnion\'s core is:',
    core1: 'You write functions (define capabilities)',
    core2: 'You write prompts (define behavior)',
    core3: 'Framework combines them (I already built this part)',
    thirtySeconds: '30 Seconds with My Framework',
    done: 'Done. This is the simplicity I wanted.',
    whyGarbage: 'Why Other Frameworks Are Garbage',
    triedAll: 'I\'ve tried them all:',
    langchainIssues: 'LangChain:',
    langchainIssue1: 'Too many abstraction layers, like Russian dolls',
    langchainIssue2: 'Breaking changes every update',
    langchainIssue3: 'Debugging? Good luck',
    langchainVerdict: 'My verdict: Textbook overengineering',
    autogenIssues: 'AutoGen:',
    autogenIssue1: 'Forces you to learn Actor patterns',
    autogenIssue2: 'Message passing will make you dizzy',
    autogenVerdict: 'My verdict: Microsoft-style complexity for no reason',
    myFramework: 'My ConnectOnion:',
    myFeature1: 'No unnecessary abstractions',
    myFeature2: 'Functions are functions, prompts are prompts',
    myFeature3: 'Something wrong? Just print and debug',
    designPhilosophy: 'Design philosophy: If it needs documentation to explain, the design is wrong',
    realFeedback: 'Real Feedback',
    usersSaying: 'What users are saying:',
    feedback1: '"Finally someone built a sane framework"',
    feedback2: '"Migrated from LangChain, 90% less code"',
    feedback3: '"This is what AI Agents should be"',
    whyFree: 'Why I Made It Free and Open Source',
    sickOf: 'Because I\'m sick of:',
    sick1: 'Garbage frameworks wasting everyone\'s time',
    sick2: 'Course sellers scamming people',
    sick3: 'Simple things made complex',
    alwaysFree: 'ConnectOnion will always be free, always open source.',
    theFormula: 'The Formula',
    discovered: 'This is the essence I discovered. Now I\'m sharing it with you.',
    classDismissed: 'Class Dismissed',
    seriesOver: 'This tutorial series is over.',
    nothingToTeach: 'Because there\'s really nothing to teach.',
    soSimple: 'ConnectOnion is that simple:',
    canWrite1: 'Can you write functions? Yes',
    canWrite2: 'Can you write prompts? Yes',
    knowHow: 'Then you already know how to use it',
    restCreativity: 'The rest is just creativity.',
    stopPaying: 'Stop paying for garbage courses.',
    useCO: 'Use ConnectOnion. 5 lines of code to change the world.',
    finalDismissal: 'Class dismissed.'
  },
  zh: {
    langName: '中文',
    readTime: '阅读时间：1分钟。构建你的第一个AI Agent：30秒。',
    title: '教程 001：AI Agent = 提示词 + 函数',
    truthAboutCourses: '那些199美元课程的真相',
    coursesIntro: '现在有人在卖这些课程：',
    course1: '"30天精通LangChain！" - $199',
    course2: '"AutoGen专家认证" - $299',
    course3: '"CrewAI完整训练营" - $499',
    secretReveal: '他们不想让你知道的秘密：',
    formula: 'AI Agent = 提示词 + 函数',
    entireCourse: '就这样。整个课程就这些。',
    whyBuilt: '我为什么要做ConnectOnion',
    langchainPain: '我用LangChain做项目时感到恶心：',
    pain1: '简单的Agent需要100多行代码',
    pain2: '文档看不懂，太多抽象概念',
    pain3: '调试让我想摔电脑',
    pain4: '每次版本更新都会破坏我的代码',
    thought: '我想：为什么不能简单点？',
    builtSolution: '所以我做了ConnectOnion。一个设计原则：让简单的事情保持简单。',
    seeDifference: '看看区别',
    langchainHell: 'LangChain天气Agent：67行地狱',
    myConnectonion: '我的ConnectOnion：5行',
    sameResult: '同样的结果。少92%的代码。',
    howDidIt: '我是怎么做到的',
    foundEssence: '很简单。我找到了本质：',
    langchainMakes: 'LangChain：把简单问题复杂化来显得专业',
    myInsight: '我的洞察：AI Agent就是能调用函数的ChatGPT',
    coreIs: '所以ConnectOnion的核心是：',
    core1: '你写函数（定义能力）',
    core2: '你写提示词（定义行为）',
    core3: '框架把它们结合（这部分我已经做好了）',
    thirtySeconds: '用我的框架30秒搞定',
    done: '完成。这就是我想要的简单。',
    whyGarbage: '为什么其他框架都是垃圾',
    triedAll: '我都试过了：',
    langchainIssues: 'LangChain：',
    langchainIssue1: '太多抽象层，像俄罗斯套娃',
    langchainIssue2: '每次更新都有破坏性改动',
    langchainIssue3: '调试？祝你好运',
    langchainVerdict: '我的评价：教科书式的过度工程',
    autogenIssues: 'AutoGen：',
    autogenIssue1: '强迫你学习Actor模式',
    autogenIssue2: '消息传递会让你头晕',
    autogenVerdict: '我的评价：毫无理由的微软式复杂',
    myFramework: '我的ConnectOnion：',
    myFeature1: '没有不必要的抽象',
    myFeature2: '函数就是函数，提示词就是提示词',
    myFeature3: '出问题了？print调试就行',
    designPhilosophy: '设计哲学：如果需要文档来解释，那设计就是错的',
    realFeedback: '真实反馈',
    usersSaying: '用户在说什么：',
    feedback1: '"终于有人做了个正常的框架"',
    feedback2: '"从LangChain迁移过来，代码少了90%"',
    feedback3: '"AI Agent就该是这样"',
    whyFree: '为什么我要做成免费开源',
    sickOf: '因为我受够了：',
    sick1: '垃圾框架浪费大家时间',
    sick2: '课程贩子骗钱',
    sick3: '简单的事情被搞复杂',
    alwaysFree: 'ConnectOnion永远免费，永远开源。',
    theFormula: '公式',
    discovered: '这是我发现的本质。现在分享给你。',
    classDismissed: '下课',
    seriesOver: '这个教程系列结束了。',
    nothingToTeach: '因为真的没什么可教的。',
    soSimple: 'ConnectOnion就是这么简单：',
    canWrite1: '会写函数吗？会',
    canWrite2: '会写提示词吗？会',
    knowHow: '那你已经会用了',
    restCreativity: '剩下的就是创意。',
    stopPaying: '别再为垃圾课程付钱了。',
    useCO: '用ConnectOnion。5行代码改变世界。',
    finalDismissal: '下课。'
  },
  ja: {
    langName: '日本語',
    readTime: '読了時間：1分。初めてのAIエージェント構築：30秒。',
    title: 'チュートリアル001：AIエージェント = プロンプト + 関数',
    truthAboutCourses: '$199コースの真実',
    coursesIntro: '今、こんなコースが売られています：',
    course1: '"30日でLangChainマスター！" - $199',
    course2: '"AutoGen専門家認定" - $299',
    course3: '"CrewAI完全ブートキャンプ" - $499',
    secretReveal: '彼らが教えたくない秘密：',
    formula: 'AIエージェント = プロンプト + 関数',
    entireCourse: 'これだけ。コース全体がこれだけです。',
    whyBuilt: 'なぜConnectOnionを作ったか',
    langchainPain: 'LangChainでプロジェクトを作っていて嫌気がさしました：',
    pain1: 'シンプルなエージェントに100行以上のコードが必要',
    pain2: 'ドキュメントが理解不能、抽象化が多すぎる',
    pain3: 'デバッグでノートパソコンを投げたくなった',
    pain4: 'バージョン更新のたびにコードが壊れる',
    thought: '思いました：なぜシンプルにできないのか？',
    builtSolution: 'だからConnectOnionを作りました。設計原則は一つ：シンプルなものはシンプルに。',
    seeDifference: '違いを見てください',
    langchainHell: 'LangChain天気エージェント：67行の地獄',
    myConnectonion: '私のConnectOnion：5行',
    sameResult: '同じ結果。92%少ないコード。',
    howDidIt: 'どうやったか',
    foundEssence: 'シンプルです。本質を見つけました：',
    langchainMakes: 'LangChain：プロフェッショナルに見せるために単純な問題を複雑にする',
    myInsight: '私の洞察：AIエージェントは関数を呼び出せるChatGPT',
    coreIs: 'ConnectOnionのコアは：',
    core1: '関数を書く（能力を定義）',
    core2: 'プロンプトを書く（動作を定義）',
    core3: 'フレームワークが組み合わせる（この部分は作りました）',
    thirtySeconds: '私のフレームワークで30秒',
    done: '完了。これが求めていたシンプルさです。',
    whyGarbage: 'なぜ他のフレームワークはゴミなのか',
    triedAll: '全部試しました：',
    langchainIssues: 'LangChain：',
    langchainIssue1: 'ロシアのマトリョーシカのような抽象化レイヤー',
    langchainIssue2: '更新のたびに破壊的変更',
    langchainIssue3: 'デバッグ？幸運を祈る',
    langchainVerdict: '私の評価：教科書的な過剰エンジニアリング',
    autogenIssues: 'AutoGen：',
    autogenIssue1: 'Actorパターンの学習を強制',
    autogenIssue2: 'メッセージパッシングで目が回る',
    autogenVerdict: '私の評価：理由なきマイクロソフト流の複雑さ',
    myFramework: '私のConnectOnion：',
    myFeature1: '不要な抽象化なし',
    myFeature2: '関数は関数、プロンプトはプロンプト',
    myFeature3: '問題が？printでデバッグ',
    designPhilosophy: '設計哲学：説明にドキュメントが必要なら、設計が間違っている',
    realFeedback: '実際のフィードバック',
    usersSaying: 'ユーザーの声：',
    feedback1: '"ついにまともなフレームワークが登場"',
    feedback2: '"LangChainから移行、コード90%削減"',
    feedback3: '"AIエージェントはこうあるべき"',
    whyFree: 'なぜ無料でオープンソースにしたか',
    sickOf: 'うんざりだから：',
    sick1: 'ゴミフレームワークが皆の時間を無駄にする',
    sick2: 'コース販売者が詐欺をする',
    sick3: 'シンプルなことが複雑になる',
    alwaysFree: 'ConnectOnionは永遠に無料、永遠にオープンソース。',
    theFormula: '公式',
    discovered: 'これが発見した本質です。今あなたと共有します。',
    classDismissed: '授業終了',
    seriesOver: 'このチュートリアルシリーズは終わりです。',
    nothingToTeach: '本当に教えることがないから。',
    soSimple: 'ConnectOnionはそれほどシンプル：',
    canWrite1: '関数を書ける？はい',
    canWrite2: 'プロンプトを書ける？はい',
    knowHow: 'ならもう使い方を知っています',
    restCreativity: '残りは創造性だけ。',
    stopPaying: 'ゴミコースにお金を払うのをやめて。',
    useCO: 'ConnectOnionを使おう。5行のコードで世界を変える。',
    finalDismissal: '授業終了。'
  }
}

export default function Tutorial001Page() {
  const [lang, setLang] = useState<'en' | 'zh' | 'ja'>('en')
  const t = translations[lang]

  const pageContent = `# ${t.title}

**${t.readTime}**

## ${t.truthAboutCourses}

${t.coursesIntro}
- **${t.course1}**
- **${t.course2}**
- **${t.course3}**

${t.secretReveal}

**${t.formula}**

${t.entireCourse}

[... rest of content in selected language ...]`

  return (
    <div className="min-h-screen bg-gray-950 text-gray-200">
      <div className="max-w-[52rem] mx-auto px-4 sm:px-6 py-4 sm:py-8 md:py-12">
        {/* Language Switcher */}
        <div className="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-3 mb-6">
          <div className="flex items-center gap-2 text-xs sm:text-sm text-gray-400">
            <Globe className="w-4 h-4" />
            <span>Language:</span>
          </div>
          <div className="flex gap-1 sm:gap-2">
            {(['en', 'zh', 'ja'] as const).map((langCode) => (
              <button
                key={langCode}
                onClick={() => setLang(langCode)}
                className={`px-2 sm:px-3 py-1 rounded-md text-xs sm:text-sm transition-all ${
                  lang === langCode
                    ? 'bg-purple-600 text-white'
                    : 'bg-gray-800 text-gray-300 hover:bg-gray-700'
                }`}
              >
                {translations[langCode].langName}
              </button>
            ))}
          </div>
        </div>

        <div className="prose prose-sm sm:prose-base prose-invert prose-purple max-w-none">
          <PageCopyButton content={pageContent} />

          <h1 className="gradient-text text-2xl sm:text-3xl md:text-4xl lg:text-5xl">{t.title}</h1>

          <p className="text-sm sm:text-base md:text-lg text-gray-300">
            <strong>{t.readTime}</strong>
          </p>

          <h2>{t.truthAboutCourses}</h2>

          <p>{t.coursesIntro}</p>
          <ul>
            <li><strong>{t.course1}</strong></li>
            <li><strong>{t.course2}</strong></li>
            <li><strong>{t.course3}</strong></li>
          </ul>

          <p>{t.secretReveal}</p>

          <p className="text-lg sm:text-xl md:text-2xl font-bold text-purple-400 text-center my-6 sm:my-8 px-2">
            {t.formula}
          </p>

          <p>{t.entireCourse}</p>

          <h2>{t.whyBuilt}</h2>

          <p>{t.langchainPain}</p>
          <ul>
            <li>{t.pain1}</li>
            <li>{t.pain2}</li>
            <li>{t.pain3}</li>
            <li>{t.pain4}</li>
          </ul>

          <p><strong>{t.thought}</strong></p>

          <p>{t.builtSolution}</p>

          <h2>{t.seeDifference}</h2>

          <h3>{t.langchainHell}</h3>

          <pre className="bg-gray-900 border border-gray-800 rounded-lg p-2 sm:p-3 md:p-4 overflow-x-auto text-xs sm:text-sm">
            <code className="text-sm">{`from langchain.agents import Tool, AgentExecutor, LLMSingleActionAgent
from langchain.prompts import StringPromptTemplate
from langchain.chains import LLMChain
from langchain.schema import AgentAction, AgentFinish, OutputParserException
from langchain.chat_models import ChatOpenAI
from typing import List, Union
import re

# Define the tool
def get_weather(city: str) -> str:
    return f"Sunny in {city}, 22°C"

weather_tool = Tool(
    name="Weather",
    func=get_weather,
    description="Get weather for a city"
)

tools = [weather_tool]

# Set up the prompt template (yes, this is required)
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

# Output parser (more boilerplate)
class CustomOutputParser:
    def parse(self, llm_output: str) -> Union[AgentAction, AgentFinish]:
        if "Final Answer:" in llm_output:
            return AgentFinish(
                return_values={"output": llm_output.split("Final Answer:")[-1].strip()},
                log=llm_output,
            )
        regex = r"Action\\s*\\d*\\s*:(.*?)\\nAction\\s*\\d*\\s*Input\\s*\\d*\\s*:[\\s]*(.*)"
        match = re.search(regex, llm_output, re.DOTALL)
        if not match:
            raise OutputParserException(f"Could not parse LLM output: \`{llm_output}\`")
        action = match.group(1).strip()
        action_input = match.group(2)
        return AgentAction(tool=action, tool_input=action_input.strip(" ").strip('"'), log=llm_output)

# Create the LLM chain
llm = ChatOpenAI(temperature=0)
llm_chain = LLMChain(llm=llm, prompt=prompt)

# Create the agent (finally!)
tool_names = [tool.name for tool in tools]
agent = LLMSingleActionAgent(
    llm_chain=llm_chain,
    output_parser=CustomOutputParser(),
    stop=["\\nObservation:"],
    allowed_tools=tool_names
)

# Create the executor
agent_executor = AgentExecutor.from_agent_and_tools(agent=agent, tools=tools, verbose=True)

# Use it (after 67 lines of setup)
agent_executor.run("What's the weather in Tokyo?")`}</code>
          </pre>

          <h3>{t.myConnectonion}</h3>

          <pre className="bg-gray-900 border border-gray-800 rounded-lg p-2 sm:p-3 md:p-4 overflow-x-auto text-xs sm:text-sm">
            <code className="text-sm">{`from connectonion import Agent

def get_weather(city: str) -> str:
    return f"Sunny in {city}, 22°C"

agent = Agent("weather_bot", tools=[get_weather])
agent.input("What's the weather in Tokyo?")`}</code>
          </pre>

          <p className="text-base sm:text-lg md:text-xl font-bold text-center my-4 sm:my-6 md:my-8">{t.sameResult}</p>

          <h2>{t.howDidIt}</h2>

          <p>{t.foundEssence}</p>
          <ul>
            <li><strong>{t.langchainMakes}</strong></li>
            <li><strong>{t.myInsight}</strong></li>
          </ul>

          <p>{t.coreIs}</p>
          <ol>
            <li>{t.core1}</li>
            <li>{t.core2}</li>
            <li>{t.core3}</li>
          </ol>

          <h2>{t.thirtySeconds}</h2>

          <pre className="bg-gray-900 border border-gray-800 rounded-lg p-2 sm:p-3 md:p-4 overflow-x-auto text-xs sm:text-sm">
            <code className="text-sm">{`from connectonion import Agent

# 1. ${lang === 'en' ? 'Write a function - You already know how (10 seconds)' : lang === 'zh' ? '写个函数 - 你已经会了（10秒）' : '関数を書く - もう知っています（10秒）'}
def calculate(expression: str) -> str:
    """${lang === 'en' ? 'Calculate math expression' : lang === 'zh' ? '计算数学表达式' : '数式を計算'}"""
    return str(eval(expression))

# 2. ${lang === 'en' ? 'Create agent - Just prompt + function (10 seconds)' : lang === 'zh' ? '创建Agent - 就是提示词+函数（10秒）' : 'エージェント作成 - プロンプト+関数だけ（10秒）'}
agent = Agent(
    "calculator",
    system_prompt="${lang === 'en' ? "You're a math tutor, explain your steps" : lang === 'zh' ? '你是数学老师，解释你的步骤' : '数学の家庭教師です、手順を説明してください'}",
    tools=[calculate]
)

# 3. ${lang === 'en' ? 'Use it (10 seconds)' : lang === 'zh' ? '使用它（10秒）' : '使う（10秒）'}
print(agent.input("${lang === 'en' ? "What's 42 times 17?" : lang === 'zh' ? '42乘以17等于多少？' : '42×17は？'}"))
# Output: ${lang === 'en' ? '42 times 17 equals 714. Here\'s how: 40×17=680, 2×17=34, 680+34=714' : lang === 'zh' ? '42乘以17等于714。计算方法：40×17=680，2×17=34，680+34=714' : '42×17は714です。計算方法：40×17=680、2×17=34、680+34=714'}`}</code>
          </pre>

          <p><strong>{t.done}</strong></p>

          <h2>{t.whyGarbage}</h2>

          <p>{t.triedAll}</p>

          <p><strong>{t.langchainIssues}</strong></p>
          <ul>
            <li>{t.langchainIssue1}</li>
            <li>{t.langchainIssue2}</li>
            <li>{t.langchainIssue3}</li>
            <li><strong>{t.langchainVerdict}</strong></li>
          </ul>

          <p><strong>{t.autogenIssues}</strong></p>
          <ul>
            <li>{t.autogenIssue1}</li>
            <li>{t.autogenIssue2}</li>
            <li><strong>{t.autogenVerdict}</strong></li>
          </ul>

          <p><strong>{t.myFramework}</strong></p>
          <ul>
            <li>{t.myFeature1}</li>
            <li>{t.myFeature2}</li>
            <li>{t.myFeature3}</li>
            <li><strong>{t.designPhilosophy}</strong></li>
          </ul>

          <h2>{t.realFeedback}</h2>

          <p>{t.usersSaying}</p>
          <ul>
            <li>{t.feedback1}</li>
            <li>{t.feedback2}</li>
            <li>{t.feedback3}</li>
          </ul>

          <h2>{t.whyFree}</h2>

          <p>{t.sickOf}</p>
          <ol>
            <li>{t.sick1}</li>
            <li>{t.sick2}</li>
            <li>{t.sick3}</li>
          </ol>

          <p><strong>{t.alwaysFree}</strong></p>

          <CommandBlock commands={['pip install connectonion']} />

          <h2>{t.theFormula}</h2>

          <p className="text-lg sm:text-xl md:text-2xl font-bold text-purple-400 text-center my-6 sm:my-8 px-2">
            {t.formula}
          </p>

          <p>{t.discovered}</p>

          <hr className="my-12 border-gray-800" />

          <h2>{t.classDismissed}</h2>

          <p>{t.seriesOver}</p>

          <p><strong>{t.nothingToTeach}</strong></p>

          <p>{t.soSimple}</p>
          <ul>
            <li>{t.canWrite1}</li>
            <li>{t.canWrite2}</li>
            <li>{t.knowHow}</li>
          </ul>

          <p>{t.restCreativity}</p>

          <p className="text-base sm:text-lg font-bold px-2">
            {t.stopPaying}<br/>
            {t.useCO}
          </p>

          <p className="text-lg sm:text-xl font-bold text-purple-400 text-center mt-6 sm:mt-8">
            {t.finalDismissal}
          </p>
        </div>
      </div>
    </div>
  )
}