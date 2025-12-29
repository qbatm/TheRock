#!/usr/bin/env python3
"""
Trigger Jenkins ucicd-production-v1 job directly from GitHub Actions.

This script consolidates the functionality previously split between:
- sent_email.py (constructing parameters and sending emails)
- trigger_pipeline_based_on_email_inbox.py (parsing emails and triggering Jenkins)

Now we skip the email step entirely and trigger Jenkins directly with the proper parameters.
"""

import argparse
import copy
import json
import os
import platform
import subprocess
import sys
import time
from typing import Optional

# Try to import requests, but make it optional for parameter generation
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False


# GPU architecture pattern to Jenkins GPU tag mapping
# This maps TheRock build architecture patterns to Jenkins agent GPU patterns
GPU_MAPPING = {
    "gfx120X-all": [
        "gpu_navi4x",
        # "gpu_navi48xt",       # AMD Radeon RX 9070 - gfx1201
        # "gpu_navi48xtx",    # AMD Radeon RX 9070 XT - gfx1201
        # "gpu_navi44xl",     # AMD Radeon RX 9060 - gfx1200
        # "gpu_navi44xt"      # AMD Radeon RX 9060 XT - gfx1200
    ],
    "gfx110X-all": [
        "gpu_navi3x",
    ],
    "gfx1151": [
        "igpu_stxh",
    ]
    # Uncomment and expand as needed:
    # "gfx110X-dgpu": [
    #     "gpu_navi31xtx",    # AMD Radeon RX 7900 XTX - gfx1100
    #     "gpu_navi31xt",     # AMD Radeon RX 7900 XT - gfx1100
    #     "gpu_navi32xtx",    # AMD Radeon RX 7800 XT - gfx1101
    #     "gpu_navi32xl",     # AMD Radeon RX 7700 XT - gfx1101
    # ],
}

# S3 bucket URLs for different platforms
S3_BUCKETS = {
    "linux": "https://therock-nightly-tarball.s3.amazonaws.com/",
    "windows": "https://rocm.nightlies.amd.com/tarball/",
}

# Jenkins configuration
JENKINS_URL = "https://ucicd-jenkins.amd.com"
# JENKINS_JOB = "ucicd-production-v1"
JENKINS_JOB = "DevOps/nm/ucicd-production-v1"
DEFAULT_POOL_TYPE = "default_hot"


def run_command(cmd: str, timeout: int = 60) -> subprocess.CompletedProcess:
    """Execute a command and return the result."""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        return result
    except subprocess.TimeoutExpired:
        class MockResult:
            returncode = 124
            stdout = ""
            stderr = f"Command timed out after {timeout} seconds"
        return MockResult()
    except Exception as e:
        class MockResult:
            returncode = 1
            stdout = ""
            stderr = str(e)
        return MockResult()


def get_latest_s3_tarball(s3_bucket_url: str, arch_pattern: str) -> str:
    """
    Get the latest tar.gz file URL from S3 bucket matching the architecture pattern.

    Args:
        s3_bucket_url: The S3 bucket URL
        arch_pattern: The GPU architecture pattern to match (e.g., "linux-gfx120X-all")

    Returns:
        str: The full URL to the latest tar.gz file, or empty string if not found
    """
    if not s3_bucket_url or not arch_pattern:
        print("ERROR: Both s3_bucket_url and arch_pattern are required", file=sys.stderr)
        return ""

    # Use only the part before underscore for matching
    arch_pattern_base = arch_pattern.split("_")[0]

    # Add therock-dist- prefix only for rocm.nightlies.amd.com bucket
    if "rocm.nightlies.amd.com" in s3_bucket_url:
        search_pattern = f"therock-dist-{arch_pattern_base}"
    else:
        search_pattern = arch_pattern_base

    print(f"Searching for latest tarball in {s3_bucket_url} matching pattern {search_pattern}")

    # Build the command to get the latest tarball matching the pattern
    if platform.system().lower() == "windows":
        escaped_pattern = search_pattern.replace("[", "`[").replace("]", "`]")
        cmd = f'powershell -Command "$content = (Invoke-WebRequest -Uri \'{s3_bucket_url}\' -UseBasicParsing).Content; $content | Select-String -Pattern \'<Key>([^<]*{escaped_pattern}[^<]*\\.tar\\.gz)</Key>\' -AllMatches | ForEach-Object {{$_.Matches.Groups[1].Value}} | Where-Object {{$_ -notmatch \'ADHOCBUILD\'}} | Sort-Object {{[regex]::Match($_, \'[0-9]{{8}}\').Value}} | Select-Object -Last 1"'
    else:
        cmd = f'curl -s "{s3_bucket_url}" | grep -oP \'(?<=<Key>)[^<]*{search_pattern}[^<]*\\.tar\\.gz(?=</Key>)|(?<="name": ")[^"]*{search_pattern}[^"]*\\.tar\\.gz(?=")\' | grep -v "ADHOCBUILD" | awk \'{{match($0, /[0-9]{{8}}/); print substr($0, RSTART, 8), $0}}\' | sort -k1 -n | tail -1 | cut -d" " -f2'

    result = run_command(cmd)

    if result.returncode != 0:
        print(f"ERROR: Failed to get S3 bucket listing: {result.stderr}", file=sys.stderr)
        return ""

    latest_filename = result.stdout.strip()

    if not latest_filename:
        print(f"ERROR: No tar.gz file found matching pattern '{search_pattern}'", file=sys.stderr)
        return ""

    # Construct the full URL
    base_url = s3_bucket_url.rstrip("/")
    filename = latest_filename.lstrip("/")
    full_url = f"{base_url}/{filename}"

    print(f"Latest tarball found: {full_url}")
    return full_url


def build_builds_json(
    platform_name: str,
    gpu_arch_pattern: str,
    therock_sdk_url: str,
    commit_id: str,
    pool_type: str = DEFAULT_POOL_TYPE,
    run_id: str = None,
    amdgpu_family: str = None
) -> str:
    """
    Build the BUILDS_JSON parameter for the Jenkins job.

    Args:
        platform_name: "ubuntu" or "windows"
        gpu_arch_pattern: Jenkins GPU pattern (e.g., "gpu_navi48xt")
        therock_sdk_url: URL to the SDK tarball (for nightly builds)
        commit_id: GitHub commit SHA
        pool_type: Jenkins agent pool type
        run_id: GitHub Actions workflow run ID (for bump PRs)
        amdgpu_family: AMDGPU family for install_rocm_from_artifacts.py (e.g., "gfx120X-all")

    Returns:
        str: JSON string for BUILDS_JSON parameter
    """
    payload = {
        "use_case": {
            "the_rock": {
                "platform": platform_name.lower(),
                "gpu_arch_pattern": gpu_arch_pattern,
                "therock_sdk_url": therock_sdk_url or "",
                "pool_type": pool_type,
                "gh_commit_id": commit_id,
                "run_id": run_id or ""
            }
        }
    }
    # Add amdgpu_family if provided
    if amdgpu_family:
        payload["use_case"]["the_rock"]["amdgpu_family"] = amdgpu_family
        # Add therock_requirements_txt based on amdgpu_family
        payload["use_case"]["the_rock"]["therock_requirements_txt"] = (
            f"--index-url https://rocm.nightlies.amd.com/v2/{amdgpu_family}/ "
            f"rocm[libraries,devel] torch torchvision torchaudio"
        )
    return json.dumps(payload)


def generate_trigger_configs(
    platform_name: str,
    commit_id: str,
    gpu_mapping: dict = None,
    pool_type: str = DEFAULT_POOL_TYPE,
    sdk_url_override: str = None,
    run_id: str = None
) -> list:
    """
    Generate all Jenkins trigger configurations for a given platform.

    This mimics the behavior of sent_email.py which sends one email per GPU tag,
    allowing Jenkins to run tests on each GPU type.

    For bump PRs (run_id provided), the SDK URL is left empty and Jenkins will use
    install_rocm_from_artifacts.py to consolidate the artifacts.

    For nightly builds (sdk_url provided), the tarball URL is passed directly.

    Args:
        platform_name: "linux" or "windows"
        commit_id: GitHub commit SHA
        gpu_mapping: Optional custom GPU mapping (defaults to GPU_MAPPING)
        pool_type: Jenkins agent pool type
        sdk_url_override: Optional SDK URL override (skips S3 lookup)
        run_id: GitHub Actions workflow run ID (for bump PRs)

    Returns:
        list: List of dicts with 'builds_json' and metadata for each trigger
    """
    if gpu_mapping is None:
        gpu_mapping = GPU_MAPPING

    # For bump PRs with run_id, we don't need S3 lookup
    is_bump_pr = bool(run_id)

    s3_bucket_url = S3_BUCKETS.get(platform_name.lower())
    if not s3_bucket_url and not is_bump_pr:
        print(f"ERROR: Unknown platform '{platform_name}'", file=sys.stderr)
        return []

    # Map platform name to Jenkins platform value
    jenkins_platform = "ubuntu" if platform_name.lower() == "linux" else platform_name.lower()

    configs = []

    for arch_pattern, gpu_list in gpu_mapping.items():
        # Build the full architecture pattern with platform prefix
        full_arch_pattern = f"{platform_name.lower()}-{arch_pattern}"

        # For bump PRs, SDK URL is empty (Jenkins will use install_rocm_from_artifacts.py)
        if is_bump_pr:
            sdk_url = ""
        elif sdk_url_override:
            sdk_url = sdk_url_override
        else:
            sdk_url = get_latest_s3_tarball(s3_bucket_url, full_arch_pattern)

        if not sdk_url and not is_bump_pr:
            print(f"WARNING: No SDK tarball found for {full_arch_pattern}, skipping", file=sys.stderr)
            continue

        if not gpu_list:
            print(f"WARNING: No GPUs defined for architecture pattern '{arch_pattern}'", file=sys.stderr)
            continue

        # Generate a config for each GPU in the list
        for gpu_tag in gpu_list:
            builds_json = build_builds_json(
                platform_name=jenkins_platform,
                gpu_arch_pattern=gpu_tag,
                therock_sdk_url=sdk_url,
                commit_id=commit_id,
                pool_type=pool_type,
                run_id=run_id,
                amdgpu_family=arch_pattern
            )

            configs.append({
                "builds_json": builds_json,
                "arch_pattern": arch_pattern,
                "gpu_tag": gpu_tag,
                "sdk_url": sdk_url,
                "run_id": run_id or "",
                "platform": jenkins_platform
            })

            if is_bump_pr:
                print(f"Generated config for {gpu_tag} on {jenkins_platform} (bump PR run_id: {run_id})")
            else:
                print(f"Generated config for {gpu_tag} on {jenkins_platform}")

    return configs


def trigger_jenkins_job(
    builds_json: str,
    jenkins_user: str,
    jenkins_token: str,
    jenkins_url: str = JENKINS_URL,
    jenkins_job: str = JENKINS_JOB
) -> dict:
    """
    Trigger a Jenkins job with the given BUILDS_JSON parameter.

    Args:
        builds_json: The BUILDS_JSON parameter value
        jenkins_user: Jenkins username
        jenkins_token: Jenkins API token
        jenkins_url: Jenkins server URL
        jenkins_job: Jenkins job name

    Returns:
        dict: Result with 'success', 'queue_url', 'build_number', 'error' keys
    """
    if not REQUESTS_AVAILABLE:
        return {
            "success": False,
            "error": "requests library not available",
            "queue_url": None,
            "build_number": None
        }

    session = requests.Session()
    session.auth = (jenkins_user, jenkins_token)
    session.verify = True

    result = {
        "success": False,
        "queue_url": None,
        "build_number": None,
        "error": None
    }

    try:
        # Get crumb for CSRF protection
        crumb_url = f"{jenkins_url}/crumbIssuer/api/json"
        crumb = {}
        r = session.get(crumb_url)
        if r.ok:
            j = r.json()
            crumb = {j['crumbRequestField']: j['crumb']}

        # Trigger the build
        trigger_url = f"{jenkins_url}/job/{jenkins_job}/buildWithParameters"
        params = {"BUILDS_JSON": builds_json}

        r = session.post(trigger_url, headers=crumb, data=params)

        if r.status_code not in (201, 302):
            result["error"] = f"Trigger failed: {r.status_code} {r.text}"
            return result

        queue_url = r.headers.get("Location")
        result["queue_url"] = queue_url
        print(f"Enqueued at: {queue_url}")

        # Poll queue to get build number
        if queue_url:
            api_queue_url = queue_url if queue_url.endswith('/api/json') else queue_url + "api/json"
            for _ in range(60):
                q = session.get(api_queue_url, headers=crumb).json()
                if q.get("executable"):
                    build_number = q["executable"]["number"]
                    result["build_number"] = build_number
                    result["success"] = True
                    print(f"Build assigned: {build_number}")
                    print(f"Console URL: {jenkins_url}/job/{jenkins_job}/{build_number}/console")
                    break
                time.sleep(2)
            else:
                result["error"] = "Timed out waiting for build assignment"

    except Exception as e:
        result["error"] = str(e)

    return result


def output_for_github_actions(configs: list, output_file: str = None):
    """
    Output the trigger configurations in a format suitable for GitHub Actions.

    Args:
        configs: List of trigger configurations
        output_file: Optional path to GITHUB_OUTPUT file
    """
    # Output as JSON array for matrix strategy or sequential processing
    configs_json = json.dumps(configs)

    if output_file:
        with open(output_file, "a") as f:
            f.write(f"trigger_configs={configs_json}\n")
            f.write(f"trigger_count={len(configs)}\n")

    # Also print to stdout for debugging
    print(f"\n{'=' * 60}")
    print(f"Generated {len(configs)} trigger configuration(s)")
    print(f"{'=' * 60}")

    for i, config in enumerate(configs, 1):
        print(f"\n[{i}] {config['gpu_tag']} ({config['platform']})")
        if config.get('run_id'):
            print(f"    Run ID: {config['run_id']}")
        if config.get('sdk_url'):
            print(f"    SDK URL: {config['sdk_url']}")
        print(f"    BUILDS_JSON: {config['builds_json']}")

    return configs_json


def main():
    parser = argparse.ArgumentParser(
        description="Generate Jenkins trigger parameters or trigger Jenkins directly"
    )

    # Mode selection
    parser.add_argument(
        "--mode",
        choices=["generate", "trigger"],
        default="generate",
        help="Mode: 'generate' outputs parameters, 'trigger' calls Jenkins API"
    )

    # Required parameters
    parser.add_argument(
        "--platform",
        required=True,
        choices=["linux", "windows"],
        help="Target platform"
    )
    parser.add_argument(
        "--commit-id",
        default="",
        help="GitHub commit SHA (optional for bump PRs with run_id)"
    )

    # Optional parameters
    parser.add_argument(
        "--pool-type",
        default=DEFAULT_POOL_TYPE,
        help=f"Jenkins agent pool type (default: {DEFAULT_POOL_TYPE})"
    )
    parser.add_argument(
        "--sdk-url",
        help="Override SDK URL (skips S3 lookup, for nightly builds)"
    )
    parser.add_argument(
        "--run-id",
        help="GitHub Actions workflow run ID (for bump PRs, uses install_rocm_from_artifacts.py)"
    )
    parser.add_argument(
        "--gpu-mapping-json",
        help="Custom GPU mapping as JSON string"
    )

    # Jenkins credentials (only needed for trigger mode)
    parser.add_argument(
        "--jenkins-user",
        help="Jenkins username (required for trigger mode)"
    )
    parser.add_argument(
        "--jenkins-token",
        help="Jenkins API token (required for trigger mode)"
    )
    parser.add_argument(
        "--jenkins-url",
        default=JENKINS_URL,
        help=f"Jenkins server URL (default: {JENKINS_URL})"
    )
    parser.add_argument(
        "--jenkins-job",
        default=JENKINS_JOB,
        help=f"Jenkins job name (default: {JENKINS_JOB})"
    )

    # Output options
    parser.add_argument(
        "--github-output",
        help="Path to GITHUB_OUTPUT file for GitHub Actions"
    )
    parser.add_argument(
        "--output-json",
        action="store_true",
        help="Output only JSON (for piping)"
    )

    args = parser.parse_args()

    # Parse custom GPU mapping if provided
    gpu_mapping = None
    if args.gpu_mapping_json:
        try:
            gpu_mapping = json.loads(args.gpu_mapping_json)
        except json.JSONDecodeError as e:
            print(f"ERROR: Invalid GPU mapping JSON: {e}", file=sys.stderr)
            sys.exit(1)

    # Generate trigger configurations
    configs = generate_trigger_configs(
        platform_name=args.platform,
        commit_id=args.commit_id,
        gpu_mapping=gpu_mapping,
        pool_type=args.pool_type,
        sdk_url_override=args.sdk_url,
        run_id=args.run_id
    )

    if not configs:
        print("ERROR: No trigger configurations generated", file=sys.stderr)
        sys.exit(1)

    if args.mode == "generate":
        # Output configurations for GitHub Actions to use
        configs_json = output_for_github_actions(configs, args.github_output)

        if args.output_json:
            print(configs_json)

    elif args.mode == "trigger":
        # Validate credentials
        if not args.jenkins_user or not args.jenkins_token:
            print("ERROR: --jenkins-user and --jenkins-token required for trigger mode", file=sys.stderr)
            sys.exit(1)

        if not REQUESTS_AVAILABLE:
            print("ERROR: 'requests' library required for trigger mode. Install with: pip install requests", file=sys.stderr)
            sys.exit(1)

        # Trigger Jenkins for each configuration
        results = []
        for config in configs:
            print(f"\nTriggering Jenkins for {config['gpu_tag']}...")
            result = trigger_jenkins_job(
                builds_json=config["builds_json"],
                jenkins_user=args.jenkins_user,
                jenkins_token=args.jenkins_token,
                jenkins_url=args.jenkins_url,
                jenkins_job=args.jenkins_job
            )
            result["config"] = config
            results.append(result)

        # Summary
        successful = sum(1 for r in results if r["success"])
        print(f"\n{'=' * 60}")
        print(f"Triggered {successful}/{len(results)} Jenkins jobs successfully")

        if successful < len(results):
            sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
