# Tutorial 001: AI Agent = Prompt + Function

**Read time: 1 minute. Build your first AI Agent: 30 seconds.**

## The Truth About Those $199 Courses

People are selling courses right now:
- **"Master LangChain in 30 Days!"** - $199
- **"AutoGen Expert Certification"** - $299
- **"Complete CrewAI Bootcamp"** - $499

Here's what they don't want you to know:

**AI Agent = Prompt + Function**

That's it. That's the entire course.

## Why I Built ConnectOnion

I was building a project with LangChain and got disgusted:
- Simple agent required 100+ lines of code
- Documentation was incomprehensible, too many abstractions
- Debugging made me want to throw my laptop
- Every version update broke my code

**I thought: Why can't this be simple?**

So I built ConnectOnion. One design principle: **Keep simple things simple**.

## See the Difference

**LangChain Weather Agent:** 67 lines of hell
```python
from langchain.agents import Tool, AgentExecutor, LLMSingleActionAgent
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
            thoughts += f"\nObservation: {observation}\nThought: "
        kwargs["agent_scratchpad"] = thoughts
        kwargs["tools"] = "\n".join([f"{tool.name}: {tool.description}" for tool in self.tools])
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
        regex = r"Action\s*\d*\s*:(.*?)\nAction\s*\d*\s*Input\s*\d*\s*:[\s]*(.*)"
        match = re.search(regex, llm_output, re.DOTALL)
        if not match:
            raise OutputParserException(f"Could not parse LLM output: `{llm_output}`")
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
    stop=["\nObservation:"],
    allowed_tools=tool_names
)

# Create the executor
agent_executor = AgentExecutor.from_agent_and_tools(agent=agent, tools=tools, verbose=True)

# Use it (after 67 lines of setup)
agent_executor.run("What's the weather in Tokyo?")
```

**My ConnectOnion:** 5 lines
```python
from connectonion import Agent

def get_weather(city: str) -> str:
    return f"Sunny in {city}, 22°C"

agent = Agent("weather_bot", tools=[get_weather])
agent.input("What's the weather in Tokyo?")
```

**Same result. 92% less code.**

## How I Did It

Simple. I found the essence:
- **LangChain**: Makes simple problems complex to look professional
- **My insight**: AI Agent is just ChatGPT that can call functions

So ConnectOnion's core is:
1. You write functions (define capabilities)
2. You write prompts (define behavior)
3. Framework combines them (I already built this part)

## 30 Seconds with My Framework

```python
from connectonion import Agent

# 1. Write a function - You already know how (10 seconds)
def calculate(expression: str) -> str:
    """Calculate math expression"""
    return str(eval(expression))

# 2. Create agent - Just prompt + function (10 seconds)
agent = Agent(
    "calculator",
    system_prompt="You're a math tutor, explain your steps",
    tools=[calculate]
)

# 3. Use it (10 seconds)
print(agent.input("What's 42 times 17?"))
# Output: 42 times 17 equals 714. Here's how: 40×17=680, 2×17=34, 680+34=714
```

**Done. This is the simplicity I wanted.**

## Why Other Frameworks Are Garbage

I've tried them all:

**LangChain:**
- Too many abstraction layers, like Russian dolls
- Breaking changes every update
- Debugging? Good luck
- **My verdict:** Textbook overengineering

**AutoGen:**
- Forces you to learn Actor patterns
- Message passing will make you dizzy
- **My verdict:** Microsoft-style complexity for no reason

**My ConnectOnion:**
- No unnecessary abstractions
- Functions are functions, prompts are prompts
- Something wrong? Just print and debug
- **Design philosophy:** If it needs documentation to explain, the design is wrong

## Real Feedback

What users are saying:
- "Finally someone built a sane framework"
- "Migrated from LangChain, 90% less code"
- "This is what AI Agents should be"

## Why I Made It Free and Open Source

Because I'm sick of:
1. Garbage frameworks wasting everyone's time
2. Course sellers scamming people
3. Simple things made complex

**ConnectOnion will always be free, always open source.**

```bash
pip install connectonion
```

## The Formula

**AI Agent = Prompt + Function**

This is the essence I discovered. Now I'm sharing it with you.

---

## Class Dismissed

This tutorial series is over.

**Because there's really nothing to teach.**

ConnectOnion is that simple:
- Can you write functions? Yes
- Can you write prompts? Yes
- Then you already know how to use it

The rest is just creativity.

**Stop paying for garbage courses.**
**Use ConnectOnion. 5 lines of code to change the world.**

**Class dismissed.**

---

**Next**: Want to see what real agents can do? → [002: Real-World Agent Examples](002-make-your-agent-useful.md)