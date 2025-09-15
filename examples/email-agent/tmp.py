from connectonion import Agent
# 1. Write a function - You already know how (10 seconds)

# Pure python function
def get_weather(city: str) -> str:
    return f"Sunny in {city}, 22°C"



# system_prompt to guide how agent use the functions :
agent = Agent(system_prompt="you are a weather bot, pls answer weather questions", tools=[get_weather])




# 2. Create agent - Just prompt + function 


# 3. Use it 
print(agent.input("What's 42 times 17?"))