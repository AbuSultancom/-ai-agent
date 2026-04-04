class OSTools:
    def execute_bash(self, command: str) -> str:
        """Executes a bash command and returns the output."""
        import subprocess
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        return result.stdout if result.returncode == 0 else result.stderr

    def get_system_info(self) -> dict:
        """Returns system information such as OS name, version, and architecture."""
        import platform
        return {
            "OS": platform.system(),
            "Version": platform.version(),
            "Architecture": platform.architecture()
        }