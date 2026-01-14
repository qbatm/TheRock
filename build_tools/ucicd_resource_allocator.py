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
import os
import re
import subprocess
import sys
from dataclasses import dataclass

import requests


@dataclass
class RunnerRequirement:
    """Represents a runner requirement from the configuration."""
    label: str
    max_count: int  # Target number of runners to maintain
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
    requirement: "RunnerRequirement | None" = None  # The original requirement for this action


@dataclass
class PoolMachine:
    """Represents a machine available in the pool."""
    hostname: str
    tags: list[str]
    platform: str  # "linux" or "windows"
    status: str = "available"  # "available", "in_use", "maintenance"


@dataclass
class RegisteredRunner:
    """Represents a runner registered to the repository."""
    id: int
    name: str
    os: str  # "Linux" or "Windows"
    status: str  # "online" or "offline"
    busy: bool
    labels: list[str]


def load_config(config_path: str) -> list[RunnerRequirement]:
    """Load runner requirements from the configuration file."""
    print(f"Loading configuration from: {config_path}")
    
    with open(config_path, 'r') as f:
        config = json.load(f)
    
    requirements = []
    for runner_config in config.get("runners", []):
        req = RunnerRequirement(
            label=runner_config["label"],
            max_count=runner_config.get("max_count", 1),
            maas_tags=runner_config.get("maas_tags", []),
            platform=runner_config.get("platform", "linux"),
            description=runner_config.get("description", ""),
        )
        requirements.append(req)
    
    return requirements


def get_github_token() -> str:
    """Get GitHub token from environment variable."""
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise ValueError(
            "GITHUB_TOKEN environment variable is not set. "
            "Please set it with a token that has 'admin:org' or 'repo' scope."
        )
    return token


def normalize_repository(repository: str) -> str:
    """
    Normalize repository input to owner/repo format.
    
    Accepts:
        - owner/repo
        - https://github.com/owner/repo
        - https://github.com/owner/repo.git
        - git@github.com:owner/repo.git
    
    Returns:
        Repository in owner/repo format.
    """
    import re
    
    # Already in owner/repo format
    if re.match(r'^[^/]+/[^/]+$', repository):
        return repository.rstrip('.git')
    
    # HTTPS URL format
    https_match = re.match(r'^https?://github\.com/([^/]+)/([^/]+?)(?:\.git)?/?$', repository)
    if https_match:
        return f"{https_match.group(1)}/{https_match.group(2)}"
    
    # SSH URL format
    ssh_match = re.match(r'^git@github\.com:([^/]+)/([^/]+?)(?:\.git)?$', repository)
    if ssh_match:
        return f"{ssh_match.group(1)}/{ssh_match.group(2)}"
    
    raise ValueError(
        f"Invalid repository format: '{repository}'. "
        "Expected 'owner/repo' or a GitHub URL like 'https://github.com/owner/repo'."
    )


def get_available_machines_from_pool(tags: list[str], platform: str) -> list[PoolMachine]:
    """
    Get available machines from the pool that match the given tags and platform.
    
    TODO: This is a mock implementation. Replace with actual MaaS API calls.
    
    Args:
        tags: List of tags to filter machines by (e.g., ['gpu_navi3x'])
        platform: Platform filter ('linux' or 'windows')
    
    Returns:
        List of available PoolMachine objects matching the criteria.
    """
    # Mock pool of available machines
    mock_pool = [
        PoolMachine(
            hostname="CS-UCICD-DT155",
            tags=["gpu_navi4x"],
            platform="linux",
            status="available",
        ),
        PoolMachine(
            hostname="CS-UCICD-DT29",
            tags=["gpu_navi3x"],
            platform="windows",
            status="available",
        ),
    ]
    
    # Filter machines by tags and platform
    matching_machines = []
    for machine in mock_pool:
        # Check platform match
        if machine.platform != platform:
            continue
        # Check if machine has at least one matching tag
        if any(tag in machine.tags for tag in tags):
            if machine.status == "available":
                matching_machines.append(machine)
    
    return matching_machines


def generate_runner_registration_token(repository: str) -> str:
    """
    Generate a GitHub Actions runner registration token.
    
    Uses GitHub API: POST /repos/{owner}/{repo}/actions/runners/registration-token
    
    Returns:
        The registration token string.
    """
    token = get_github_token()
    
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    
    api_url = f"https://api.github.com/repos/{repository}/actions/runners/registration-token"
    
    response = requests.post(api_url, headers=headers, timeout=30)
    
    if response.status_code == 401:
        raise ValueError("GitHub API authentication failed. Check your GITHUB_TOKEN.")
    elif response.status_code == 404:
        raise ValueError(f"Repository '{repository}' not found or no access to create runner tokens.")
    elif response.status_code != 201:
        raise ValueError(f"GitHub API error: {response.status_code} - {response.text}")
    
    data = response.json()
    return data["token"]


def generate_runner_removal_token(repository: str) -> str:
    """
    Generate a GitHub Actions runner removal token.
    
    Uses GitHub API: POST /repos/{owner}/{repo}/actions/runners/remove-token
    
    Returns:
        The removal token string.
    """
    token = get_github_token()
    
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    
    api_url = f"https://api.github.com/repos/{repository}/actions/runners/remove-token"
    
    response = requests.post(api_url, headers=headers, timeout=30)
    
    if response.status_code == 401:
        raise ValueError("GitHub API authentication failed. Check your GITHUB_TOKEN.")
    elif response.status_code == 404:
        raise ValueError(f"Repository '{repository}' not found or no access to create runner tokens.")
    elif response.status_code != 201:
        raise ValueError(f"GitHub API error: {response.status_code} - {response.text}")
    
    data = response.json()
    return data["token"]


# SSH connection settings
SSH_DOMAIN = "mkm.ctr.maas"


def get_ssh_credentials(platform: str) -> dict[str, str]:
    """
    Get SSH credentials for the given platform.
    
    Reads passwords from environment variables:
    - LNX_SSH_PASS: Password for Linux machines
    - WIN_SSH_PASS: Password for Windows machines
    
    Args:
        platform: 'linux' or 'windows'
    
    Returns:
        Dictionary with 'user' and 'password' keys.
    
    Raises:
        ValueError: If the required environment variable is not set.
    """
    if platform == "linux":
        password = os.environ.get("LNX_SSH_PASS")
        if not password:
            raise ValueError(
                "LNX_SSH_PASS environment variable is not set. "
                "Please set it with the SSH password for Linux machines."
            )
        return {"user": "ubuntu", "password": password}
    elif platform == "windows":
        password = os.environ.get("WIN_SSH_PASS")
        if not password:
            raise ValueError(
                "WIN_SSH_PASS environment variable is not set. "
                "Please set it with the SSH password for Windows machines."
            )
        return {"user": "defaultuser", "password": password}
    else:
        raise ValueError(f"Unknown platform: {platform}")


def get_ssh_target(machine: PoolMachine) -> str:
    """Get the full SSH target (user@hostname.domain) for a machine."""
    creds = get_ssh_credentials(machine.platform)
    return f"{creds['user']}@{machine.hostname}.{SSH_DOMAIN}"


def run_ssh_command(
    machine: PoolMachine,
    command: str,
    timeout: int = 120,
) -> tuple[bool, str, str]:
    """
    Run a command on a remote machine via SSH using sshpass for password auth.
    
    Args:
        machine: The target machine.
        command: The command to execute.
        timeout: Command timeout in seconds.
    
    Returns:
        Tuple of (success, stdout, stderr).
    """
    creds = get_ssh_credentials(machine.platform)
    ssh_target = get_ssh_target(machine)
    
    try:
        result = subprocess.run(
            [
                "sshpass", "-p", creds["password"],
                "ssh",
                "-o", "StrictHostKeyChecking=no",
                "-o", "UserKnownHostsFile=/dev/null",
                "-o", "ConnectTimeout=30",
                ssh_target,
                command,
            ],
            capture_output=True,
            timeout=timeout,
        )
        # Decode with error handling for Windows machines that may return non-UTF-8 output
        try:
            stdout = result.stdout.decode("utf-8")
        except UnicodeDecodeError:
            stdout = result.stdout.decode("utf-8", errors="replace")
        try:
            stderr = result.stderr.decode("utf-8")
        except UnicodeDecodeError:
            stderr = result.stderr.decode("utf-8", errors="replace")
        return result.returncode == 0, stdout, stderr
    except subprocess.TimeoutExpired:
        return False, "", "SSH command timed out"
    except FileNotFoundError:
        return False, "", "sshpass not found. Install it with: apt install sshpass (Linux) or brew install hudochenkov/sshpass/sshpass (macOS)"
    except Exception as e:
        return False, "", str(e)


def register_runner_on_linux(
    machine: PoolMachine,
    repository: str,
    registration_token: str,
    labels: list[str],
) -> bool:
    """
    Register a GitHub Actions runner on a Linux machine via SSH.
    
    Args:
        machine: The PoolMachine to register as a runner.
        repository: The GitHub repository (owner/repo format).
        registration_token: The GitHub runner registration token.
        labels: List of labels to assign to the runner.
    
    Returns:
        True if registration was successful, False otherwise.
    """
    runner_name = machine.hostname
    labels_str = ",".join(labels)
    repo_url = f"https://github.com/{repository}"
    ssh_target = get_ssh_target(machine)
    
    # Commands to execute on the remote machine
    # This assumes the runner is already downloaded and extracted at ~/actions-runner
    configure_cmd = (
        f"cd ~/actions-runner && "
        f"./config.sh --url {repo_url} --token {registration_token} "
        f"--name {runner_name} --labels {labels_str} --unattended --replace"
    )
    
    # Install and start runner as a systemd service (persists across SSH disconnect and reboots)
    install_service_cmd = "cd ~/actions-runner && sudo ./svc.sh install"
    start_service_cmd = "cd ~/actions-runner && sudo ./svc.sh start"
    
    print(f"    Connecting to {ssh_target}...")
    
    # Execute configuration command
    success, stdout, stderr = run_ssh_command(machine, configure_cmd, timeout=120)
    
    if not success:
        print(f"    ERROR: Failed to configure runner: {stderr}")
        return False
    
    print(f"    Runner configured successfully")
    
    # Install the runner as a systemd service
    print(f"    Installing runner as systemd service...")
    success, stdout, stderr = run_ssh_command(machine, install_service_cmd, timeout=60)
    
    if not success:
        print(f"    WARNING: Service install returned non-zero: {stderr}")
        # May fail if already installed, continue to start
    
    # Start the service
    print(f"    Starting runner service...")
    success, stdout, stderr = run_ssh_command(machine, start_service_cmd, timeout=30)
    
    if not success:
        print(f"    WARNING: Service start returned non-zero: {stderr}")
    
    print(f"    Runner service started on {machine.hostname}")
    return True


def register_runner_on_windows(
    machine: PoolMachine,
    repository: str,
    registration_token: str,
    labels: list[str],
) -> bool:
    """
    Register a GitHub Actions runner on a Windows machine via SSH.
    
    Args:
        machine: The PoolMachine to register as a runner.
        repository: The GitHub repository (owner/repo format).
        registration_token: The GitHub runner registration token.
        labels: List of labels to assign to the runner.
    
    Returns:
        True if registration was successful, False otherwise.
    """
    runner_name = machine.hostname
    labels_str = ",".join(labels)
    repo_url = f"https://github.com/{repository}"
    ssh_target = get_ssh_target(machine)
    
    # Commands to execute on the Windows machine via SSH
    # This assumes the runner is already downloaded and extracted at C:\actions-runner
    # Using full paths for reliable execution in PowerShell over SSH
    runner_dir = "C:\\actions-runner"
    configure_cmd = (
        f"& '{runner_dir}\\config.cmd' --url {repo_url} --token {registration_token} "
        f"--name {runner_name} --labels {labels_str} --unattended --replace"
    )
    
    # Check if svc.cmd exists (may not exist in older runner versions)
    check_svc_cmd = f"Test-Path '{runner_dir}\\svc.cmd'"
    
    # Install and start runner as a Windows service (if svc.cmd exists)
    install_service_cmd = f"& '{runner_dir}\\svc.cmd' install"
    start_service_cmd = f"& '{runner_dir}\\svc.cmd' start"
    
    # Fallback: Create a scheduled task to run the runner at startup
    task_name = f"GitHubActionsRunner_{runner_name}"
    create_task_cmd = (
        f"schtasks /Create /TN '{task_name}' /TR '{runner_dir}\\run.cmd' "
        f"/SC ONSTART /RU SYSTEM /F /RL HIGHEST"
    )
    start_task_cmd = f"schtasks /Run /TN '{task_name}'"
    
    print(f"    Connecting to {ssh_target}...")
    
    # Execute configuration command
    success, stdout, stderr = run_ssh_command(machine, configure_cmd, timeout=120)
    
    if not success:
        print(f"    ERROR: Failed to configure runner: {stderr}")
        return False
    
    print(f"    Runner configured successfully")
    
    # Check if svc.cmd exists
    print(f"    Checking for svc.cmd...")
    success, stdout, stderr = run_ssh_command(machine, check_svc_cmd, timeout=30)
    has_svc_cmd = success and "True" in stdout
    
    if has_svc_cmd:
        # Use the service approach
        print(f"    Installing runner as Windows service...")
        success, stdout, stderr = run_ssh_command(machine, install_service_cmd, timeout=60)
        
        if not success:
            print(f"    ERROR: Service install failed: {stderr}")
            return False
        
        print(f"    Starting runner service...")
        success, stdout, stderr = run_ssh_command(machine, start_service_cmd, timeout=30)
        
        if not success:
            print(f"    ERROR: Service start failed: {stderr}")
            return False
        
        print(f"    Runner service started on {machine.hostname}")
    else:
        # Fallback to scheduled task
        print(f"    svc.cmd not found, using scheduled task fallback...")
        print(f"    Creating scheduled task...")
        success, stdout, stderr = run_ssh_command(machine, create_task_cmd, timeout=60)
        
        if not success:
            print(f"    ERROR: Failed to create scheduled task: {stderr}")
            return False
        
        print(f"    Starting scheduled task...")
        success, stdout, stderr = run_ssh_command(machine, start_task_cmd, timeout=30)
        
        if not success:
            print(f"    WARNING: Failed to start scheduled task: {stderr}")
            # Task was created, it will run on next boot
        
        print(f"    Runner scheduled task created on {machine.hostname}")
    
    return True


def register_runner(
    machine: PoolMachine,
    repository: str,
    registration_token: str,
    labels: list[str],
) -> bool:
    """
    Register a GitHub Actions runner on the given machine.
    
    Dispatches to the appropriate platform-specific function.
    """
    if machine.platform == "linux":
        return register_runner_on_linux(machine, repository, registration_token, labels)
    elif machine.platform == "windows":
        return register_runner_on_windows(machine, repository, registration_token, labels)
    else:
        print(f"    ERROR: Unsupported platform: {machine.platform}")
        return False


def get_all_registered_runner_names(repository: str) -> set[str]:
    """
    Get the names of all runners registered to the repository.
    
    Uses GitHub API: GET /repos/{owner}/{repo}/actions/runners
    
    Returns:
        Set of runner names (hostnames) currently registered.
    """
    token = get_github_token()
    
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    
    api_url = f"https://api.github.com/repos/{repository}/actions/runners"
    
    runner_names: set[str] = set()
    
    # Handle pagination
    page = 1
    per_page = 100
    
    while True:
        response = requests.get(
            api_url,
            headers=headers,
            params={"per_page": per_page, "page": page},
            timeout=30,
        )
        
        if response.status_code == 401:
            raise ValueError("GitHub API authentication failed. Check your GITHUB_TOKEN.")
        elif response.status_code == 404:
            raise ValueError(f"Repository '{repository}' not found or no access to runners.")
        elif response.status_code != 200:
            raise ValueError(f"GitHub API error: {response.status_code} - {response.text}")
        
        data = response.json()
        runners = data.get("runners", [])
        
        for runner in runners:
            runner_names.add(runner.get("name", ""))
        
        # Check if there are more pages
        if len(runners) < per_page:
            break
        page += 1
    
    return runner_names


def get_all_registered_runners(repository: str) -> list[RegisteredRunner]:
    """
    Get all runners registered to the repository with full details.
    
    Uses GitHub API: GET /repos/{owner}/{repo}/actions/runners
    
    Returns:
        List of RegisteredRunner objects.
    """
    token = get_github_token()
    
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    
    api_url = f"https://api.github.com/repos/{repository}/actions/runners"
    
    registered_runners: list[RegisteredRunner] = []
    
    # Handle pagination
    page = 1
    per_page = 100
    
    while True:
        response = requests.get(
            api_url,
            headers=headers,
            params={"per_page": per_page, "page": page},
            timeout=30,
        )
        
        if response.status_code == 401:
            raise ValueError("GitHub API authentication failed. Check your GITHUB_TOKEN.")
        elif response.status_code == 404:
            raise ValueError(f"Repository '{repository}' not found or no access to runners.")
        elif response.status_code != 200:
            raise ValueError(f"GitHub API error: {response.status_code} - {response.text}")
        
        data = response.json()
        runners = data.get("runners", [])
        
        for runner in runners:
            labels = [lbl["name"] for lbl in runner.get("labels", [])]
            registered_runners.append(RegisteredRunner(
                id=runner.get("id"),
                name=runner.get("name", ""),
                os=runner.get("os", "Unknown"),
                status=runner.get("status", "offline"),
                busy=runner.get("busy", False),
                labels=labels,
            ))
        
        # Check if there are more pages
        if len(runners) < per_page:
            break
        page += 1
    
    return registered_runners


def get_current_runners(repository: str, maas_tags: list[str], platform: str) -> RunnerStatus:
    """
    Get the current status of runners for specific maas_tags and platform.
    
    Uses GitHub API: GET /repos/{owner}/{repo}/actions/runners
    and filters runners by the specified maas_tags AND platform (using runner's OS field).
    
    Args:
        repository: The GitHub repository (owner/repo format).
        maas_tags: List of tags to search for (runner must have at least one).
        platform: Platform filter ('linux' or 'windows').
    """
    token = get_github_token()
    
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    
    # GitHub API endpoint for repository runners
    api_url = f"https://api.github.com/repos/{repository}/actions/runners"
    
    connected_count = 0
    busy_count = 0
    idle_count = 0
    
    # Map platform to GitHub's OS field values
    platform_to_os = {
        "linux": "Linux",
        "windows": "Windows",
    }
    expected_os = platform_to_os.get(platform, platform)
    
    # Handle pagination
    page = 1
    per_page = 100
    
    while True:
        response = requests.get(
            api_url,
            headers=headers,
            params={"per_page": per_page, "page": page},
            timeout=30,
        )
        
        if response.status_code == 401:
            raise ValueError("GitHub API authentication failed. Check your GITHUB_TOKEN.")
        elif response.status_code == 404:
            raise ValueError(f"Repository '{repository}' not found or no access to runners.")
        elif response.status_code != 200:
            raise ValueError(f"GitHub API error: {response.status_code} - {response.text}")
        
        data = response.json()
        runners = data.get("runners", [])
        
        # Filter runners that have at least one maas_tag AND match the platform (by OS)
        for runner in runners:
            runner_labels = [lbl["name"] for lbl in runner.get("labels", [])]
            runner_os = runner.get("os", "Unknown")
            
            # Must have at least one maas_tag AND match the expected OS
            has_matching_tag = any(tag in runner_labels for tag in maas_tags)
            if has_matching_tag and runner_os == expected_os:
                connected_count += 1
                if runner.get("busy", False):
                    busy_count += 1
                else:
                    idle_count += 1
        
        # Check if there are more pages
        if len(runners) < per_page:
            break
        page += 1
    
    return RunnerStatus(
        label=",".join(maas_tags),
        connected_count=connected_count,
        busy_count=busy_count,
        idle_count=idle_count,
    )


def calculate_allocation_actions(
    requirements: list[RunnerRequirement],
    repository: str
) -> list[AllocationAction]:
    """
    Calculate what actions need to be taken to meet runner requirements.
    
    Tries to fill up to max_count runners for each requirement.
    """
    actions = []
    
    for req in requirements:
        print(f"  Checking runners with tags {req.maas_tags} on platform '{req.platform}'...")
        status = get_current_runners(repository, req.maas_tags, req.platform)
        print(f"    Found: {status.connected_count} connected ({status.busy_count} busy, {status.idle_count} idle)")
        
        if status.connected_count < req.max_count:
            # Try to add runners up to max_count
            needed = req.max_count - status.connected_count
            actions.append(AllocationAction(
                label=req.label,
                action="add",
                count=needed,
                reason=f"Below target ({status.connected_count}/{req.max_count})",
                requirement=req,
            ))
        else:
            # Already at or above max_count
            actions.append(AllocationAction(
                label=req.label,
                action="none",
                count=0,
                reason=f"OK ({status.connected_count}/{req.max_count} runners)",
                requirement=req,
            ))
    
    return actions


def allocate_runners(
    action: AllocationAction,
    requirement: RunnerRequirement,
    repository: str,
) -> tuple[bool, str]:
    """
    Allocate runners from the pre-provisioned machine pool for a specific label.
    
    This will:
    1. Query the machine pool for available machines matching the requirement
    2. Generate a runner registration token via GitHub API
    3. Connect to machines and register them as GitHub runners
    
    Args:
        action: The allocation action with count and label info.
        requirement: The runner requirement with tags and platform info.
        repository: The GitHub repository (owner/repo format).
    
    Returns:
        Tuple of (success, reason) where:
        - success: True if allocation succeeded or pool is just exhausted
        - reason: 'success', 'pool_exhausted', or 'error'
    """
    print(f"  Looking for {action.count} machine(s) with tags {requirement.maas_tags} "
          f"on platform '{requirement.platform}'...")
    
    # Get available machines from the pool
    available_machines = get_available_machines_from_pool(
        tags=requirement.maas_tags,
        platform=requirement.platform,
    )
    
    if not available_machines:
        print(f"  WARNING: No available machines found in pool matching criteria")
        return True, "pool_exhausted"
    
    print(f"  Found {len(available_machines)} machine(s) in pool matching criteria")
    
    # Filter out machines that are already registered as runners
    print(f"  Checking for already registered runners...")
    try:
        registered_runner_names = get_all_registered_runner_names(repository)
    except ValueError as e:
        print(f"  ERROR: Failed to get registered runners: {e}")
        return False, "error"
    
    unregistered_machines = [
        m for m in available_machines
        if m.hostname not in registered_runner_names
    ]
    
    already_registered = len(available_machines) - len(unregistered_machines)
    if already_registered > 0:
        print(f"  Filtered out {already_registered} machine(s) already registered as runners")
    
    available_machines = unregistered_machines
    
    if not available_machines:
        print(f"  WARNING: All matching machines are already registered as runners")
        return True, "pool_exhausted"
    
    print(f"  {len(available_machines)} unregistered machine(s) available for allocation")
    
    if len(available_machines) < action.count:
        print(f"  WARNING: Only {len(available_machines)} machines available, "
              f"but {action.count} requested")
    
    # Allocate up to the requested count
    machines_to_allocate = available_machines[:action.count]
    
    # Generate a registration token
    print(f"  Generating GitHub runner registration token...")
    try:
        registration_token = generate_runner_registration_token(repository)
        print(f"  Registration token obtained")
    except ValueError as e:
        print(f"  ERROR: Failed to generate registration token: {e}")
        return False, "error"
    
    # Labels to assign to the runners
    # Include: platform (e.g., linux) and maas_tags (e.g., gpu_navi4x)
    # The maas_tags are the actual hardware identifiers used in workflows
    labels = [requirement.platform] + requirement.maas_tags
    
    # Register each machine as a runner
    success_count = 0
    for machine in machines_to_allocate:
        print(f"  Registering runner on {machine.hostname}...")
        if register_runner(machine, repository, registration_token, labels):
            success_count += 1
        else:
            print(f"  Failed to register runner on {machine.hostname}")
    
    print(f"  Successfully registered {success_count}/{len(machines_to_allocate)} runner(s)")
    
    if success_count == 0:
        return False, "error"
    elif success_count < len(machines_to_allocate):
        return True, "partial"
    else:
        return True, "success"


def delete_runner_from_github(repository: str, runner_id: int) -> bool:
    """
    Delete a runner from GitHub using the API.
    
    Uses GitHub API: DELETE /repos/{owner}/{repo}/actions/runners/{runner_id}
    
    Args:
        repository: The GitHub repository (owner/repo format).
        runner_id: The ID of the runner to delete.
    
    Returns:
        True if deletion was successful, False otherwise.
    """
    token = get_github_token()
    
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    
    api_url = f"https://api.github.com/repos/{repository}/actions/runners/{runner_id}"
    
    response = requests.delete(api_url, headers=headers, timeout=30)
    
    if response.status_code == 204:
        return True
    elif response.status_code == 401:
        print(f"    ERROR: GitHub API authentication failed.")
        return False
    elif response.status_code == 404:
        print(f"    WARNING: Runner {runner_id} not found (may already be deleted).")
        return True  # Consider it success if already gone
    else:
        print(f"    ERROR: GitHub API error: {response.status_code} - {response.text}")
        return False


def unregister_runner_on_machine(
    runner: RegisteredRunner,
    repository: str,
    removal_token: str,
) -> bool:
    """
    Unregister a runner by SSHing to the machine and running the remove command.
    
    Args:
        runner: The RegisteredRunner to unregister.
        repository: The GitHub repository (owner/repo format).
        removal_token: The GitHub runner removal token.
    
    Returns:
        True if unregistration was successful, False otherwise.
    """
    # Determine platform from runner OS
    if runner.os.lower() == "linux":
        platform = "linux"
    elif runner.os.lower() == "windows":
        platform = "windows"
    else:
        print(f"    WARNING: Unknown OS '{runner.os}', assuming linux")
        platform = "linux"
    
    # Create a temporary PoolMachine object for SSH functions
    machine = PoolMachine(
        hostname=runner.name,
        tags=[],
        platform=platform,
        status="in_use",
    )
    
    ssh_target = get_ssh_target(machine)
    print(f"    Connecting to {ssh_target}...")
    
    # Stop the runner process first
    if platform == "linux":
        # Stop and uninstall the systemd service
        stop_cmd = "cd ~/actions-runner && sudo ./svc.sh stop && sudo ./svc.sh uninstall || true"
        remove_cmd = f"cd ~/actions-runner && ./config.sh remove --token {removal_token}"
    else:
        # Stop and uninstall the Windows service or scheduled task
        runner_dir = "C:\\actions-runner"
        task_name = f"GitHubActionsRunner_{runner.name}"
        # Try both service and scheduled task cleanup (one will succeed)
        stop_cmd = (
            f"& '{runner_dir}\\svc.cmd' stop 2>$null; "
            f"& '{runner_dir}\\svc.cmd' uninstall 2>$null; "
            f"schtasks /End /TN '{task_name}' 2>$null; "
            f"schtasks /Delete /TN '{task_name}' /F 2>$null; "
            f"$true"  # Always return success
        )
        remove_cmd = f"& '{runner_dir}\\config.cmd' remove --token {removal_token}"
    
    # Stop the runner
    print(f"    Stopping runner process...")
    success, stdout, stderr = run_ssh_command(machine, stop_cmd, timeout=30)
    if not success:
        print(f"    WARNING: Failed to stop runner process: {stderr}")
        # Continue anyway - runner might not be running
    
    # Remove the runner configuration
    print(f"    Removing runner configuration...")
    success, stdout, stderr = run_ssh_command(machine, remove_cmd, timeout=60)
    if not success:
        print(f"    WARNING: Failed to remove runner config: {stderr}")
        # Continue - we'll try to delete from GitHub API anyway
        return False
    
    print(f"    Runner unregistered from {runner.name}")
    return True


def release_all_runners(
    repository: str,
    force: bool = False,
    prefix: str | None = None,
    hostnames: list[str] | None = None,
) -> tuple[int, int]:
    """
    Release runners from the repository.
    
    Args:
        repository: The GitHub repository (owner/repo format).
        force: If True, delete from GitHub even if SSH unregister fails.
        prefix: If provided, only release runners whose names start with this prefix.
        hostnames: If provided, release only runners with these exact hostnames (overrides prefix).
    
    Returns:
        Tuple of (success_count, failure_count).
    """
    print(f"\n{'=' * 60}")
    print("RELEASING RUNNERS")
    print(f"{'=' * 60}")
    print(f"Repository: {repository}")
    print(f"Force mode: {force}")
    if hostnames:
        print(f"Target hostname(s): {', '.join(hostnames)}")
    else:
        print(f"Prefix filter: {prefix or '(none - releasing ALL runners)'}")
    print()
    
    # Get all registered runners
    print("Fetching all registered runners...")
    try:
        runners = get_all_registered_runners(repository)
    except ValueError as e:
        print(f"ERROR: Failed to get runners: {e}")
        return 0, 1
    
    if not runners:
        print("No runners registered to this repository.")
        return 0, 0
    
    print(f"Found {len(runners)} total registered runner(s)")
    
    # Filter by hostnames (exact match) or prefix
    if hostnames:
        hostname_set = set(hostnames)
        original_count = len(runners)
        runners = [r for r in runners if r.name in hostname_set]
        if not runners:
            print(f"No runners found matching hostname(s): {', '.join(hostnames)}")
            return 0, 0
        found_names = {r.name for r in runners}
        not_found = hostname_set - found_names
        if not_found:
            print(f"WARNING: Runner(s) not found: {', '.join(not_found)}")
        print(f"Found {len(runners)} runner(s) matching specified hostname(s)")
    elif prefix:
        original_count = len(runners)
        runners = [r for r in runners if r.name.startswith(prefix)]
        skipped = original_count - len(runners)
        if skipped > 0:
            print(f"Filtered to {len(runners)} runner(s) matching prefix '{prefix}' (skipping {skipped})")
        if not runners:
            print(f"No runners match prefix '{prefix}'.")
            return 0, 0
    
    print(f"\nRunners to release:")
    for runner in runners:
        status = "BUSY" if runner.busy else runner.status
        print(f"  - {runner.name} (ID: {runner.id}, OS: {runner.os}, Status: {status})")
    
    # Check for busy runners
    busy_runners = [r for r in runners if r.busy]
    if busy_runners and not force:
        print(f"\nWARNING: {len(busy_runners)} runner(s) are currently busy!")
        print("Use --force to release busy runners anyway.")
        print("Busy runners:")
        for r in busy_runners:
            print(f"  - {r.name}")
        return 0, len(busy_runners)
    
    # Generate removal token
    print("\nGenerating runner removal token...")
    try:
        removal_token = generate_runner_removal_token(repository)
        print("Removal token obtained.")
    except ValueError as e:
        print(f"ERROR: Failed to generate removal token: {e}")
        return 0, len(runners)
    
    # Release each runner
    success_count = 0
    failure_count = 0
    
    for runner in runners:
        print(f"\n--- Releasing runner: {runner.name} ---")
        
        if runner.busy and not force:
            print(f"  Skipping busy runner (use --force to override)")
            failure_count += 1
            continue
        
        # Try to unregister via SSH
        ssh_success = unregister_runner_on_machine(runner, repository, removal_token)
        
        if ssh_success:
            print(f"  Runner {runner.name} released successfully.")
            success_count += 1
        elif force:
            # Force delete from GitHub API
            print(f"  SSH unregister failed, force-deleting from GitHub...")
            if delete_runner_from_github(repository, runner.id):
                print(f"  Runner {runner.name} force-deleted from GitHub.")
                success_count += 1
            else:
                print(f"  Failed to delete runner {runner.name}.")
                failure_count += 1
        else:
            print(f"  Failed to release runner {runner.name}.")
            failure_count += 1
    
    # Summary
    print(f"\n{'=' * 60}")
    print("Release Summary")
    print(f"{'=' * 60}")
    print(f"Total runners: {len(runners)}")
    print(f"Successfully released: {success_count}")
    print(f"Failed: {failure_count}")
    
    return success_count, failure_count


def execute_actions(
    actions: list[AllocationAction],
    repository: str
) -> tuple[int, int, int]:
    """
    Execute the calculated allocation actions.
    
    Returns:
        Tuple of (success_count, failure_count, pool_exhausted_count)
    """
    success_count = 0
    failure_count = 0
    pool_exhausted_count = 0
    
    for action in actions:
        if action.action == "add":
            print(f"\n[ACTION] Allocating {action.count} runner(s) for '{action.label}' from pool")
            print(f"  Reason: {action.reason}")
            if action.requirement is None:
                print(f"  ERROR: No requirement found for action")
                failure_count += 1
            else:
                ok, reason = allocate_runners(action, action.requirement, repository)
                if reason == "pool_exhausted":
                    pool_exhausted_count += 1
                elif ok:
                    success_count += 1
                else:
                    failure_count += 1
        else:
            print(f"\n[OK] '{action.label}': {action.reason}")
    
    return success_count, failure_count, pool_exhausted_count


def main():
    parser = argparse.ArgumentParser(
        description="UCICD Resource Allocator - Manage GitHub Actions runners"
    )
    parser.add_argument(
        "--config",
        required=False,
        help="Path to the runner configuration JSON file (required unless using --release-all)"
    )
    parser.add_argument(
        "--repository",
        required=True,
        help="GitHub repository in format owner/repo"
    )
    parser.add_argument(
        "--release",
        action="store_true",
        help="Release runners from the repository (use --hostname for specific, --prefix for filtered, or neither for all)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force release even if runners are busy (use with --release)"
    )
    parser.add_argument(
        "--prefix",
        default="CS-UCICD",
        help="Only release runners whose names start with this prefix (default: CS-UCICD)"
    )
    parser.add_argument(
        "--hostname",
        help="Release specific runner(s) by hostname (comma-separated for multiple, overrides --prefix)"
    )
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("UCICD Resource Allocator")
    print("=" * 60)
    
    # Normalize repository format
    try:
        repository = normalize_repository(args.repository)
    except ValueError as e:
        print(f"ERROR: {e}")
        sys.exit(1)
    
    print(f"Repository: {repository}")
    print(f"Config: {args.config}")
    print("=" * 60)
    
    # Handle --release mode
    if args.release:
        # Parse comma-separated hostnames if provided
        hostnames = None
        if args.hostname:
            hostnames = [h.strip() for h in args.hostname.split(",") if h.strip()]
        
        success, failures = release_all_runners(
            repository,
            force=args.force,
            prefix=args.prefix,
            hostnames=hostnames,
        )
        if failures > 0:
            print("\nWARNING: Some runners failed to release!")
            sys.exit(1)
        print("\nAll matching runners released successfully.")
        return 0
    
    # Normal mode requires config
    if not args.config:
        print("ERROR: --config is required (unless using --release)")
        sys.exit(1)
    
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
        print(f"  - {req.label}: max={req.max_count} (tags: {req.maas_tags}, platform: {req.platform})")
        if req.description:
            print(f"    Description: {req.description}")
    
    # Calculate actions
    print("\n--- Checking Current State ---")
    try:
        actions = calculate_allocation_actions(requirements, repository)
    except ValueError as e:
        print(f"ERROR: Failed to check runners: {e}")
        sys.exit(1)
    except requests.exceptions.RequestException as e:
        print(f"ERROR: Network error while checking runners: {e}")
        sys.exit(1)
    
    # Execute actions
    print("\n--- Executing Actions ---")
    success, failures, pool_exhausted = execute_actions(actions, repository)
    
    # Summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    
    # Re-check current state to get accurate counts for summary
    total_runners_connected = 0
    total_runners_needed = 0
    requirements_at_target = 0
    requirements_partial = 0
    requirements_empty = 0
    
    print("\nRunner Status by Requirement:")
    for req in requirements:
        status = get_current_runners(repository, req.maas_tags, req.platform)
        total_runners_connected += status.connected_count
        total_runners_needed += req.max_count
        
        if status.connected_count >= req.max_count:
            requirements_at_target += 1
            icon = "[OK]"
        elif status.connected_count > 0:
            requirements_partial += 1
            icon = "[..]"
        else:
            requirements_empty += 1
            icon = "[  ]"
        
        print(f"  {icon} {req.label}/{req.platform}: {status.connected_count}/{req.max_count} runners")
    
    print()
    print(f"Total requirements: {len(requirements)}")
    print(f"  Fully satisfied: {requirements_at_target}")
    print(f"  Partially satisfied: {requirements_partial}")
    print(f"  No runners: {requirements_empty}")
    print()
    print(f"Total runners: {total_runners_connected}/{total_runners_needed}")
    print()
    print(f"This run:")
    print(f"  New runners allocated: {success}")
    print(f"  Pool exhausted: {pool_exhausted}")
    print(f"  Allocation errors: {failures}")
    
    if failures > 0:
        print("\nERROR: Some allocations failed!")
        sys.exit(1)
    
    # Determine the overall status message
    if requirements_at_target == len(requirements):
        print("\nOK: All requirements are fully satisfied.")
    elif pool_exhausted > 0 and success == 0:
        print("\nOK: Pool fully utilized - all available machines are registered as runners.")
    elif pool_exhausted > 0:
        print(f"\nOK: Allocated {success} new runner(s). Pool now exhausted.")
    elif success > 0:
        print(f"\nOK: Successfully allocated {success} new runner(s).")
    
    print("\nResource allocation check completed successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
