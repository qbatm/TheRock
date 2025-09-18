"""
Gmail Push Webhook Server
Receives push notifications from Gmail via Google Cloud Pub/Sub
and triggers Jenkins pipeline based on email content.
"""

import base64
import json
import logging
import hmac
import hashlib
from typing import Dict, Any, Optional
from datetime import datetime

from flask import Flask, request, jsonify
from google.cloud import pubsub_v1
from google.oauth2 import service_account
from googleapiclient.discovery import build
import requests

from gmail_push_config import GmailPushConfig
from security_utils import security_validator, is_duplicate_request

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

class GmailPushHandler:
    """Handles Gmail push notifications and processes emails"""
    
    def __init__(self):
        self.config = GmailPushConfig()
        self.gmail_service = None
        self.setup_gmail_service()
    
    def setup_gmail_service(self):
        """Initialize Gmail API service"""
        try:
            # Load service account credentials
            credentials = service_account.Credentials.from_service_account_file(
                self.config.GOOGLE_CREDENTIALS_FILE,
                scopes=['https://www.googleapis.com/auth/gmail.readonly']
            )
            
            # Delegate to the user email for accessing their Gmail
            delegated_credentials = credentials.with_subject(self.config.GMAIL_USER_EMAIL)
            
            self.gmail_service = build('gmail', 'v1', credentials=delegated_credentials)
            logger.info("Gmail service initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize Gmail service: {e}")
            raise
    
    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        """Verify webhook signature for security"""
        if not self.config.WEBHOOK_SECRET:
            logger.warning("No webhook secret configured - skipping signature verification")
            return True
            
        expected_signature = hmac.new(
            self.config.WEBHOOK_SECRET.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(signature, expected_signature)
    
    def get_email_content(self, message_id: str) -> Optional[Dict[str, Any]]:
        """Fetch email content using Gmail API"""
        try:
            message = self.gmail_service.users().messages().get(
                userId='me',
                id=message_id,
                format='full'
            ).execute()
            
            headers = message['payload'].get('headers', [])
            subject = next((h['value'] for h in headers if h['name'] == 'Subject'), '')
            
            # Check if subject matches our filter
            if self.config.EMAIL_SUBJECT_FILTER not in subject:
                logger.info(f"Email subject '{subject}' doesn't match filter")
                return None
            
            # Extract email body
            body = self._extract_email_body(message['payload'])
            
            return {
                'subject': subject,
                'body': body,
                'message_id': message_id,
                'timestamp': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to fetch email content: {e}")
            return None
    
    def _extract_email_body(self, payload: Dict[str, Any]) -> str:
        """Extract plain text body from email payload"""
        body = ""
        
        if 'parts' in payload:
            # Multipart message
            for part in payload['parts']:
                if part['mimeType'] == 'text/plain' and 'data' in part['body']:
                    body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8')
                    break
        elif payload['mimeType'] == 'text/plain' and 'data' in payload['body']:
            # Simple text message
            body = base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8')
        
        return body
    
    def extract_pipeline_info(self, email_body: str) -> Dict[str, str]:
        """Extract pipeline information from email body (from existing script)"""
        import re
        
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
    
    def trigger_jenkins_pipeline(self, pipeline_info: Dict[str, str]) -> bool:
        """Trigger Jenkins pipeline with extracted parameters"""
        try:
            session = requests.Session()
            session.auth = (self.config.JENKINS_USER, self.config.JENKINS_API_TOKEN)
            session.verify = True
            
            # Get Jenkins crumb
            crumb_url = f"{self.config.JENKINS_URL}/crumbIssuer/api/json"
            crumb = {}
            r = session.get(crumb_url)
            if r.ok:
                j = r.json()
                crumb = {j['crumbRequestField']: j['crumb']}
            
            # Trigger build
            trigger_url = f"{self.config.JENKINS_URL}/job/{self.config.JENKINS_JOB}/buildWithParameters"
            
            params = {
                'PLATFORM': pipeline_info.get('Platform', ''),
                'S3_BUCKET_URL': pipeline_info.get('S3_BUCKET_URL', ''),
                'gpuArchPattern': pipeline_info.get('gpuArchPattern', ''),
                'THEROCK_WHL_URL': pipeline_info.get('THEROCK_WHL_URL', '')
            }
            
            r = session.post(trigger_url, headers=crumb, data=params)
            
            if r.status_code in (201, 302):
                queue_url = r.headers.get("Location")
                logger.info(f"Pipeline triggered successfully. Queue URL: {queue_url}")
                return True
            else:
                logger.error(f"Failed to trigger pipeline: {r.status_code} {r.text}")
                return False
                
        except Exception as e:
            logger.error(f"Error triggering Jenkins pipeline: {e}")
            return False
    
    def process_push_notification(self, message_data: Dict[str, Any], request_ip: str = '') -> Dict[str, Any]:
        """Process Gmail push notification with security validation"""
        try:
            # Decode the message data
            if 'emailAddress' not in message_data:
                logger.warning("No email address in push notification")
                return {'status': 'ignored', 'reason': 'no_email_address'}
            
            if 'historyId' not in message_data:
                logger.warning("No history ID in push notification")
                return {'status': 'ignored', 'reason': 'no_history_id'}
            
            # For simplicity, we'll get the latest unread emails
            # In production, you might want to use the historyId to get specific changes
            messages = self.gmail_service.users().messages().list(
                userId='me',
                q='is:unread'
            ).execute()
            
            if 'messages' not in messages:
                logger.info("No unread messages found")
                return {'status': 'no_new_messages'}
            
            for message in messages['messages'][:5]:  # Check latest 5 unread messages
                email_content = self.get_email_content(message['id'])
                
                if email_content:
                    logger.info(f"Processing email: {email_content['subject']}")
                    
                    # Check for duplicate requests
                    if is_duplicate_request(email_content):
                        logger.info("Duplicate request detected, skipping")
                        continue
                    
                    # Security validation
                    validation_result = security_validator.validate_request(request_ip, email_content)
                    if not validation_result['valid']:
                        logger.warning(f"Security validation failed: {validation_result['reason']}")
                        return {
                            'status': 'blocked',
                            'reason': validation_result['reason'],
                            'email_subject': email_content['subject']
                        }
                    
                    # Extract pipeline info
                    pipeline_info = self.extract_pipeline_info(email_content['body'])
                    
                    if pipeline_info:
                        # Mark email as read
                        self.gmail_service.users().messages().modify(
                            userId='me',
                            id=message['id'],
                            body={'removeLabelIds': ['UNREAD']}
                        ).execute()
                        
                        # Trigger Jenkins pipeline
                        success = self.trigger_jenkins_pipeline(pipeline_info)
                        
                        return {
                            'status': 'processed',
                            'email_subject': email_content['subject'],
                            'pipeline_triggered': success,
                            'pipeline_info': pipeline_info,
                            'security_check': 'passed'
                        }
            
            return {'status': 'no_matching_emails'}
            
        except Exception as e:
            logger.error(f"Error processing push notification: {e}")
            return {'status': 'error', 'message': str(e)}

# Initialize handler
gmail_handler = GmailPushHandler()

@app.route('/webhook/gmail-push', methods=['POST'])
def handle_gmail_push():
    """Handle Gmail push notification webhook"""
    try:
        # Verify signature if configured
        signature = request.headers.get('X-Webhook-Signature', '')
        if not gmail_handler.verify_webhook_signature(request.data, signature):
            logger.warning("Invalid webhook signature")
            return jsonify({'error': 'Invalid signature'}), 401
        
        # Parse Pub/Sub message
        envelope = request.get_json()
        if not envelope:
            logger.warning("No JSON payload in request")
            return jsonify({'error': 'No JSON payload'}), 400
        
        pubsub_message = envelope.get('message', {})
        if not pubsub_message:
            logger.warning("No message in envelope")
            return jsonify({'error': 'No message'}), 400
        
        # Decode message data
        message_data = {}
        if 'data' in pubsub_message:
            try:
                decoded_data = base64.b64decode(pubsub_message['data']).decode('utf-8')
                message_data = json.loads(decoded_data)
            except Exception as e:
                logger.error(f"Failed to decode message data: {e}")
                return jsonify({'error': 'Invalid message data'}), 400
        
        logger.info(f"Received Gmail push notification: {message_data}")
        
        # Get client IP for security validation
        client_ip = request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr)
        
        # Process the notification
        result = gmail_handler.process_push_notification(message_data, client_ip)
        
        return jsonify(result), 200
        
    except Exception as e:
        logger.error(f"Error handling webhook: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat()}), 200

@app.route('/test', methods=['POST'])
def test_endpoint():
    """Test endpoint for manual testing"""
    try:
        # Get client IP for security validation
        client_ip = request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr)
        
        # Process latest unread email for testing
        result = gmail_handler.process_push_notification(
            {'emailAddress': gmail_handler.config.GMAIL_USER_EMAIL}, 
            client_ip
        )
        return jsonify(result), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    # Validate configuration
    missing_config = GmailPushConfig.validate_config()
    if missing_config:
        logger.error(f"Missing required configuration: {missing_config}")
        exit(1)
    
    logger.info("Starting Gmail Push webhook server...")
    app.run(
        host=GmailPushConfig.WEBHOOK_HOST,
        port=GmailPushConfig.WEBHOOK_PORT,
        debug=False
    )