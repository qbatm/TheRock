import argparse
import json
import os
import smtplib
import sys
from datetime import datetime
from email.mime.text import MIMEText

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
        platform_configs = {
            "linux-gfx110X-dgpu": {
                "PLATFORM": "Linux",
                "S3_BUCKET_URL": "https://therock-nightly-tarball.s3.amazonaws.com/",
                "gpuArchPattern": "linux-gfx110X-dgpu",
                "THEROCK_WHL_URL": "https://rocm.nightlies.amd.com/v2/gfx110X-dgpu/"
            },
            "linux-gfx110X-dgpu-xtx": {
                "PLATFORM": "Linux",
                "S3_BUCKET_URL": "https://therock-nightly-tarball.s3.amazonaws.com/",
                "gpuArchPattern": "linux-gfx110X-dgpu_xtx",
                "THEROCK_WHL_URL": "https://rocm.nightlies.amd.com/v2/gfx110X-dgpu/"
            },
            "linux-gfx110X-dgpu-navi44xt": {
                "PLATFORM": "Linux",
                "S3_BUCKET_URL": "https://therock-nightly-tarball.s3.amazonaws.com/",
                "gpuArchPattern": "linux-gfx110X-dgpu_navi44xt",
                "THEROCK_WHL_URL": "https://rocm.nightlies.amd.com/v2/gfx110X-dgpu/"
            },
            "windows-gfx110X-dgpu-1": {
                "PLATFORM": "Windows",
                "S3_BUCKET_URL": "https://therock-nightly-tarball.s3.amazonaws.com/",
                "gpuArchPattern": "windows-gfx110X-dgpu",
                "THEROCK_WHL_URL": "https://rocm.nightlies.amd.com/v2/gfx110X-dgpu/"
            },
            "windows-gfx110X-dgpu-2": {
                "PLATFORM": "Windows",
                "S3_BUCKET_URL": "https://therock-nightly-tarball.s3.amazonaws.com/",
                "gpuArchPattern": "windows-gfx110X-dgpu",
                "THEROCK_WHL_URL": "https://rocm.nightlies.amd.com/v2/gfx110X-dgpu/"
            },
            "windows-gfx110X-dgpu-3": {
                "PLATFORM": "Windows",
                "S3_BUCKET_URL": "https://therock-nightly-tarball.s3.amazonaws.com/",
                "gpuArchPattern": "windows-gfx110X-dgpu",
                "THEROCK_WHL_URL": "https://rocm.nightlies.amd.com/v2/gfx110X-dgpu/"
            },
            "windows-gfx110X-dgpu-4": {
                "PLATFORM": "Windows",
                "S3_BUCKET_URL": "https://therock-nightly-tarball.s3.amazonaws.com/",
                "gpuArchPattern": "windows-gfx110X-dgpu",
                "THEROCK_WHL_URL": "https://rocm.nightlies.amd.com/v2/gfx110X-dgpu/"
            },
            "windows-gfx110X-dgpu-navi44xt-1": {
                "PLATFORM": "Windows",
                "S3_BUCKET_URL": "https://therock-nightly-tarball.s3.amazonaws.com/",
                "gpuArchPattern": "windows-gfx110X-dgpu_navi44xt",
                "THEROCK_WHL_URL": "https://rocm.nightlies.amd.com/v2/gfx110X-dgpu/"
            },
            "windows-gfx110X-dgpu-navi44xt-2": {
                "PLATFORM": "Windows",
                "S3_BUCKET_URL": "https://therock-nightly-tarball.s3.amazonaws.com/",
                "gpuArchPattern": "windows-gfx110X-dgpu_navi44xt",
                "THEROCK_WHL_URL": "https://rocm.nightlies.amd.com/v2/gfx110X-dgpu/"
            },
            "windows-gfx110X-dgpu-navi44xt-3": {
                "PLATFORM": "Windows",
                "S3_BUCKET_URL": "https://therock-nightly-tarball.s3.amazonaws.com/",
                "gpuArchPattern": "windows-gfx110X-dgpu_navi44xt",
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
