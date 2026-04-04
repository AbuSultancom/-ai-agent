class ExecutorAgent:
    def __init__(self):
        self.tools = []

    def register_tool(self, tool):
        self.tools.append(tool)

    def execute_steps(self, steps):
        results = []
        for step in steps:
            tool = step['tool']
            params = step['params']
            if tool in self.tools:
                result = tool.execute(**params)
                results.append(result)
            else:
                raise ValueError(f"Tool {tool} not registered.")
        return results
