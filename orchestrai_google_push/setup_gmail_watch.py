"""
Gmail API Watch Configuration Script
Sets up Gmail push notifications by configuring the watch request
"""

import json
import logging
from typing import Dict, Any

from google.oauth2 import service_account
from googleapiclient.discovery import build
from google.cloud import pubsub_v1

from gmail_push_config import GmailPushConfig

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class GmailWatchSetup:
    """Setup Gmail API watch functionality"""
    
    def __init__(self):
        self.config = GmailPushConfig()
        self.gmail_service = None
        self.pubsub_client = None
        self.setup_services()
    
    def setup_services(self):
        """Initialize Gmail and Pub/Sub services"""
        try:
            # Load service account credentials
            credentials = service_account.Credentials.from_service_account_file(
                self.config.GOOGLE_CREDENTIALS_FILE,
                scopes=[
                    'https://www.googleapis.com/auth/gmail.readonly',
                    'https://www.googleapis.com/auth/pubsub'
                ]
            )
            
            # Gmail service with domain delegation
            gmail_credentials = credentials.with_subject(self.config.GMAIL_USER_EMAIL)
            self.gmail_service = build('gmail', 'v1', credentials=gmail_credentials)
            
            # Pub/Sub client
            self.pubsub_client = pubsub_v1.PublisherClient(credentials=credentials)
            
            logger.info("Services initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize services: {e}")
            raise
    
    def create_pubsub_topic(self) -> str:
        """Create Pub/Sub topic if it doesn't exist"""
        topic_path = self.pubsub_client.topic_path(
            self.config.GOOGLE_CLOUD_PROJECT_ID, 
            self.config.PUBSUB_TOPIC_NAME
        )
        
        try:
            # Try to create the topic
            self.pubsub_client.create_topic(request={"name": topic_path})
            logger.info(f"Created Pub/Sub topic: {topic_path}")
        except Exception as e:
            if "already exists" in str(e).lower():
                logger.info(f"Pub/Sub topic already exists: {topic_path}")
            else:
                logger.error(f"Failed to create Pub/Sub topic: {e}")
                raise
        
        return topic_path
    
    def setup_gmail_watch(self, webhook_url: str) -> Dict[str, Any]:
        """
        Set up Gmail watch request to receive push notifications
        
        Args:
            webhook_url: The URL where push notifications will be sent
        """
        try:
            # Ensure Pub/Sub topic exists
            topic_path = self.create_pubsub_topic()
            
            # Configure watch request
            request_body = {
                'labelIds': ['INBOX'],  # Watch inbox only
                'topicName': topic_path,
                'labelFilterAction': 'include'  # Only include emails with specified labels
            }
            
            # Set up the watch
            watch_response = self.gmail_service.users().watch(
                userId='me',
                body=request_body
            ).execute()
            
            logger.info(f"Gmail watch setup successful: {watch_response}")
            
            return {
                'status': 'success',
                'watch_response': watch_response,
                'topic_path': topic_path,
                'webhook_url': webhook_url
            }
            
        except Exception as e:
            logger.error(f"Failed to setup Gmail watch: {e}")
            return {
                'status': 'error',
                'error': str(e)
            }
    
    def stop_gmail_watch(self) -> Dict[str, Any]:
        """Stop Gmail watch notifications"""
        try:
            self.gmail_service.users().stop(userId='me').execute()
            logger.info("Gmail watch stopped successfully")
            return {'status': 'success', 'message': 'Watch stopped'}
        except Exception as e:
            logger.error(f"Failed to stop Gmail watch: {e}")
            return {'status': 'error', 'error': str(e)}
    
    def get_watch_status(self) -> Dict[str, Any]:
        """Get current Gmail watch status"""
        try:
            # Get user profile to check watch status
            profile = self.gmail_service.users().getProfile(userId='me').execute()
            
            # Note: Gmail API doesn't provide direct watch status endpoint
            # You would typically store watch information in your application
            return {
                'status': 'success',
                'email_address': profile.get('emailAddress'),
                'messages_total': profile.get('messagesTotal'),
                'threads_total': profile.get('threadsTotal')
            }
        except Exception as e:
            logger.error(f"Failed to get watch status: {e}")
            return {'status': 'error', 'error': str(e)}

def main():
    """Main function to setup Gmail watch"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Setup Gmail Push Notifications')
    parser.add_argument('--webhook-url', required=True, 
                       help='Webhook URL to receive push notifications')
    parser.add_argument('--action', choices=['setup', 'stop', 'status'], 
                       default='setup', help='Action to perform')
    
    args = parser.parse_args()
    
    # Validate configuration
    missing_config = GmailPushConfig.validate_config()
    if missing_config:
        logger.error(f"Missing required configuration: {missing_config}")
        return 1
    
    setup = GmailWatchSetup()
    
    if args.action == 'setup':
        result = setup.setup_gmail_watch(args.webhook_url)
        print(json.dumps(result, indent=2))
    elif args.action == 'stop':
        result = setup.stop_gmail_watch()
        print(json.dumps(result, indent=2))
    elif args.action == 'status':
        result = setup.get_watch_status()
        print(json.dumps(result, indent=2))
    
    return 0 if result.get('status') == 'success' else 1

if __name__ == '__main__':
    exit(main())