import argparse
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
        print("Email sent successfully!")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
    finally:
        if 'server' in locals() and server:
            server.quit()

def send_pipeline_notification(receiver_email, status, workflow_url=None, failed_jobs=None, details=None, sender_password=None, sender_email=None, platform=None):
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

    if platform.lower() == "linux":
        body_parts.extend([
            "This pipeline includes:",
            "• ROCm libraries compilation and testing",
            "• PyTorch wheel building and validation",
            "• Cross-platform support (Linux & Windows)",
            "• Multiple GPU family targets (gfx94X, gfx110X, etc.)",
            "",
            "This notification was sent automatically by TheRock CI pipeline.",
            "PLATFORM: Linux",
            "S3_BUCKET_URL: \"https://therock-nightly-tarball.s3.amazonaws.com/\"",
            "gpuArchPattern: linux-gfx120X",
            "THEROCK_WHL_URL: https://d2awnip2yjpvqn.cloudfront.net/v2/gfx120X-all/"
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
            "gpuArchPattern: windows-gfx110X-dgpu",
            "THEROCK_WHL_URL: https://rocm.nightlies.amd.com/v2/gfx110X-dgpu/"
        ])
    
    body = "\n".join(body_parts)
    send_email(receiver_email, subject, body, sender_password, sender_email)

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
            platform=args.platform
        )

# Example usage:
if __name__ == "__main__":
    if len(sys.argv) > 1:
        main()
    else:
        print("Usage: python sent_email.py --receiver EMAIL --status STATUS --sender-email EMAIL [options]")
        print("Use --help for more information.")
        sys.exit(1)


