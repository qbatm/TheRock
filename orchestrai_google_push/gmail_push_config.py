"""
Configuration for Gmail Push Notifications
"""
import os
from typing import Optional

class GmailPushConfig:
    """Configuration class for Gmail Push notifications"""
    
    # Google Cloud Project settings
    GOOGLE_CLOUD_PROJECT_ID: str = os.getenv('GOOGLE_CLOUD_PROJECT_ID', '')
    PUBSUB_TOPIC_NAME: str = os.getenv('PUBSUB_TOPIC_NAME', 'gmail-push-notifications')
    PUBSUB_SUBSCRIPTION_NAME: str = os.getenv('PUBSUB_SUBSCRIPTION_NAME', 'gmail-push-subscription')
    
    # Service Account credentials file path
    GOOGLE_CREDENTIALS_FILE: str = os.getenv('GOOGLE_CREDENTIALS_FILE', 'service-account.json')
    
    # Gmail API settings
    GMAIL_USER_EMAIL: str = os.getenv('GMAIL_USER_EMAIL', 'j93113820@gmail.com')
    
    # Webhook server settings
    WEBHOOK_HOST: str = os.getenv('WEBHOOK_HOST', '0.0.0.0')
    WEBHOOK_PORT: int = int(os.getenv('WEBHOOK_PORT', '8080'))
    WEBHOOK_SECRET: str = os.getenv('WEBHOOK_SECRET', '')  # For request validation
    
    # Jenkins settings (from existing script)
    JENKINS_URL: str = os.getenv('JENKINS_URL', 'https://ucicd-jenkins.amd.com/')
    JENKINS_JOB: str = os.getenv('JENKINS_JOB', 'OrchestrAI-TheRock-Multi')
    JENKINS_USER: str = os.getenv('JENKINS_USER', 'jpiatkow')
    JENKINS_API_TOKEN: str = os.getenv('JENKINS_API_TOKEN', '')
    
    # Email filtering settings
    EMAIL_SUBJECT_FILTER: str = os.getenv('EMAIL_SUBJECT_FILTER', 'TheRock Pipeline')
    
    # Security settings
    ENABLE_GITHUB_VERIFICATION: bool = os.getenv('ENABLE_GITHUB_VERIFICATION', 'false').lower() == 'true'
    GITHUB_TOKEN: Optional[str] = os.getenv('GITHUB_TOKEN')
    
    @classmethod
    def validate_config(cls) -> list[str]:
        """Validate configuration and return list of missing required settings"""
        missing = []
        
        if not cls.GOOGLE_CLOUD_PROJECT_ID:
            missing.append('GOOGLE_CLOUD_PROJECT_ID')
        
        if not cls.JENKINS_API_TOKEN:
            missing.append('JENKINS_API_TOKEN')
            
        if not cls.WEBHOOK_SECRET:
            missing.append('WEBHOOK_SECRET')
            
        if cls.ENABLE_GITHUB_VERIFICATION and not cls.GITHUB_TOKEN:
            missing.append('GITHUB_TOKEN (required when ENABLE_GITHUB_VERIFICATION is true)')
            
        return missing