class AIOrchestrator:
    def __init__(self):
        self.agents = []  # List to store registered agents

    def register_agent(self, agent):
        """Register a new agent to the orchestrator."""
        if agent not in self.agents:
            self.agents.append(agent)
            print(f'Agent {agent} registered successfully.')
        else:
            print(f'Agent {agent} is already registered.')

    def execute_task(self, task):
        """Execute a task using registered agents."""
        print(f'Executing task: {task}')
        # Here we would implement the logic to execute the task using agents

    def get_registered_agents(self):
        """Get a list of registered agents."""
        return self.agents
