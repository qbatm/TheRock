import argparse
import json
import os
import smtplib
import sys
from datetime import datetime
from email.mime.text import MIMEText
import subprocess

def send_email(receiver_email, subject, body, sender_password=None, sender_email=None):
    smtp_server = "smtp.gmail.com"
    smtp_port = 587
    
    # Check for sender email
    if sender_email is None:
        print("Error: Sender email not provided. Use --sender-email argument.")
        sys.exit(1)
    
    # Get password from parameter, environment variable, or prompt user
    if sender_password is None:
        sender_password = os.getenv('GMAIL_PASSWORD')
        if sender_password is None:
            print("Error: Sender email password not provided. Use --sender-email-pass argument or GMAIL_PASSWORD environment variable.")
            sys.exit(1)

    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = sender_email
    msg['To'] = receiver_email

    try:
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, receiver_email, msg.as_string())
        print(f"Email sent successfully to {receiver_email} for platform: {subject.split('-')[-1]}")
    except Exception as e:
        print(f"Error sending email to {receiver_email}: {e}")
        return False
    finally:
        if 'server' in locals() and server:
            server.quit()
    return True

def send_pipeline_notification(receiver_email, status, workflow_url=None, failed_jobs=None, details=None, 
                               sender_password=None, sender_email=None, platform_config=None):
    """Send a pipeline completion notification email for a specific platform configuration."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
    status_emoji = "✅" if status == "success" else "❌" if status == "failure" else "⚠️"
    
    platform_name = platform_config.get('PLATFORM', 'Unknown')
    subject = f"{status_emoji} TheRock Pipeline {status.title()} - Libraries & PyTorch Wheels - {platform_name}"
    
    body_parts = [
        f"TheRock Pipeline Completion Notification",
        f"=" * 45,
        f"Status: {status.upper()}",
        f"Timestamp: {timestamp}",
        f"Pipeline: ROCm Libraries Build + PyTorch Wheel Creation",
        "",
    ]
    
    if workflow_url:
        body_parts.extend([
            f"Workflow Details: {workflow_url}",
            "",
        ])
    
    if failed_jobs and failed_jobs.strip():
        body_parts.extend([
            f"Failed Jobs: {failed_jobs}",
            "",
        ])
    
    if details:
        body_parts.extend([
            "Additional Details:",
            "-" * 20,
            details,
            "",
        ])

    body_parts.extend([
        "This pipeline includes:",
        "• ROCm libraries compilation and testing",
        "• PyTorch wheel building and validation",
        "• Cross-platform support (Linux & Windows)",
        "• Multiple GPU family targets (gfx94X, gfx110X, etc.)",
        "",
        "This notification was sent automatically by TheRock CI pipeline.",
        f"PLATFORM: {platform_config.get('PLATFORM', 'N/A')}",
        f"S3_BUCKET_URL: \"{platform_config.get('S3_BUCKET_URL', 'N/A')}\"",
        f"THEROCK_SDK_URL: {platform_config.get('THEROCK_SDK_URL', 'N/A')}",
        f"gpuArchPattern: {platform_config.get('gpuArchPattern', 'N/A')}",
        f"THEROCK_WHL_URL: {platform_config.get('THEROCK_WHL_URL', 'N/A')}"
    ])
    
    body = "\n".join(body_parts)
    return send_email(receiver_email, subject, body, sender_password, sender_email)

def send_multiple_notifications(receiver_email, status, workflow_url=None, failed_jobs=None, details=None,
                                sender_password=None, sender_email=None, platform_configs=None):
    """Send pipeline notifications for multiple platform configurations."""
    if not platform_configs:
        print("Error: No platform configurations provided")
        sys.exit(1)
    
    success_count = 0
    failed_count = 0
    
    print(f"\nSending {len(platform_configs)} email(s)...")
    print("=" * 50)
    
    for i, (platform_key, platform_config) in enumerate(platform_configs.items(), 1):
        print(f"\n[{i}/{len(platform_configs)}] Processing platform: {platform_config.get('PLATFORM', platform_key)}")
        
        success = send_pipeline_notification(
            receiver_email=receiver_email,
            status=status,
            workflow_url=workflow_url,
            failed_jobs=failed_jobs,
            details=details,
            sender_password=sender_password,
            sender_email=sender_email,
            platform_config=platform_config
        )
        
        if success:
            success_count += 1
        else:
            failed_count += 1
    
    print("\n" + "=" * 50)
    print(f"Email sending completed: {success_count} succeeded, {failed_count} failed")
    
    if failed_count > 0:
        sys.exit(1)

def run_command_with_logging(cmd: str, timeout: int = None) -> subprocess.CompletedProcess:
    """
    Execute a command with comprehensive logging.
    
    Args:
        cmd: Command as a string
        timeout: Maximum time in seconds to wait for command completion (None for no timeout)

    Returns:
        subprocess.CompletedProcess: The complete result object with returncode, stdout, stderr
    """
    try:
        print(f"Running command: {cmd}")
        if timeout:
            print(f"Timeout: {timeout} seconds")
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)

        # Log all output regardless of return code
        print(f"Command exit code: {result.returncode}")

        if result.stdout:
            print("STDOUT:")
            print(result.stdout)

        if result.stderr:
            print("STDERR:")
            print(result.stderr)

        # Check exit code and log result
        if result.returncode != 0:
            print(f"ERROR: Command failed with exit code {result.returncode}")
        else:
            print("✓ Command executed successfully")

        return result

    except subprocess.TimeoutExpired as e:
        print(f"ERROR: Command timed out after {timeout} seconds")

        # Return a mock result object with error code
        class MockResult:
            def __init__(self):
                self.returncode = 124  # Standard timeout exit code
                self.stdout = ""
                self.stderr = f"Command timed out after {timeout} seconds"

        return MockResult()

    except Exception as e:
        print(f"ERROR: Failed to execute command {cmd}: {e}")

        # Return a mock result object with error code
        class MockResult:
            def __init__(self):
                self.returncode = 1
                self.stdout = ""
                self.stderr = str(e)

        return MockResult()

def get_latest_s3_tarball(s3_bucket_url: str, gpu_arch_pattern: str) -> str:
    """
    Get the latest tar.gz file path from S3 bucket matching the GPU architecture pattern.
    Args:
        s3_bucket_url: The S3 bucket URL (e.g., "https://therock-nightly-tarball.s3.amazonaws.com/")
        gpu_arch_pattern: The GPU architecture pattern to match (e.g., "linux-gfx120X")
    Returns:
        str: The full URL to the latest tar.gz file, or empty string if not found or error
    """
    if not s3_bucket_url or not gpu_arch_pattern:
        print("ERROR: Both s3_bucket_url and gpu_arch_pattern are required")
        return ""

    print("GPU patter before removing suffix: ", gpu_arch_pattern)
    gpu_arch_pattern = gpu_arch_pattern.split("_")[0]  # Use only the part before underscore
    print("GPU pattern after removing suffix: ", gpu_arch_pattern)

    print(f"Searching for latest tarball in {s3_bucket_url} matching pattern {gpu_arch_pattern}")

    # Build the command to get the latest tarball matching the pattern
    # Extract date suffix (YYYYMMDD) from filenames and sort numerically to get the latest build
    # Date format in filenames: 7.10.0a20251113 or 7.9.0rc20251008 (8 digits at the end before .tar.gz)
    # We extract just the date part, sort numerically, then get the corresponding full filename
    cmd = f'/bin/bash -c \'curl -s "{s3_bucket_url}" | grep -oP "(?<=<Key>)[^<]*{gpu_arch_pattern}[^<]*\\.tar\\.gz(?=</Key>)" | grep -v "ADHOCBUILD" | awk -F"[.tar.gz]" "{{match(\\$0, /[0-9]{{8}}/); print substr(\\$0, RSTART, 8), \\$0}}" | sort -k1 -n | tail -1 | cut -d" " -f2\''

    result = run_command_with_logging(cmd)

    if result.returncode != 0:
        print("ERROR: Failed to get S3 bucket listing")
        return ""

    # Get the filename from stdout
    latest_filename = result.stdout.strip()

    if not latest_filename:
        print(f"ERROR: No tar.gz file found matching pattern '{gpu_arch_pattern}'")
        return ""

    # Construct the full URL
    # Ensure s3_bucket_url ends with / and filename doesn't start with /
    base_url = s3_bucket_url.rstrip("/")
    filename = latest_filename.lstrip("/")
    full_url = f"{base_url}/{filename}"

    print(f"Latest tarball found: {latest_filename}")
    print(f"Full URL: {full_url}")

    return full_url

def main():
    parser = argparse.ArgumentParser(description="Send TheRock pipeline completion notifications for multiple platforms")
    parser.add_argument("--receiver", required=True, help="Receiver email address")
    parser.add_argument("--status", required=True, choices=["success", "failure", "warning"], 
                       help="Pipeline status")
    parser.add_argument("--workflow-url", help="URL to the GitHub workflow run")
    parser.add_argument("--failed-jobs", help="Comma-separated list of failed jobs")
    parser.add_argument("--details", help="Additional details about the pipeline")
    
    # Email configuration
    parser.add_argument("--sender-email-pass", help="Sender email app password for authentication")
    parser.add_argument("--sender-email", required=True, 
                       help="Sender email address")
    
    # Platform configurations
    parser.add_argument("--platforms-json", help="JSON string or file path containing platform configurations")
    parser.add_argument("--platforms-file", help="Path to JSON file containing platform configurations")
    
    args = parser.parse_args()
    
    # Load platform configurations
    platform_configs = None
    
    if args.platforms_file:
        # Load from file
        try:
            with open(args.platforms_file, 'r') as f:
                platform_configs = json.load(f)
        except Exception as e:
            print(f"Error loading platforms file: {e}")
            sys.exit(1)
    elif args.platforms_json:
        # Try to parse as JSON string or load from file
        try:
            platform_configs = json.loads(args.platforms_json)
        except json.JSONDecodeError:
            # Maybe it's a file path
            try:
                with open(args.platforms_json, 'r') as f:
                    platform_configs = json.load(f)
            except Exception as e:
                print(f"Error parsing platforms JSON: {e}")
                sys.exit(1)
    else:
        # Use default configurations
        s3_bucket_url = "https://therock-nightly-tarball.s3.amazonaws.com/"

        linux_arch_night = "linux-gfx110X-dgpu"
        latest_linux_sdk_url = get_latest_s3_tarball(s3_bucket_url, linux_arch_night)
        print(f"Latest Linux SDK URL: {latest_linux_sdk_url}")

        windows_arch_night = "windows-gfx110X-all"
        latest_windows_sdk_url = get_latest_s3_tarball(s3_bucket_url, windows_arch_night)
        print(f"Latest Windows SDK URL: {latest_windows_sdk_url}")

        platform_configs = {
            # "linux-gfx110X-dgpu": {
            #     "PLATFORM": "Ubuntu",
            #     "S3_BUCKET_URL": "https://therock-nightly-tarball.s3.amazonaws.com/",
            #     "gpuArchPattern": "linux-gfx110X-dgpu", # tag gpu_navi31xtw 
            #     "THEROCK_WHL_URL": "https://rocm.nightlies.amd.com/v2/gfx110X-dgpu/"
            # },
            "linux-gfx110X-dgpu-navi44xt": {
                "PLATFORM": "Ubuntu",
                "S3_BUCKET_URL": "https://therock-nightly-tarball.s3.amazonaws.com/",
                "THEROCK_SDK_URL": latest_linux_sdk_url,
                "gpuArchPattern": "linux-gfx110X-dgpu_navi44xt", # gpu_navi44xt
                "THEROCK_WHL_URL": "https://rocm.nightlies.amd.com/v2/gfx110X-dgpu/"
            },
            "windows-gfx110X-dgpu-1": {
                "PLATFORM": "Windows",
                "THEROCK_SDK_URL": latest_windows_sdk_url,
                "S3_BUCKET_URL": "https://therock-nightly-tarball.s3.amazonaws.com/",
                "gpuArchPattern": "windows-gfx110X-dgpu", # gpu_navi31xtx
                "THEROCK_WHL_URL": "https://rocm.nightlies.amd.com/v2/gfx110X-dgpu/"
            },
            "windows-gfx110X-dgpu-2": {
                "PLATFORM": "Windows",
                "THEROCK_SDK_URL": latest_windows_sdk_url,
                "S3_BUCKET_URL": "https://therock-nightly-tarball.s3.amazonaws.com/",
                "gpuArchPattern": "windows-gfx110X-dgpu", # gpu_navi31xtx
                "THEROCK_WHL_URL": "https://rocm.nightlies.amd.com/v2/gfx110X-dgpu/"
            },
            "windows-gfx110X-dgpu-navi44xt-1": {
                "PLATFORM": "Windows",
                "THEROCK_SDK_URL": latest_windows_sdk_url,
                "S3_BUCKET_URL": "https://therock-nightly-tarball.s3.amazonaws.com/",
                "gpuArchPattern": "windows-gfx110X-dgpu_navi44xt", # gpu_navi44xt
                "THEROCK_WHL_URL": "https://rocm.nightlies.amd.com/v2/gfx110X-dgpu/"
            },
            "windows-gfx110X-dgpu-navi44xt-2": {
                "PLATFORM": "Windows",
                "THEROCK_SDK_URL": latest_windows_sdk_url,
                "S3_BUCKET_URL": "https://therock-nightly-tarball.s3.amazonaws.com/",
                "gpuArchPattern": "windows-gfx110X-dgpu_navi44xt", # gpu_navi44xt
                "THEROCK_WHL_URL": "https://rocm.nightlies.amd.com/v2/gfx110X-dgpu/"
            },
            "windows-gfx110X-dgpu-navi44xt-3": {
                "PLATFORM": "Windows",
                "THEROCK_SDK_URL": latest_windows_sdk_url,
                "S3_BUCKET_URL": "https://therock-nightly-tarball.s3.amazonaws.com/",
                "gpuArchPattern": "windows-gfx110X-dgpu_navi44xt", # gpu_navi44xt
                "THEROCK_WHL_URL": "https://rocm.nightlies.amd.com/v2/gfx110X-dgpu/"
            },
            "windows-gfx110X-dgpu-navi48xtx-1": {
                "PLATFORM": "Windows",
                "THEROCK_SDK_URL": latest_windows_sdk_url,
                "S3_BUCKET_URL": "https://therock-nightly-tarball.s3.amazonaws.com/",
                "gpuArchPattern": "windows-gfx110X-dgpu_navi48xtx", # gpu_navi48xtx
                "THEROCK_WHL_URL": "https://rocm.nightlies.amd.com/v2/gfx110X-dgpu/"
            },
            "linux-gfx110X-dgpu-navi48xtx-1": {
                "PLATFORM": "Ubuntu",
                "S3_BUCKET_URL": "https://therock-nightly-tarball.s3.amazonaws.com/",
                "THEROCK_SDK_URL": latest_linux_sdk_url,
                "gpuArchPattern": "linux-gfx110X-dgpu_navi48xtx", # gpu_navi48xtx
                "THEROCK_WHL_URL": "https://rocm.nightlies.amd.com/v2/gfx110X-dgpu/"
            },
            "linux-gfx110X-dgpu-navi44xt-1": {
                "PLATFORM": "Ubuntu",
                "S3_BUCKET_URL": "https://therock-nightly-tarball.s3.amazonaws.com/",
                "THEROCK_SDK_URL": latest_linux_sdk_url,
                "gpuArchPattern": "linux-gfx110X-dgpu_navi44xt", # gpu_navi44xt
                "THEROCK_WHL_URL": "https://rocm.nightlies.amd.com/v2/gfx110X-dgpu/"
            },
        }
        print("No platform configurations provided. Using default configurations (10 platforms).")
    
    # Send notifications
    send_multiple_notifications(
        receiver_email=args.receiver,
        status=args.status,
        workflow_url=args.workflow_url,
        failed_jobs=args.failed_jobs,
        details=args.details,
        sender_password=args.sender_email_pass,
        sender_email=args.sender_email,
        platform_configs=platform_configs
    )

# Example usage:
if __name__ == "__main__":
    if len(sys.argv) > 1:
        main()
    else:
        print("Usage: python sent_email_multi.py --receiver EMAIL --status STATUS --sender-email EMAIL [options]")
        print("\nPlatform Configuration Options:")
        print("  --platforms-json    JSON string or file path with platform configs")
        print("  --platforms-file    Path to JSON file with platform configs")
        print("\nExample JSON format:")
        print("""{
  "linux": {
    "PLATFORM": "Linux",
    "S3_BUCKET_URL": "https://therock-nightly-tarball.s3.amazonaws.com/",
    "gpuArchPattern": "linux-gfx110X-dgpu",
    "THEROCK_WHL_URL": "https://rocm.nightlies.amd.com/v2/gfx110X-dgpu/"
  },
  "windows": {
    "PLATFORM": "Windows",
    "S3_BUCKET_URL": "https://therock-nightly-tarball.s3.amazonaws.com/",
    "gpuArchPattern": "windows-gfx110X-dgpu",
    "THEROCK_WHL_URL": "https://rocm.nightlies.amd.com/v2/gfx110X-dgpu/"
  }
}""")
        print("\nUse --help for more information.")
        sys.exit(1)
