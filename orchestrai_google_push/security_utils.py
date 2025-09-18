"""
Security utilities for Gmail Push webhook system
"""

import hashlib
import time
import logging
from typing import Dict, Any, Optional
from collections import defaultdict, deque
from datetime import datetime, timedelta

import requests
from gmail_push_config import GmailPushConfig

logger = logging.getLogger(__name__)

class RateLimiter:
    """Simple rate limiter to prevent abuse"""
    
    def __init__(self, max_requests: int = 10, window_minutes: int = 5):
        self.max_requests = max_requests
        self.window_seconds = window_minutes * 60
        self.requests = defaultdict(deque)
    
    def is_allowed(self, identifier: str) -> bool:
        """Check if request is allowed based on rate limiting"""
        now = time.time()
        window_start = now - self.window_seconds
        
        # Clean old requests
        request_times = self.requests[identifier]
        while request_times and request_times[0] < window_start:
            request_times.popleft()
        
        # Check if under limit
        if len(request_times) >= self.max_requests:
            return False
        
        # Add current request
        request_times.append(now)
        return True

class GitHubVerifier:
    """Verify GitHub integration for additional security"""
    
    def __init__(self, config: GmailPushConfig):
        self.config = config
        self.github_api_base = "https://api.github.com"
    
    def verify_recent_commit(self, repo_owner: str = "qbatm", repo_name: str = "TheRock", 
                           hours_threshold: int = 24) -> bool:
        """
        Verify there was a recent commit in the repository
        This ensures the pipeline trigger is likely legitimate
        """
        if not self.config.ENABLE_GITHUB_VERIFICATION:
            return True
            
        if not self.config.GITHUB_TOKEN:
            logger.warning("GitHub verification enabled but no token provided")
            return False
        
        try:
            headers = {
                'Authorization': f'token {self.config.GITHUB_TOKEN}',
                'Accept': 'application/vnd.github.v3+json'
            }
            
            # Get recent commits
            url = f"{self.github_api_base}/repos/{repo_owner}/{repo_name}/commits"
            params = {
                'since': (datetime.utcnow() - timedelta(hours=hours_threshold)).isoformat() + 'Z',
                'per_page': 10
            }
            
            response = requests.get(url, headers=headers, params=params, timeout=10)
            
            if response.status_code == 200:
                commits = response.json()
                logger.info(f"Found {len(commits)} recent commits in {repo_owner}/{repo_name}")
                return len(commits) > 0
            else:
                logger.error(f"GitHub API error: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Error verifying GitHub commits: {e}")
            return False
    
    def verify_build_number_pattern(self, email_body: str) -> bool:
        """
        Verify that the email contains a valid build number pattern
        This helps ensure the email is from legitimate CI/CD system
        """
        import re
        
        # Look for common CI/CD build number patterns
        build_patterns = [
            r'Build\s+#?\d+',
            r'build\s+number[:\s]+\d+',
            r'Pipeline\s+#?\d+',
            r'Job\s+#?\d+',
            r'\bbuild[:\s]+\d+',
        ]
        
        for pattern in build_patterns:
            if re.search(pattern, email_body, re.IGNORECASE):
                logger.info(f"Found build number pattern: {pattern}")
                return True
        
        logger.warning("No valid build number pattern found in email")
        return False

class SecurityValidator:
    """Main security validation class"""
    
    def __init__(self, config: GmailPushConfig):
        self.config = config
        self.rate_limiter = RateLimiter(max_requests=20, window_minutes=5)
        self.github_verifier = GitHubVerifier(config)
    
    def validate_request(self, request_ip: str, email_content: Dict[str, Any]) -> Dict[str, Any]:
        """
        Comprehensive request validation
        Returns dict with 'valid' boolean and 'reason' if invalid
        """
        # Rate limiting
        if not self.rate_limiter.is_allowed(request_ip):
            return {'valid': False, 'reason': 'Rate limit exceeded'}
        
        # Verify build number pattern in email
        if not self.github_verifier.verify_build_number_pattern(email_content.get('body', '')):
            return {'valid': False, 'reason': 'No valid build number pattern found'}
        
        # GitHub verification (if enabled)
        if self.config.ENABLE_GITHUB_VERIFICATION:
            if not self.github_verifier.verify_recent_commit():
                return {'valid': False, 'reason': 'No recent commits found in repository'}
        
        return {'valid': True, 'reason': 'All validations passed'}
    
    def get_request_fingerprint(self, email_content: Dict[str, Any]) -> str:
        """
        Generate a fingerprint for the request to detect duplicates
        """
        content_to_hash = f"{email_content.get('subject', '')}{email_content.get('message_id', '')}"
        return hashlib.sha256(content_to_hash.encode()).hexdigest()

# Global instances
security_validator = SecurityValidator(GmailPushConfig())
processed_fingerprints = set()
fingerprint_cleanup_time = time.time()

def is_duplicate_request(email_content: Dict[str, Any]) -> bool:
    """Check if this request has been processed recently"""
    global fingerprint_cleanup_time, processed_fingerprints
    
    # Clean up old fingerprints every hour
    now = time.time()
    if now - fingerprint_cleanup_time > 3600:  # 1 hour
        processed_fingerprints.clear()
        fingerprint_cleanup_time = now
    
    fingerprint = security_validator.get_request_fingerprint(email_content)
    
    if fingerprint in processed_fingerprints:
        return True
    
    processed_fingerprints.add(fingerprint)
    return False