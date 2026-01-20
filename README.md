# Microsoft 365 Email Automation System

A production-ready Python system for sending personalized cold emails with automated follow-up sequences using Microsoft Graph API. The system automatically detects replies and stops further emails to prevent spam.

## 🚀 Features

- **Personalized Email Sequences**: Send customized cold emails with Jinja2 templates
- **Automated Follow-ups**: 3-step email sequence with configurable timing
- **Reply Detection**: Automatically stops sequences when recipients reply
- **Rate Limiting**: Respects Microsoft 365 sending limits with adaptive controls
- **Scalable Architecture**: From small tests to thousands of recipients
- **Production Ready**: Comprehensive error handling, logging, and monitoring

## 📋 Requirements

- Python 3.10+
- Microsoft 365 account with admin access
- Azure App Registration with appropriate permissions

## 🛠️ Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd email_automation
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration (see Configuration section)
   ```

## ⚙️ Configuration

### Azure App Registration Setup

1. **Create App Registration**
   - Go to [Azure Portal](https://portal.azure.com)
   - Navigate to "Azure Active Directory" > "App registrations"
   - Click "New registration"
   - Name: "Email Automation System"
   - Account types: "Accounts in this organizational directory only"
   - Click "Register"

2. **Configure API Permissions**
   - Go to "API permissions"
   - Click "Add a permission" > "Microsoft Graph"
   - Add these **Application permissions**:
     - `Mail.Send` - Send emails
     - `Mail.Read` - Read mailbox for reply detection
   - Click "Grant admin consent" (required!)

3. **Create Client Secret**
   - Go to "Certificates & secrets"
   - Click "New client secret"
   - Description: "Email Automation Secret"
   - Expiration: Choose appropriate duration
   - **Copy the secret value immediately** (you won't see it again!)

4. **Get Configuration Values**
   - **Tenant ID**: Found in "Overview" section
   - **Client ID**: Found in "Overview" section (Application ID)
   - **Client Secret**: The value you copied above

### Environment Configuration

Edit your `.env` file with the values from Azure:

```env
# Microsoft Graph API Configuration
MICROSOFT_TENANT_ID=your-tenant-id-here
MICROSOFT_CLIENT_ID=your-client-id-here
MICROSOFT_CLIENT_SECRET=your-client-secret-here
SENDER_EMAIL=sender@yourdomain.com

# Authentication method
AUTH_METHOD=client_credentials

# Database (SQLite default)
DATABASE_URL=sqlite:///email_automation.db

# Rate Limiting
RATE_LIMIT_PER_MINUTE=30
RATE_LIMIT_PER_DAY=10000

# Email Sequence Timing
FOLLOW_UP_1_DELAY_DAYS=14
FOLLOW_UP_2_ENABLED=true
FOLLOW_UP_2_DELAY_DAYS=10

# Reply Detection
REPLY_CHECK_INTERVAL_MINUTES=15
```

## 🚦 Quick Start

### 1. Validate Configuration
```bash
python main.py validate
```
This will check your configuration and test authentication.

### 2. Send Test Email
```bash
python main.py test-email "your-email@example.com"
```

### 3. Add Recipients
```bash
# Add single recipient
python main.py add-recipient "John" "Acme Corp" "CEO" "john@acme.com"

# Or bulk import from CSV
python cli_tools.py create-sample  # Creates sample CSV
python cli_tools.py bulk-import recipients.csv
```

### 4. Start the System
```bash
python main.py run
```

### 5. Monitor Status
```bash
python main.py status
```

## 📧 Email Sequence

The system sends a 3-step email sequence:

1. **Initial Email** - Sent immediately after adding recipient
2. **Follow-up 1** - Sent 14 days after initial email (configurable)
3. **Follow-up 2** - Sent 10-11 days after follow-up 1 (optional, configurable)

**Automatic Stop Conditions:**
- Recipient replies to any email
- Recipient is manually stopped
- System detects auto-reply/out-of-office

## 🎨 Email Templates

Templates are located in `email/templates/` and use Jinja2 syntax:

- `email_1.html` - Initial outreach email
- `email_2.html` - First follow-up
- `email_3.html` - Final follow-up

**Available Variables:**
- `{{ first_name }}` - Recipient's first name
- `{{ company }}` - Company name
- `{{ role }}` - Job title/role

**Customizing Templates:**
1. Edit the HTML files in `email/templates/`
2. Use the available variables for personalization
3. Test with: `python main.py test-email "test@example.com"`

## 📊 Monitoring & Analytics

### System Status
```bash
python main.py status
```

### Analytics Report
```bash
python cli_tools.py analytics
python cli_tools.py analytics --output report.json
```

### Health Check
```bash
python integration_tests.py --health-check
```

### Export Data
```bash
python cli_tools.py export recipients.csv
```

## 🔧 Advanced Usage

### Bulk Operations

**Import from CSV:**
```bash
# Create sample CSV template
python cli_tools.py create-sample

# Import recipients
python cli_tools.py bulk-import recipients.csv
```

**CSV Format:**
```csv
first_name,company,role,email
John,Acme Corp,CEO,john@acme.com
Jane,Tech Solutions,VP Sales,jane@techsolutions.com
```

### Database Management

**SQLite (Default):**
- Database file: `email_automation.db`
- Automatic schema creation and migrations
- Suitable for up to 10,000 recipients

**Azure SQL (Production):**
```env
DATABASE_URL=mssql+pyodbc://username:password@server/database?driver=ODBC+Driver+17+for+SQL+Server
```

### Rate Limiting

The system includes adaptive rate limiting:
- **Default**: 30 emails/minute, 10,000/day
- **Adaptive**: Automatically adjusts based on API responses
- **Backoff**: Exponential backoff on errors

Configure in `.env`:
```env
RATE_LIMIT_PER_MINUTE=30
RATE_LIMIT_PER_DAY=10000
```

## 🛡️ Security Best Practices

1. **Environment Variables**: Never commit `.env` file
2. **Permissions**: Use least-privilege principle
3. **Secrets**: Rotate client secrets regularly
4. **Access**: Limit who can access the system
5. **Monitoring**: Monitor for unusual activity

## 🔍 Troubleshooting

### Common Issues

**Authentication Errors:**
```
AADSTS70011: The provided request must include a 'scope' parameter
```
- **Solution**: Ensure you're using `client_credentials` auth method
- **Check**: Verify scopes in configuration

**Permission Errors:**
```
AADSTS65001: The user or administrator has not consented
```
- **Solution**: Grant admin consent in Azure Portal
- **Path**: App Registration > API Permissions > Grant admin consent

**Rate Limiting:**
```
Rate limit exceeded
```
- **Solution**: System handles automatically with backoff
- **Check**: Monitor rate limiting in logs

**Database Errors:**
```
Database connection failed
```
- **Solution**: Check database URL and permissions
- **SQLite**: Ensure directory is writable

### Debug Mode

Run with debug logging:
```bash
python main.py --log-level DEBUG run
```

### Integration Tests

Run comprehensive tests:
```bash
python integration_tests.py
```

## 📈 Scaling Considerations

### Small Scale (< 100 recipients)
- SQLite database
- Single instance
- Default rate limits

### Medium Scale (100-1,000 recipients)
- SQLite or Azure SQL
- Monitor rate limits
- Consider dedicated server

### Large Scale (1,000+ recipients)
- Azure SQL database
- Multiple instances with shared database
- Custom rate limiting
- Load balancing

## 🔄 Maintenance

### Regular Tasks

**Daily:**
- Monitor system status
- Check error logs
- Review reply rates

**Weekly:**
- Export analytics
- Review template performance
- Update recipient lists

**Monthly:**
- Rotate secrets
- Update dependencies
- Review scaling needs

### Backup Strategy

**Database Backup:**
```bash
# SQLite
cp email_automation.db backup_$(date +%Y%m%d).db

# Azure SQL
# Use Azure backup features
```

**Configuration Backup:**
- Store `.env.example` in version control
- Document any custom configurations
- Backup email templates

## 🤝 Support

### Getting Help

1. **Check Documentation**: Review this README thoroughly
2. **Run Diagnostics**: Use `python main.py validate`
3. **Check Logs**: Review `email_automation.log`
4. **Test Components**: Run `python integration_tests.py`

### Reporting Issues

When reporting issues, include:
- Error messages from logs
- Configuration (without secrets)
- Steps to reproduce
- System information

## 📄 License

[Add your license information here]

## 🔗 Additional Resources

- [Microsoft Graph API Documentation](https://docs.microsoft.com/en-us/graph/)
- [Azure App Registration Guide](https://docs.microsoft.com/en-us/azure/active-directory/develop/quickstart-register-app)
- [Email Best Practices](https://docs.microsoft.com/en-us/microsoft-365/compliance/email-best-practices)

---

**⚠️ Important**: This system is for legitimate business outreach only. Ensure compliance with:
- CAN-SPAM Act
- GDPR (if applicable)
- Your organization's email policies
- Recipient consent requirements