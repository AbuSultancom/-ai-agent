"""
Main entry point for the AI Agent.

Run modes:
  python orchestrator.py serve          — start Flask API server
  python orchestrator.py run "task..."  — execute a single task from CLI
  python orchestrator.py plan "task..."  — show planning steps only
"""

import argparse
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def cmd_serve() -> None:
    from core.app import app
    from core.config import config
    logger.info("Starting AI Agent API on %s:%s", config.HOST, config.PORT)
    app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG)


def cmd_run(task: str) -> None:
    from core.orchestrator import AIOrchestrator
    orchestrator = AIOrchestrator()
    print(f"\n{'='*60}")
    print(f"Task: {task}")
    print("=" * 60)
    for chunk in orchestrator.run_task(task):
        print(chunk, end="", flush=True)
    print("\n" + "=" * 60)


def cmd_plan(task: str) -> None:
    from agents.planner_agent import PlannerAgent
    planner = PlannerAgent()
    print(planner.format_plan(task))


def main() -> None:
    parser = argparse.ArgumentParser(description="AI Agent")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("serve", help="Start Flask API server")

    run_p = subparsers.add_parser("run", help="Run a task directly")
    run_p.add_argument("task", nargs="+", help="Task description")

    plan_p = subparsers.add_parser("plan", help="Show task plan without executing")
    plan_p.add_argument("task", nargs="+", help="Task description")

    args = parser.parse_args()

    if args.command == "serve" or args.command is None:
        cmd_serve()
    elif args.command == "run":
        cmd_run(" ".join(args.task))
    elif args.command == "plan":
        cmd_plan(" ".join(args.task))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
