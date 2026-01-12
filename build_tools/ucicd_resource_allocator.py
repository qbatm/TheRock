#!/usr/bin/env python3
"""
UCICD Resource Allocator

This script ensures that the proper number of special labeled runners
are connected to a GitHub repository. It reads a configuration file
specifying the desired runner counts per label/type and compares against
the currently connected runners.

If runners are missing, it will allocate machines from a pool of
pre-provisioned machines that are already ready and waiting.
If there are too many runners, it will release excess machines back to the pool.

Usage:
    python ucicd_resource_allocator.py --config <config_file> --repository <owner/repo>

Options:
    --config        Path to the runner configuration JSON file
    --repository    GitHub repository in format owner/repo
"""

import argparse
import json
import sys
from dataclasses import dataclass


@dataclass
class RunnerRequirement:
    """Represents a runner requirement from the configuration."""
    label: str
    min_count: int
    max_count: int
    maas_tags: list[str]  # Tags used to identify machines in the pool
    platform: str = "linux"  # "linux" or "windows"
    description: str = ""


@dataclass
class RunnerStatus:
    """Represents the current status of runners for a specific label."""
    label: str
    connected_count: int
    busy_count: int
    idle_count: int


@dataclass
class AllocationAction:
    """Represents an action to be taken for runner allocation."""
    label: str
    action: str  # "add", "remove", "none"
    count: int
    reason: str


def load_config(config_path: str) -> list[RunnerRequirement]:
    """Load runner requirements from the configuration file."""
    print(f"Loading configuration from: {config_path}")
    
    with open(config_path, 'r') as f:
        config = json.load(f)
    
    requirements = []
    for runner_config in config.get("runners", []):
        req = RunnerRequirement(
            label=runner_config["label"],
            min_count=runner_config.get("min_count", 1),
            max_count=runner_config.get("max_count", 10),
            maas_tags=runner_config.get("maas_tags", []),
            platform=runner_config.get("platform", "linux"),
            description=runner_config.get("description", ""),
        )
        requirements.append(req)
    
    return requirements


def get_current_runners(repository: str, label: str) -> RunnerStatus:
    """
    Get the current status of runners for a specific label.
    
    TODO: This is a mock implementation. Replace with actual GitHub API calls.
    """
    # Mock implementation - in reality, this would call the GitHub API
    # GET /repos/{owner}/{repo}/actions/runners
    # and filter by label
    
    # Mock data - simulating different states for different labels
    mock_data = {
        "arc-lnx-pub": RunnerStatus(label="arc-lnx-pub", connected_count=5, busy_count=2, idle_count=3),
        "arc-win-pub": RunnerStatus(label="arc-win-pub", connected_count=2, busy_count=1, idle_count=1),
        "gpu-mi300x": RunnerStatus(label="gpu-mi300x", connected_count=0, busy_count=0, idle_count=0),
        "gpu-mi250": RunnerStatus(label="gpu-mi250", connected_count=1, busy_count=1, idle_count=0),
    }
    
    return mock_data.get(label, RunnerStatus(label=label, connected_count=0, busy_count=0, idle_count=0))


def calculate_allocation_actions(
    requirements: list[RunnerRequirement],
    repository: str
) -> list[AllocationAction]:
    """
    Calculate what actions need to be taken to meet runner requirements.
    """
    actions = []
    
    for req in requirements:
        status = get_current_runners(repository, req.label)
        
        if status.connected_count < req.min_count:
            # Need to add runners
            needed = req.min_count - status.connected_count
            actions.append(AllocationAction(
                label=req.label,
                action="add",
                count=needed,
                reason=f"Below minimum ({status.connected_count}/{req.min_count})"
            ))
        elif status.connected_count > req.max_count:
            # Need to remove runners (scale down)
            excess = status.connected_count - req.max_count
            actions.append(AllocationAction(
                label=req.label,
                action="remove",
                count=excess,
                reason=f"Above maximum ({status.connected_count}/{req.max_count})"
            ))
        else:
            # Within acceptable range
            actions.append(AllocationAction(
                label=req.label,
                action="none",
                count=0,
                reason=f"OK ({status.connected_count} runners, range: {req.min_count}-{req.max_count})"
            ))
    
    return actions


def allocate_runners(action: AllocationAction, repository: str) -> bool:
    """
    Allocate runners from the pre-provisioned machine pool for a specific label.
    
    TODO: This is a mock implementation. Replace with actual allocation logic.
    This will request machines from the pool of pre-provisioned machines.
    """
    # Mock implementation
    print(f"  [MOCK] Allocating {action.count} runner(s) with label '{action.label}' from pool")
    print(f"  [MOCK] This would request machines from the pre-provisioned pool")
    
    # In reality, this would:
    # 1. Query the machine pool for available machines of the required type
    # 2. Generate a runner registration token via GitHub API
    # 3. Assign the machines from the pool to this repository
    # 4. Register the runners with the repository
    
    return True


def release_runners(action: AllocationAction, repository: str) -> bool:
    """
    Release excess runners back to the machine pool for a specific label.
    
    TODO: This is a mock implementation. Replace with actual release logic.
    """
    # Mock implementation
    print(f"  [MOCK] Releasing {action.count} runner(s) with label '{action.label}' back to pool")
    print(f"  [MOCK] This would unregister runners and return machines to the pool")
    
    return True


def execute_actions(
    actions: list[AllocationAction],
    repository: str
) -> tuple[int, int]:
    """
    Execute the calculated allocation actions.
    
    Returns:
        Tuple of (success_count, failure_count)
    """
    success_count = 0
    failure_count = 0
    
    for action in actions:
        if action.action == "add":
            print(f"\n[ACTION] Allocating {action.count} runner(s) for '{action.label}' from pool")
            print(f"  Reason: {action.reason}")
            if allocate_runners(action, repository):
                success_count += 1
            else:
                failure_count += 1
                
        elif action.action == "remove":
            print(f"\n[ACTION] Releasing {action.count} runner(s) for '{action.label}' back to pool")
            print(f"  Reason: {action.reason}")
            if release_runners(action, repository):
                success_count += 1
            else:
                failure_count += 1
                
        else:
            print(f"\n[OK] '{action.label}': {action.reason}")
    
    return success_count, failure_count


def main():
    parser = argparse.ArgumentParser(
        description="UCICD Resource Allocator - Manage GitHub Actions runners"
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Path to the runner configuration JSON file"
    )
    parser.add_argument(
        "--repository",
        required=True,
        help="GitHub repository in format owner/repo"
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("UCICD Resource Allocator")
    print("=" * 60)
    print(f"Repository: {args.repository}")
    print(f"Config: {args.config}")
    print("=" * 60)
    
    # Load configuration
    try:
        requirements = load_config(args.config)
        print(f"Loaded {len(requirements)} runner requirement(s)")
    except FileNotFoundError:
        print(f"ERROR: Configuration file not found: {args.config}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON in configuration file: {e}")
        sys.exit(1)
    
    # Print requirements
    print("\n--- Runner Requirements ---")
    for req in requirements:
        print(f"  - {req.label}: min={req.min_count}, max={req.max_count} (tags: {req.maas_tags})")
        if req.description:
            print(f"    Description: {req.description}")
    
    # Calculate actions
    print("\n--- Checking Current State ---")
    actions = calculate_allocation_actions(requirements, args.repository)
    
    # Execute actions
    print("\n--- Executing Actions ---")
    success, failures = execute_actions(actions, args.repository)
    
    # Summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    actions_needed = sum(1 for a in actions if a.action != "none")
    print(f"Total requirements: {len(requirements)}")
    print(f"Actions needed: {actions_needed}")
    print(f"Successful actions: {success}")
    print(f"Failed actions: {failures}")
    
    if failures > 0:
        print("\nWARNING: Some actions failed!")
        sys.exit(1)
    
    print("\nResource allocation check completed successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
