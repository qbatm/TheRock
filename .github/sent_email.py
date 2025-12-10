import argparse
import os
import smtplib
import sys
from datetime import datetime
from email.mime.text import MIMEText
import subprocess
import platform

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


    gpu_mapping = {
        # "gfx110X-all": [
        #     "gpu_navi31xtx",      # AMD Radeon RX 7900 XTX - gfx1100
        #     "gpu_navi31xt",       # AMD Radeon RX 7900 XT - gfx1100
        #                 # "gpu_navi31xl",       # AMD Radeon RX 7900 GRE - gfx1100
        #     "gpu_navi31xtw",      # AMD Radeon PRO W7900 - gfx1100
        #                 # "Navi 31 XTW-DS",   # AMD Radeon PRO W7900 Dual Slot - gfx1100
        #                 # "Navi 32 XTW",      # AMD Radeon PRO W7800 - gfx1100
        #                 # "Navi 32 XTW 48GB", # AMD Radeon PRO W7800 48GB - gfx1100
        #     "gpu_navi32xtx",      # AMD Radeon RX 7800 XT - gfx1101
        #     "gpu_navi32xl",       # AMD Radeon RX 7700 XT - gfx1101
        #     "gpu_navi33xt",
        #                 # "Navi33",           # AMD Radeon RX 7600 XT / RX 7600 - gfx1102
        #                 # "Navi33 GLXT",      # AMD Radeon PRO W7600 - gfx1102
        #                 # "Navi33 GLXL"       # AMD Radeon PRO W7500 - gfx1102
        # ],
        #                 # "gfx1150-all": [
        #                 #     "igpu_stx",
        #                 # ],
        # "gfx1151": [
        #     "igpu_stxh",
        # ],
        "gfx120X-all": [
            "gpu_navi48xt",       # AMD Radeon RX 9070 - gfx1201
            # "gpu_navi48xtx",      # AMD Radeon RX 9070 XT - gfx1201
            #             # "gpu_navi48xl",       # AMD Radeon RX 9070 GRE - gfx1201
            #             # "gpu_navi48xtw",      # AMD Radeon AI PRO R9700 - gfx1201
            # "gpu_navi44xl",       # AMD Radeon RX 9060 - gfx1200
            # "gpu_navi44xt"        # AMD Radeon RX 9060 XT - gfx1200
        ],
                    # "gfx115X-all": [
                    #     "Radeon 8060S Graphics",  # AMD Ryzen AI Max+ 395 - gfx1151 Strix Halo
                    #     "Radeon 8050S Graphics",  # AMD Ryzen AI Max 390/385 - gfx1151 Strix Halo
                    #     "AMD Radeon 890M",        # AMD Ryzen AI 9 HX 375/370 - gfx1150 Strix Point
                    #     "AMD Radeon 880M"         # AMD Ryzen AI 9 365 - gfx1150 Strix Point
                    # ]
    }

    if platform.lower() == "linux":
        s3_bucket_url = "https://therock-nightly-tarball.s3.amazonaws.com/"
        
        # Iterate through all GPU architecture patterns in the mapping
        for arch_pattern, gpu_list in gpu_mapping.items():
            # Add platform prefix
            linux_arch_pattern = f"linux-{arch_pattern}"
            
            print(f"\nProcessing architecture pattern: {linux_arch_pattern}")
            latest_linux_sdk_url = get_latest_s3_tarball(s3_bucket_url, linux_arch_pattern)
            
            if not latest_linux_sdk_url:
                print(f"No Linux tarball found for {linux_arch_pattern}; skipping.")
                continue

            if not gpu_list:
                print(f"ERROR: No GPUs found for architecture pattern '{linux_arch_pattern}'")
                continue
            
            # Send an email for each GPU in the list
            for gpu_tag in gpu_list:
                print(f"Sending email for GPU: {gpu_tag}")
                
                email_body_parts = body_parts.copy()
                email_body_parts.extend([
                    "This pipeline includes:",
                    "• ROCm libraries compilation and testing",
                    "• PyTorch wheel building and validation",
                    "• Cross-platform support (Linux & Windows)",
                    "• Multiple GPU family targets (gfx94X, gfx110X, etc.)",
                    "",
                    "This notification was sent automatically by TheRock CI pipeline.",
                    "PLATFORM: Ubuntu",
                    f"THEROCK_SDK_URL: {latest_linux_sdk_url}",
                    f"gpuArchPattern: {gpu_tag}",
                    f"GH_COMMIT_ID: {commit_id if commit_id else 'N/A'}"
                ])
                
                email_body = "\n".join(email_body_parts)
                success = send_email(receiver_email, subject, email_body, sender_password, sender_email)
                
                if not success:
                    print(f"Failed to send email for {gpu_tag}")
                    # Continue with other GPUs even if one fails
        
        return True
    
    elif platform.lower() == "windows":
        s3_bucket_url = "https://rocm.nightlies.amd.com/tarball/"
        
        # Iterate through all GPU architecture patterns in the mapping
        for arch_pattern, gpu_list in gpu_mapping.items():
            # Add platform prefix
            windows_arch_pattern = f"windows-{arch_pattern}"
            
            print(f"\nProcessing architecture pattern: {windows_arch_pattern}")
            latest_windows_sdk_url = get_latest_s3_tarball(s3_bucket_url, windows_arch_pattern)
            
            if not latest_windows_sdk_url:
                print(f"No Windows tarball found for {windows_arch_pattern}; skipping.")
                continue

            if not gpu_list:
                print(f"ERROR: No GPUs found for architecture pattern '{windows_arch_pattern}'")
                continue
            
            # Send an email for each GPU in the list
            for gpu_tag in gpu_list:
                print(f"Sending email for GPU: {gpu_tag}")
                
                email_body_parts = body_parts.copy()
                email_body_parts.extend([
                    "This pipeline includes:",
                    "• ROCm libraries compilation and testing",
                    "• PyTorch wheel building and validation",
                    "• Cross-platform support (Linux & Windows)",
                    "• Multiple GPU family targets (gfx94X, gfx110X, etc.)",
                    "",
                    "This notification was sent automatically by TheRock CI pipeline.",
                    "PLATFORM: Windows",
                    f"THEROCK_SDK_URL: {latest_windows_sdk_url}",
                    f"gpuArchPattern: {gpu_tag}",
                    f"GH_COMMIT_ID: {commit_id if commit_id else 'N/A'}"
                ])
                
                email_body = "\n".join(email_body_parts)
                success = send_email(receiver_email, subject, email_body, sender_password, sender_email)
                
                if not success:
                    print(f"Failed to send email for {gpu_tag}")
                    # Continue with other GPUs even if one fails
        
        return True
    
    return True

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

    print("GPU pattern before removing suffix: ", gpu_arch_pattern)
    gpu_arch_pattern_base = gpu_arch_pattern.split("_")[0]  # Use only the part before underscore
    print("GPU pattern after removing suffix: ", gpu_arch_pattern_base)
    
    # Add therock-dist- prefix only for rocm.nightlies.amd.com bucket
    if "rocm.nightlies.amd.com" in s3_bucket_url:
        search_pattern = f"therock-dist-{gpu_arch_pattern_base}"
    else:
        search_pattern = gpu_arch_pattern_base
    
    print(f"Searching for latest tarball in {s3_bucket_url} matching pattern {search_pattern}")

    # Build the command to get the latest tarball matching the pattern
    # Extract date suffix (YYYYMMDD) from filenames and sort numerically to get the latest build
    # Date format in filenames: 7.10.0a20251113 or 7.9.0rc20251008 (8 digits at the end before .tar.gz)
    # We extract just the date part, sort numerically, then get the corresponding full filename
    if platform.system().lower() == "windows":
        # Windows command using PowerShell - escape pattern for PowerShell
        escaped_pattern = search_pattern.replace("[", "`[").replace("]", "`]")
        cmd = f'powershell -Command "$content = (Invoke-WebRequest -Uri \'{s3_bucket_url}\' -UseBasicParsing).Content; $content | Select-String -Pattern \'<Key>([^<]*{escaped_pattern}[^<]*\\.tar\\.gz)</Key>\' -AllMatches | ForEach-Object {{$_.Matches.Groups[1].Value}} | Where-Object {{$_ -notmatch \'ADHOCBUILD\'}} | Sort-Object {{[regex]::Match($_, \'[0-9]{{8}}\').Value}} | Select-Object -Last 1"'
    else:
        # Linux/Mac command - handle both XML format (S3 AWS) and JavaScript array format (rocm.nightlies.amd.com)
        # Use grep -oP with alternation to match either <Key>...</Key> or "name": "..."
        cmd = f'curl -s "{s3_bucket_url}" | grep -oP \'(?<=<Key>)[^<]*{search_pattern}[^<]*\\.tar\\.gz(?=</Key>)|(?<="name": ")[^"]*{search_pattern}[^"]*\\.tar\\.gz(?=")\' | grep -v "ADHOCBUILD" | awk \'{{match($0, /[0-9]{{8}}/); print substr($0, RSTART, 8), $0}}\' | sort -k1 -n | tail -1 | cut -d" " -f2'

    result = run_command_with_logging(cmd)

    if result.returncode != 0:
        print("ERROR: Failed to get S3 bucket listing")
        return ""

    # Get the filename from stdout
    latest_filename = result.stdout.strip()

    if not latest_filename:
        print(f"ERROR: No tar.gz file found matching pattern '{search_pattern}'")
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
            sys.exit(1)

# Example usage:
if __name__ == "__main__":
    if len(sys.argv) > 1:
        main()
    else:
        print("Usage: python sent_email.py --receiver EMAIL --status STATUS --sender-email EMAIL [options]")
        print("Use --help for more information.")
        sys.exit(1)



