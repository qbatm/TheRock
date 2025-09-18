# Gmail Push Notifications for TheRock Pipeline

This system replaces the polling-based email checking with real-time Gmail push notifications. When TheRock CI/CD sends completion emails, Gmail will automatically push notifications to your webhook, which then triggers the Jenkins pipeline.

## Architecture Overview

```
TheRock CI/CD → Gmail → Google Pub/Sub → Your Webhook → Jenkins Pipeline
```

## Features

- **Real-time notifications**: No more polling for emails
- **Security validation**: Rate limiting, GitHub verification, build number validation
- **Duplicate prevention**: Prevents processing the same email multiple times
- **Flexible configuration**: Environment-based configuration
- **Comprehensive logging**: Full audit trail of all operations

## Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Setup Configuration
```bash
python deploy.py setup
```

### 3. Configure Environment
Edit the `.env` file with your actual values:
- `GOOGLE_CLOUD_PROJECT_ID`
- `JENKINS_API_TOKEN`
- `WEBHOOK_SECRET`

### 4. Setup Gmail Watch
```bash
# Replace with your actual webhook URL
python deploy.py watch --webhook-url https://your-domain.com/webhook/gmail-push
```

### 5. Start Server
```bash
python deploy.py start
```

## Google Cloud Setup Required

### 1. Create Google Cloud Project
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Enable APIs:
   - Gmail API
   - Cloud Pub/Sub API

### 2. Create Service Account
1. Go to IAM & Admin → Service Accounts
2. Create service account with these roles:
   - Pub/Sub Admin
   - Project Editor
3. Generate JSON key file and save as `service-account.json`

### 3. Setup Domain-Wide Delegation
1. Enable "G Suite Domain-wide Delegation" for your service account
2. In Google Admin Console:
   - Go to Security → API Controls → Domain-wide Delegation
   - Add Client ID with scope: `https://www.googleapis.com/auth/gmail.readonly`

## File Structure

```
orchestrai_google_push/
├── gmail_push_config.py      # Configuration management
├── gmail_push_webhook.py     # Main webhook server
├── security_utils.py         # Security features
├── setup_gmail_watch.py      # Gmail watch configuration
├── deploy.py                 # Deployment helper
├── requirements.txt          # Dependencies
├── .env.example             # Configuration template
└── README.md                # This file
```

## Security Features

- **Rate Limiting**: Max 20 requests per 5-minute window
- **GitHub Verification**: Verify recent repository commits
- **Build Number Validation**: Ensure legitimate CI/CD emails
- **Webhook Signatures**: Request validation
- **Duplicate Prevention**: Prevent double-processing

## API Endpoints

- **POST** `/webhook/gmail-push` - Main Gmail notification webhook
- **GET** `/health` - Health check
- **POST** `/test` - Manual testing

## Configuration Options

| Variable | Required | Description |
|----------|----------|-------------|
| `GOOGLE_CLOUD_PROJECT_ID` | Yes | Google Cloud project ID |
| `JENKINS_API_TOKEN` | Yes | Jenkins API token |
| `WEBHOOK_SECRET` | Yes | Webhook validation secret |
| `GMAIL_USER_EMAIL` | No | Gmail address to monitor |
| `EMAIL_SUBJECT_FILTER` | No | Subject filter (default: "TheRock Pipeline") |
| `ENABLE_GITHUB_VERIFICATION` | No | Enable GitHub verification |
| `GITHUB_TOKEN` | No* | Required if GitHub verification enabled |

## Migration from get_latest_email.py

This system replaces the polling script with real-time notifications:

**Old (Polling)**:
- Checks emails every few minutes
- Uses IMAP authentication
- Manual script execution
- Higher resource usage

**New (Push)**:
- Instant email notifications
- OAuth2 service account
- Automatic pipeline triggers
- Event-driven efficiency

## Deployment Options

### Development
```bash
python deploy.py start
```

### Production with Gunicorn
```bash
python deploy.py start --production --port 8080
```

### Docker Deployment
```dockerfile
FROM python:3.9-slim
WORKDIR /app
COPY . .
RUN pip install -r requirements.txt
EXPOSE 8080
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:8080", "gmail_push_webhook:app"]
```

## Troubleshooting

### Common Issues
1. **Gmail API Authentication**: Check domain-wide delegation setup
2. **Pub/Sub Permissions**: Verify service account roles
3. **Jenkins Integration**: Validate API token and job name
4. **Rate Limiting**: Check IP-based limits in logs

### Testing
```bash
# Test configuration
python deploy.py configure

# Test all components
python deploy.py test

# Manual webhook test
curl -X POST http://localhost:8080/test
```

## Monitoring

The system provides comprehensive logging for:
- Email processing events
- Security validation results
- Jenkins pipeline triggers
- Error conditions and debugging

Check logs for detailed operation tracking and troubleshooting information.