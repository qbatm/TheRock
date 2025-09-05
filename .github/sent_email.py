import argparse
import os
import smtplib
import sys
from datetime import datetime
from email.mime.text import MIMEText

def send_email(receiver_email, subject, body, sender_password=None, sender_email=None):
    smtp_server = "smtp.gmail.com"
    smtp_port = 587
    sender_email = sender_email or "kuba.kubanczyk@gmail.com"
    
    # Get password from parameter, environment variable, or prompt user
    if sender_password is None:
        sender_password = os.getenv('GMAIL_PASSWORD')
        if sender_password is None:
            print("Error: Gmail password not provided. Use --gmail-pass argument or GMAIL_PASSWORD environment variable.")
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

def send_pipeline_notification(receiver_email, status, workflow_url=None, failed_jobs=None, details=None, sender_password=None, sender_email=None):
    """Send a pipeline completion notification email."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
    status_emoji = "✅" if status == "success" else "❌" if status == "failure" else "⚠️"
    
    subject = f"{status_emoji} TheRock Pipeline {status.title()} - Libraries & PyTorch Wheels"
    
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
        "S3_BUCKET_URL: \"https://therock-nightly-tarball.s3.amazonaws.com/\"",
        "gpuArchPattern: linux-gfx120X",
        "THEROCK_WHL_URL: https://d2awnip2yjpvqn.cloudfront.net/v2/gfx120X-all/"
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
    parser.add_argument("--gmail-pass", help="Gmail app password for authentication")
    parser.add_argument("--sender-email", default="kuba.kubanczyk@gmail.com", 
                       help="Sender email address (default: kuba.kubanczyk@gmail.com)")
    
    # Legacy support
    parser.add_argument("--subject", help="Email subject (legacy mode)")
    parser.add_argument("--body", help="Email body (legacy mode)")
    
    args = parser.parse_args()
    
    if args.subject and args.body:
        # Legacy mode
        send_email(args.receiver, args.subject, args.body, args.gmail_pass, args.sender_email)
    else:
        # Pipeline notification mode
        send_pipeline_notification(
            receiver_email=args.receiver,
            status=args.status,
            workflow_url=args.workflow_url,
            failed_jobs=args.failed_jobs,
            details=args.details,
            sender_password=args.gmail_pass,
            sender_email=args.sender_email
        )

# Example usage:
if __name__ == "__main__":
    if len(sys.argv) > 1:
        main()
    else:
        send_email(
            receiver_email="kuba.kubanczyk@gmail.com",
            subject="Test Subject",
            body="This is a test email sent from Python using Gmail.",
            sender_password="gzha newu shxb dyua"  # Hardcoded for backward compatibility

        )
