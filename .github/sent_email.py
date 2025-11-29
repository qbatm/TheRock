import argparse
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
        print(f"Email sent successfully to {receiver_email}")
    except Exception as e:
        print(f"Error sending email to {receiver_email}: {e}")
        return False
    finally:
        if 'server' in locals() and server:
            server.quit()
    return True

def send_pipeline_notification(receiver_email, status, workflow_url=None, failed_jobs=None, details=None, sender_password=None, sender_email=None, platform=None, commit_id=None):
    """Send a pipeline completion notification email."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
    status_emoji = "✅" if status == "success" else "❌" if status == "failure" else "⚠️"
    
    subject = f"{status_emoji} TheRock Pipeline {status.title()} - Libraries & PyTorch Wheels - {platform}"
    
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

    # if platform.lower() == "linux":
    #     body_parts.extend([
    #         "This pipeline includes:",
    #         "• ROCm libraries compilation and testing",
    #         "• PyTorch wheel building and validation",
    #         "• Cross-platform support (Linux & Windows)",
    #         "• Multiple GPU family targets (gfx94X, gfx110X, etc.)",
    #         "",
    #         "This notification was sent automatically by TheRock CI pipeline.",
    #         "PLATFORM: Linux",
    #         "S3_BUCKET_URL: \"https://therock-nightly-tarball.s3.amazonaws.com/\"",
    #         "gpuArchPattern: linux-gfx120X",
    #         "THEROCK_WHL_URL: https://d2awnip2yjpvqn.cloudfront.net/v2/gfx120X-all/"
    #     ])
    if platform.lower() == "linux":
        body_parts.extend([
            "This pipeline includes:",
            "• ROCm libraries compilation and testing",
            "• PyTorch wheel building and validation",
            "• Cross-platform support (Linux & Windows)",
            "• Multiple GPU family targets (gfx94X, gfx110X, etc.)",
            "",
            "This notification was sent automatically by TheRock CI pipeline.",
            "PLATFORM: Ubuntu",
            "S3_BUCKET_URL: \"https://therock-nightly-tarball.s3.amazonaws.com/\"",
            "THEROCK_SDK_URL: \"https://therock-nightly-tarball.s3.amazonaws.com/therock-dist-linux-gfx110X-dgpu-7.10.0a20251119.tar.gz\"",
            "gpuArchPattern:  linux-gfx110X-dgpu_navi44xt",
            "THEROCK_WHL_URL: https://rocm.nightlies.amd.com/v2/gfx110X-dgpu/",
            f"GH_COMMIT_ID: {commit_id if commit_id else 'N/A'}"
        ])
    if platform.lower() == "windows":
        body_parts.extend([
            "This pipeline includes:",
            "• ROCm libraries compilation and testing",
            "• PyTorch wheel building and validation",
            "• Cross-platform support (Linux & Windows)",
            "• Multiple GPU family targets (gfx94X, gfx110X, etc.)",
            "",
            "This notification was sent automatically by TheRock CI pipeline.",
            "PLATFORM: Windows",
            "S3_BUCKET_URL: \"https://therock-nightly-tarball.s3.amazonaws.com/\"",
            "THEROCK_SDK_URL: \"https://therock-nightly-tarball.s3.amazonaws.com/therock-dist-windows-gfx110X-dgpu-7.0.0rc20250627.tar.gz\"",
            "gpuArchPattern: windows-gfx110X-dgpu_navi48xtx",
            "THEROCK_WHL_URL: https://rocm.nightlies.amd.com/v2/gfx110X-dgpu/",
            f"GH_COMMIT_ID: {commit_id if commit_id else 'N/A'}"
    
    body = "\n".join(body_parts)
    return send_email(receiver_email, subject, body, sender_password, sender_email)

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

    if args.subject and args.body:
        # Legacy mode
        success = send_email(args.receiver, args.subject, args.body, args.sender_email_pass, args.sender_email)
        if not success:
            sys.exit(1)
    else:
        # Pipeline notification mode
        success = send_pipeline_notification(
            receiver_email=args.receiver,
            status=args.status,
            workflow_url=args.workflow_url,
            failed_jobs=args.failed_jobs,
            details=args.details,
            sender_password=args.sender_email_pass,
            sender_email=args.sender_email,
            platform=args.platform,
            commit_id=args.commit_id
        )
        if not success:
            sys.exit(1) Return a mock result object with error code
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
def main():
    parser = argparse.ArgumentParser(description="Send TheRock pipeline completion notifications")
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
    parser.add_argument("--platform", default="linux", 
                       help="Chose platform: windows or linux.")
    parser.add_argument("--commit-id", help="GitHub commit SHA")
    
    # Legacy support
    parser.add_argument("--subject", help="Email subject (legacy mode)")
    parser.add_argument("--body", help="Email body (legacy mode)")
    
    args = parser.parse_args()
    
    if args.subject and args.body:
        # Legacy mode
        send_email(args.receiver, args.subject, args.body, args.sender_email_pass, args.sender_email)
    else:
        # Pipeline notification mode
        send_pipeline_notification(
            receiver_email=args.receiver,
            status=args.status,
            workflow_url=args.workflow_url,
            failed_jobs=args.failed_jobs,
            details=args.details,
            sender_password=args.sender_email_pass,
            sender_email=args.sender_email,
            platform=args.platform,
            commit_id=args.commit_id
        )

# Example usage:
if __name__ == "__main__":
    if len(sys.argv) > 1:
        main()
    else:
        print("Usage: python sent_email.py --receiver EMAIL --status STATUS --sender-email EMAIL [options]")
        print("Use --help for more information.")
        sys.exit(1)




