#!/usr/bin/env python3
"""CLI script for running H-ARCANE experiments."""

import asyncio
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from h_arcane.experiments.config import BaselineType, ExperimentConfig
from h_arcane.experiments.runner import ExperimentRunner


def get_project_root() -> Path:
    """Get the project root directory (where docker-compose.yml is)."""
    # This script is in scripts/, so go up one level
    script_dir = Path(__file__).parent
    return script_dir.parent


def get_docker_compose_cmd() -> list[str]:
    """Get the docker-compose command (try v2 first, fallback to v1)."""
    try:
        subprocess.run(
            ["docker", "compose", "version"],
            capture_output=True,
            check=True,
        )
        return ["docker", "compose"]
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ["docker-compose"]


def check_docker_compose_available() -> bool:
    """Check if docker-compose is available."""
    try:
        docker_cmd = get_docker_compose_cmd()
        subprocess.run(
            docker_cmd + ["--version"],
            capture_output=True,
            check=True,
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def get_service_status(service_name: str) -> str | None:
    """Get the status of a docker-compose service."""
    project_root = get_project_root()
    docker_cmd = get_docker_compose_cmd()
    try:
        result = subprocess.run(
            docker_cmd + ["ps", "--format", "json", service_name],
            capture_output=True,
            text=True,
            check=True,
            cwd=project_root,
        )
        if not result.stdout.strip():
            return None

        # Parse JSON output (one line per container)
        lines = [line for line in result.stdout.strip().split("\n") if line]
        if not lines:
            return None

        # Get the first container's state
        container_info = json.loads(lines[0])
        return container_info.get("State", "").lower()
    except (subprocess.CalledProcessError, FileNotFoundError, ValueError):
        return None


def is_service_running(service_name: str) -> bool:
    """Check if a docker-compose service is running."""
    status = get_service_status(service_name)
    return status in ("running", "up")


def get_service_ports(service_name: str) -> dict[str, str]:
    """Get port mappings for a docker-compose service."""
    project_root = get_project_root()
    docker_cmd = get_docker_compose_cmd()
    try:
        result = subprocess.run(
            docker_cmd + ["ps", "--format", "json", service_name],
            capture_output=True,
            text=True,
            check=True,
            cwd=project_root,
        )
        if not result.stdout.strip():
            return {}

        lines = [line for line in result.stdout.strip().split("\n") if line]
        if not lines:
            return {}

        container_info = json.loads(lines[0])
        ports = container_info.get("Ports", "")

        # Parse port mappings (format: "0.0.0.0:5433->5432/tcp")
        port_mappings = {}
        if ports:
            for port_str in ports.split(", "):
                if "->" in port_str:
                    # Extract host:port -> container:port
                    parts = port_str.split("->")
                    if len(parts) == 2:
                        host_part = parts[0].strip()
                        # Extract port from "0.0.0.0:5433" or "5433"
                        if ":" in host_part:
                            host_port = host_part.split(":")[-1]
                        else:
                            host_port = host_part
                        # Remove /tcp suffix if present
                        host_port = host_port.split("/")[0]
                        port_mappings[service_name] = host_port

        return port_mappings
    except (subprocess.CalledProcessError, FileNotFoundError, ValueError, KeyError):
        return {}


def start_services(services: list[str], wait_for_healthy: bool = True) -> bool:
    """Start docker-compose services."""
    project_root = get_project_root()
    docker_cmd = get_docker_compose_cmd()

    print(f"\n🚀 Starting services: {', '.join(services)}...")

    try:
        # Start services
        subprocess.run(
            docker_cmd + ["up", "-d"] + services,
            check=True,
            cwd=project_root,
        )

        if wait_for_healthy:
            print("⏳ Waiting for services to be ready...")
            # Wait for postgres healthcheck if it's in the list
            if "postgres" in services:
                max_wait = 30  # seconds
                waited = 0
                while waited < max_wait:
                    status = get_service_status("postgres")
                    if status == "running":
                        # Check if postgres is actually ready
                        try:
                            result = subprocess.run(
                                docker_cmd
                                + ["exec", "-T", "postgres", "pg_isready", "-U", "h_arcane"],
                                capture_output=True,
                                check=True,
                                cwd=project_root,
                            )
                            if result.returncode == 0:
                                print("✅ PostgreSQL is ready")
                                break
                        except subprocess.CalledProcessError:
                            pass

                    time.sleep(1)
                    waited += 1
                    if waited % 5 == 0:
                        print(f"   Still waiting... ({waited}s)")

                if waited >= max_wait:
                    print("⚠️  PostgreSQL took longer than expected to start")

            # Wait for other services to be running
            for service in services:
                if service == "postgres":
                    continue
                max_wait = 15
                waited = 0
                while waited < max_wait:
                    if is_service_running(service):
                        print(f"✅ {service} is running")
                        break
                    time.sleep(1)
                    waited += 1

        # Print port information
        print("\n📡 Service Ports:")
        service_ports = {
            "postgres": "5433",
            "api": "9000",
            "inngest-dev": "8289",
        }
        for service in services:
            if service in service_ports:
                print(f"   {service}: http://localhost:{service_ports[service]}")

        print("\n✅ All services started\n")
        return True

    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to start services: {e}")
        return False


def ensure_services_running(required_services: list[str] | None = None) -> bool:
    """Ensure required docker-compose services are running, start them if not."""
    if required_services is None:
        required_services = ["postgres", "inngest-dev", "api"]

    if not check_docker_compose_available():
        print("❌ docker-compose is not available. Please install Docker Compose.")
        return False

    # Check which services need to be started
    services_to_start = []
    for service in required_services:
        if not is_service_running(service):
            services_to_start.append(service)

    if not services_to_start:
        print("✅ All required services are running")
        return True

    return start_services(services_to_start)


async def main():
    parser = argparse.ArgumentParser(
        description="Run H-ARCANE experiments",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run 10 examples with ReAct baseline
  python scripts/run_experiments.py --num-examples 10 --baseline react
  
  # Check progress
  python scripts/run_experiments.py --progress
  
  # Retry failed runs
  python scripts/run_experiments.py --retry-failed
  
  # Dry run (don't start runs)
  python scripts/run_experiments.py --num-examples 5 --dry-run
        """,
    )

    parser.add_argument(
        "--num-examples",
        type=int,
        help="Number of examples to run (default: all available)",
    )
    parser.add_argument(
        "--baseline",
        type=str,
        choices=["react"],
        default="react",
        help="Baseline to run (default: react)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't actually start runs, just show what would run",
    )
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="Retry failed runs",
    )
    parser.add_argument(
        "--progress",
        action="store_true",
        help="Show current experiment progress",
    )

    args = parser.parse_args()

    # Ensure services are running (except for progress check which only needs DB)
    if args.progress:
        # Progress check only needs database
        if not ensure_services_running(required_services=["postgres"]):
            print("⚠️  Warning: Database may not be available")
    else:
        # Other commands need all services
        if not ensure_services_running():
            print("❌ Required services are not running. Exiting.")
            sys.exit(1)

    # Create config
    config = ExperimentConfig(
        baseline=BaselineType(args.baseline),
    )

    runner = ExperimentRunner(config=config)

    if args.progress:
        progress = await runner.get_progress()
        print("\n📊 Experiment Progress:")
        print(f"   Total: {progress['total']}")
        print(f"   Pending: {progress['pending']}")
        print(f"   Running: {progress['running']}")
        print(f"   Completed: {progress['completed']}")
        print(f"   Failed: {progress['failed']}")
        print(f"   Completion Rate: {progress['completion_rate']:.2%}")
        return

    if args.retry_failed:
        retried = await runner.retry_failed()
        print(f"\n✅ Retried {retried} failed runs")
        return

    result = await runner.run_full_suite(
        task_limit=args.num_examples,
        dry_run=args.dry_run,
    )

    if result.get("dry_run"):
        print("\n🔍 Dry Run Complete!")
        print(f"   Would create: {result.get('experiments', 0)} experiments")
        print(f"   Would create: {result.get('runs', 0)} runs")
    else:
        print("\n✅ Completed!")
        print(f"   Started: {result.get('started', 0)} runs")
        print(f"   Experiments: {result.get('experiments', 0)}")


if __name__ == "__main__":
    asyncio.run(main())
