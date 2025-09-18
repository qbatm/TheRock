import imaplib
import email
import argparse
import re
import time
import requests
from email.header import decode_header

def trigger_orchestrai_pipeline(S3_BUCKET_URL, gpuArchPattern, THEROCK_WHL_URL, Platform, API_TOKEN):
    """
    Triggers the OrchestrAI-TheRock Jenkins pipeline with specified parameters.
    Adjust the JOB, USER, and parameters as needed.
    """

    JENKINS = "https://ucicd-jenkins.amd.com/"
    JOB = "OrchestrAI-TheRock-Multi"  # adjust (for foldered jobs: "folder/job/JobName")
    USER = "jpiatkow"

    session = requests.Session()
    session.auth = (USER, API_TOKEN)
    session.verify = True  # set False only for self-signed certs

    # 1) get crumb (if crumb issuer enabled)
    crumb_url = f"{JENKINS}/crumbIssuer/api/json"
    crumb = {}
    r = session.get(crumb_url)
    if r.ok:
        j = r.json()
        crumb = {j['crumbRequestField']: j['crumb']}

    # 2) trigger build (use buildWithParameters for parameterized jobs)
    trigger_url = f"{JENKINS}/job/{JOB}/buildWithParameters"

    # Define your pipeline parameters
    params = {
        'PLATFORM': Platform,
        'S3_BUCKET_URL': S3_BUCKET_URL,
        'gpuArchPattern': gpuArchPattern, 
        'THEROCK_WHL_URL': THEROCK_WHL_URL
    }

    r = session.post(trigger_url, headers=crumb, data=params)
    # Jenkins usually responds with 201 Created and Location header pointing to queue item
    if r.status_code not in (201, 302):
        raise SystemExit(f"Trigger failed: {r.status_code} {r.text}")

    queue_url = r.headers.get("Location")
    print("Enqueued at:", queue_url)

    # 3) poll queue until a build is assigned, then get build number
    if queue_url:
        api_queue_url = queue_url if queue_url.endswith('/api/json') else queue_url + "api/json"
        for _ in range(60):  # up to ~60 checks
            q = session.get(api_queue_url, headers=crumb).json()
            if q.get("executable"):
                build_number = q["executable"]["number"]
                print("Build assigned:", build_number)
                print("Console URL:", f"{JENKINS}/job/{JOB}/{build_number}/console")
                break
            time.sleep(2)
        else:
            print("Timed out waiting for build assignment.")

def extract_pipeline_info(email_body):
    """Extract S3_BUCKET_URL, gpuArchPattern, and THEROCK_WHL_URL from email body."""
    info = {}
    
    # Extract Platform
    platform_match = re.search(r'PLATFORM:\s*([^\s\n]+)', email_body)
    if platform_match:
        info['Platform'] = platform_match.group(1)

    # Extract S3_BUCKET_URL
    s3_match = re.search(r'S3_BUCKET_URL:\s*"([^"]+)"', email_body)
    if s3_match:
        info['S3_BUCKET_URL'] = s3_match.group(1)
    
    # Extract gpuArchPattern
    gpu_arch_match = re.search(r'gpuArchPattern:\s*([^\s\n]+)', email_body)
    if gpu_arch_match:
        info['gpuArchPattern'] = gpu_arch_match.group(1)
    
    # Extract THEROCK_WHL_URL
    whl_match = re.search(r'THEROCK_WHL_URL:\s*([^\s\n]+)', email_body)
    if whl_match:
        info['THEROCK_WHL_URL'] = whl_match.group(1)
    
    return info

def get_latest_email(search_string, email_pass, max_emails=100, platform="linux"):
    imap_server = "imap.gmail.com"
    email_user = "j93113820@gmail.com" #"your_gmail_address@gmail.com"
    # email_pass is now passed as a parameter

    # Connect to the server
    mail = imaplib.IMAP4_SSL(imap_server)
    mail.login(email_user, email_pass)
    mail.select("inbox")

    # Search for unread emails only
    status, messages = mail.search(None, 'UNSEEN')
    email_ids = messages[0].split()
    email_ids.reverse()  # Start from the latest
    
    # Limit the number of emails to check
    email_ids = email_ids[:max_emails]

    for eid in email_ids:
        status, msg_data = mail.fetch(eid, "(RFC822)")
        for response_part in msg_data:
            if isinstance(response_part, tuple):
                msg = email.message_from_bytes(response_part[1])
                subject, encoding = decode_header(msg["Subject"])[0]
                if isinstance(subject, bytes):
                    subject = subject.decode(encoding if encoding else "utf-8")
                if search_string in subject:
                    print("Found email with subject:", subject)
                    email_body = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            if part.get_content_type() == "text/plain":
                                email_body = part.get_payload(decode=True).decode()
                                break
                    else:
                        email_body = msg.get_payload(decode=True).decode()
                    
                    print("Body:", email_body)
                    
                    # Mark email as read
                    mail.store(eid, '+FLAGS', '\\Seen')
                    
                    # Extract pipeline information
                    pipeline_info = extract_pipeline_info(email_body)
                    mail.logout()
                    return pipeline_info
    print("No email found with the specified string.")
    mail.logout()
    return {}

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Get latest email with specified search string')
    parser.add_argument('--email_pass', required=True, help='Gmail app password')
    parser.add_argument('--api_token', required=True, help='Jenkins API token')
    parser.add_argument('--search_string', default='TheRock Pipeline', help='Search string to find in email subject (default: "TheRock Pipeline")')
    parser.add_argument('--max_emails', type=int, default=100, help='Maximum number of emails to check from latest (default: 100)')
    
    args = parser.parse_args()
    
    result = get_latest_email(args.search_string, args.email_pass, args.max_emails)
    if result:
        print("\nExtracted Pipeline Information:")
        for key, value in result.items():
            print(f"{key}: {value}")
    else:
        print("No pipeline information found.")

    if result:
        trigger_orchestrai_pipeline(result.get('S3_BUCKET_URL'), result.get('gpuArchPattern'), result.get('THEROCK_WHL_URL'), result.get('Platform'), args.api_token)
