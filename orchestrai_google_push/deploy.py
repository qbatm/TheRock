#!/usr/bin/env python3
"""
Gmail Push Notification Deployment Script
Helps set up and deploy the Gmail Push notification system
"""

import os
import sys
import json
import subprocess
import argparse
from pathlib import Path
from typing import Dict, Any, List

class GmailPushDeployment:
    """Deployment helper for Gmail Push notification system"""
    
    def __init__(self):
        self.project_root = Path(__file__).parent
        self.required_files = [
            'gmail_push_config.py',
            'gmail_push_webhook.py',
            'security_utils.py',
            'setup_gmail_watch.py',
            'requirements.txt'
        ]
    
    def check_prerequisites(self) -> Dict[str, Any]:
        """Check if all required files and dependencies exist"""
        results = {
            'files_exist': True,
            'missing_files': [],
            'python_version_ok': False,
            'pip_available': False
        }
        
        # Check Python version
        if sys.version_info >= (3, 8):
            results['python_version_ok'] = True
        
        # Check if pip is available
        try:
            subprocess.run([sys.executable, '-m', 'pip', '--version'], 
                         capture_output=True, check=True)
            results['pip_available'] = True
        except subprocess.CalledProcessError:
            pass
        
        # Check required files
        for file_name in self.required_files:
            file_path = self.project_root / file_name
            if not file_path.exists():
                results['files_exist'] = False
                results['missing_files'].append(file_name)
        
        return results
    
    def install_dependencies(self) -> bool:
        """Install Python dependencies"""
        requirements_file = self.project_root / 'requirements.txt'
        
        try:
            print("Installing dependencies...")
            subprocess.run([
                sys.executable, '-m', 'pip', 'install', '-r', str(requirements_file)
            ], check=True)
            print("✓ Dependencies installed successfully")
            return True
        except subprocess.CalledProcessError as e:
            print(f"✗ Failed to install dependencies: {e}")
            return False
    
    def create_env_file(self) -> bool:
        """Create .env file from template if it doesn't exist"""
        env_file = self.project_root / '.env'
        env_example = self.project_root / '.env.example'
        
        if env_file.exists():
            print("✓ .env file already exists")
            return True
        
        if not env_example.exists():
            print("✗ .env.example file not found")
            return False
        
        try:
            # Copy example to .env
            with open(env_example, 'r') as src, open(env_file, 'w') as dst:
                dst.write(src.read())
            
            print("✓ Created .env file from template")
            print("❗ Please edit .env file with your actual configuration values")
            return True
        except Exception as e:
            print(f"✗ Failed to create .env file: {e}")
            return False
    
    def validate_configuration(self) -> Dict[str, Any]:
        """Validate configuration settings"""
        try:
            # Load environment variables from .env if it exists
            env_file = self.project_root / '.env'
            if env_file.exists():
                with open(env_file, 'r') as f:
                    for line in f:
                        if '=' in line and not line.startswith('#'):
                            key, value = line.strip().split('=', 1)
                            os.environ[key] = value
            
            # Import config to validate
            sys.path.insert(0, str(self.project_root))
            from gmail_push_config import GmailPushConfig
            
            missing_config = GmailPushConfig.validate_config()
            
            return {
                'valid': len(missing_config) == 0,
                'missing_config': missing_config
            }
        except Exception as e:
            return {
                'valid': False,
                'error': str(e)
            }
    
    def setup_gmail_watch(self, webhook_url: str) -> bool:
        """Setup Gmail watch configuration"""
        try:
            print(f"Setting up Gmail watch for webhook: {webhook_url}")
            
            result = subprocess.run([
                sys.executable, 'setup_gmail_watch.py',
                '--webhook-url', webhook_url,
                '--action', 'setup'
            ], capture_output=True, text=True, cwd=self.project_root)
            
            if result.returncode == 0:
                print("✓ Gmail watch setup successful")
                print(result.stdout)
                return True
            else:
                print("✗ Gmail watch setup failed")
                print(result.stderr)
                return False
        except Exception as e:
            print(f"✗ Error setting up Gmail watch: {e}")
            return False
    
    def start_webhook_server(self, port: int = 8080, production: bool = False) -> None:
        """Start the webhook server"""
        try:
            if production:
                print(f"Starting production server on port {port}...")
                subprocess.run([
                    sys.executable, '-m', 'gunicorn',
                    '-w', '4',
                    '-b', f'0.0.0.0:{port}',
                    'gmail_push_webhook:app'
                ], cwd=self.project_root)
            else:
                print(f"Starting development server on port {port}...")
                os.environ['WEBHOOK_PORT'] = str(port)
                subprocess.run([
                    sys.executable, 'gmail_push_webhook.py'
                ], cwd=self.project_root)
        except KeyboardInterrupt:
            print("\n✓ Server stopped")
        except Exception as e:
            print(f"✗ Error starting server: {e}")
    
    def run_tests(self) -> bool:
        """Run basic system tests"""
        print("Running system tests...")
        
        tests_passed = 0
        total_tests = 3
        
        # Test 1: Configuration validation
        try:
            config_result = self.validate_configuration()
            if config_result['valid']:
                print("✓ Configuration validation passed")
                tests_passed += 1
            else:
                print("✗ Configuration validation failed")
                print(f"  Missing: {config_result.get('missing_config', [])}")
        except Exception as e:
            print(f"✗ Configuration test error: {e}")
        
        # Test 2: Import all modules
        try:
            sys.path.insert(0, str(self.project_root))
            import gmail_push_config
            import gmail_push_webhook
            import security_utils
            import setup_gmail_watch
            print("✓ All modules imported successfully")
            tests_passed += 1
        except Exception as e:
            print(f"✗ Module import failed: {e}")
        
        # Test 3: Check service account file
        try:
            service_account_file = self.project_root / 'service-account.json'
            if service_account_file.exists():
                print("✓ Service account file found")
                tests_passed += 1
            else:
                print("✗ Service account file not found (service-account.json)")
        except Exception as e:
            print(f"✗ Service account check error: {e}")
        
        print(f"\nTests passed: {tests_passed}/{total_tests}")
        return tests_passed == total_tests

def main():
    """Main deployment function"""
    parser = argparse.ArgumentParser(description='Deploy Gmail Push Notification System')
    parser.add_argument('action', choices=['setup', 'install', 'configure', 'watch', 'start', 'test'],
                       help='Action to perform')
    parser.add_argument('--webhook-url', help='Webhook URL for Gmail watch setup')
    parser.add_argument('--port', type=int, default=8080, help='Server port')
    parser.add_argument('--production', action='store_true', help='Run in production mode')
    
    args = parser.parse_args()
    
    deployment = GmailPushDeployment()
    
    print("=== Gmail Push Notification Deployment ===\n")
    
    if args.action == 'setup':
        # Full setup process
        print("1. Checking prerequisites...")
        prereq_result = deployment.check_prerequisites()
        
        if not prereq_result['python_version_ok']:
            print("✗ Python 3.8+ required")
            return 1
        
        if not prereq_result['pip_available']:
            print("✗ pip not available")
            return 1
        
        if not prereq_result['files_exist']:
            print(f"✗ Missing files: {prereq_result['missing_files']}")
            return 1
        
        print("✓ Prerequisites check passed")
        
        print("\n2. Installing dependencies...")
        if not deployment.install_dependencies():
            return 1
        
        print("\n3. Creating configuration...")
        if not deployment.create_env_file():
            return 1
        
        print("\n4. Running tests...")
        if not deployment.run_tests():
            print("❗ Some tests failed. Please review configuration.")
        
        print("\n✓ Setup complete!")
        print("Next steps:")
        print("1. Edit .env file with your actual values")
        print("2. Place service-account.json in project directory")
        print("3. Run: python deploy.py configure")
        print("4. Run: python deploy.py watch --webhook-url YOUR_URL")
        print("5. Run: python deploy.py start")
    
    elif args.action == 'install':
        deployment.install_dependencies()
    
    elif args.action == 'configure':
        result = deployment.validate_configuration()
        if result['valid']:
            print("✓ Configuration is valid")
        else:
            print("✗ Configuration validation failed")
            if 'missing_config' in result:
                print(f"Missing: {result['missing_config']}")
            if 'error' in result:
                print(f"Error: {result['error']}")
            return 1
    
    elif args.action == 'watch':
        if not args.webhook_url:
            print("✗ --webhook-url required for watch setup")
            return 1
        deployment.setup_gmail_watch(args.webhook_url)
    
    elif args.action == 'start':
        deployment.start_webhook_server(args.port, args.production)
    
    elif args.action == 'test':
        if deployment.run_tests():
            print("\n✓ All tests passed")
            return 0
        else:
            print("\n✗ Some tests failed")
            return 1
    
    return 0

if __name__ == '__main__':
    exit(main())