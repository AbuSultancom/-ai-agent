class PlannerAgent:
    """
    A class to define a planner agent that decomposes tasks into smaller manageable steps.
    """

    def __init__(self, task):
        self.task = task

    def decompose(self):
        """
        Decomposes the main task into smaller steps.
        """
        # This is a placeholder implementation.
        steps = self.task.split(' ')
        return steps

    def execute(self):
        """
        Execute the steps generated from decomposition.
        """
        steps = self.decompose()
        for step in steps:
            print(f'Executing step: {step}')