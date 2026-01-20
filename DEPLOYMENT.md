# Deployment Guide

This guide covers deploying the Microsoft 365 Email Automation System in various environments.

## 🏗️ Deployment Options

### 1. Local Development
- **Use Case**: Testing, development, small-scale usage
- **Database**: SQLite
- **Scale**: < 100 recipients

### 2. Single Server Production
- **Use Case**: Small to medium business
- **Database**: SQLite or Azure SQL
- **Scale**: 100-1,000 recipients

### 3. Cloud Production (Azure)
- **Use Case**: Enterprise deployment
- **Database**: Azure SQL
- **Scale**: 1,000+ recipients

## 🖥️ Local Development Deployment

### Prerequisites
- Python 3.10+
- Git
- Text editor

### Steps
1. **Clone and Setup**
   ```bash
   git clone <repository-url>
   cd email_automation
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Configure Environment**
   ```bash
   cp .env.example .env
   # Edit .env with your Azure configuration
   ```

3. **Validate Setup**
   ```bash
   python main.py validate
   ```

4. **Run System**
   ```bash
   python main.py run
   ```

## 🖥️ Single Server Production

### Server Requirements
- **OS**: Ubuntu 20.04+ or Windows Server 2019+
- **RAM**: 2GB minimum, 4GB recommended
- **Storage**: 10GB minimum
- **Network**: Outbound HTTPS (443) access

### Installation Steps

#### Ubuntu/Debian
```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Python 3.10+
sudo apt install python3.10 python3.10-venv python3-pip -y

# Create application user
sudo useradd -m -s /bin/bash emailautomation
sudo su - emailautomation

# Clone application
git clone <repository-url> email_automation
cd email_automation

# Setup virtual environment
python3.10 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with production values
```

#### Windows Server
```powershell
# Install Python 3.10+ from python.org
# Clone repository
git clone <repository-url> C:\EmailAutomation
cd C:\EmailAutomation

# Setup virtual environment
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

# Configure environment
copy .env.example .env
# Edit .env with production values
```

### Service Configuration

#### Linux (systemd)
Create `/etc/systemd/system/email-automation.service`:
```ini
[Unit]
Description=Email Automation System
After=network.target

[Service]
Type=simple
User=emailautomation
WorkingDirectory=/home/emailautomation/email_automation
Environment=PATH=/home/emailautomation/email_automation/venv/bin
ExecStart=/home/emailautomation/email_automation/venv/bin/python main.py run
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable email-automation
sudo systemctl start email-automation
sudo systemctl status email-automation
```

#### Windows (Service)
Create `install_service.py`:
```python
import win32serviceutil
import win32service
import win32event
import subprocess
import os

class EmailAutomationService(win32serviceutil.ServiceFramework):
    _svc_name_ = "EmailAutomation"
    _svc_display_name_ = "Email Automation System"
    _svc_description_ = "Microsoft 365 Email Automation System"

    def __init__(self, args):
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
        self.process = None

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        if self.process:
            self.process.terminate()
        win32event.SetEvent(self.hWaitStop)

    def SvcDoRun(self):
        os.chdir(r'C:\EmailAutomation')
        self.process = subprocess.Popen([
            r'C:\EmailAutomation\venv\Scripts\python.exe',
            'main.py', 'run'
        ])
        win32event.WaitForSingleObject(self.hWaitStop, win32event.INFINITE)

if __name__ == '__main__':
    win32serviceutil.HandleCommandLine(EmailAutomationService)
```

Install service:
```powershell
python install_service.py install
python install_service.py start
```

## ☁️ Azure Cloud Deployment

### Architecture Overview
```
Internet → Azure Load Balancer → VM Scale Set → Azure SQL Database
                                      ↓
                              Azure Storage (Logs)
```

### Azure Resources Needed
- **Resource Group**
- **Virtual Machine or App Service**
- **Azure SQL Database**
- **Key Vault** (for secrets)
- **Storage Account** (for logs)
- **Application Insights** (monitoring)

### Azure SQL Database Setup

1. **Create Azure SQL Database**
   ```bash
   az sql server create \
     --name emailautomation-sql \
     --resource-group emailautomation-rg \
     --location eastus \
     --admin-user sqladmin \
     --admin-password <strong-password>

   az sql db create \
     --resource-group emailautomation-rg \
     --server emailautomation-sql \
     --name emailautomation \
     --service-objective Basic
   ```

2. **Configure Firewall**
   ```bash
   az sql server firewall-rule create \
     --resource-group emailautomation-rg \
     --server emailautomation-sql \
     --name AllowAzureServices \
     --start-ip-address 0.0.0.0 \
     --end-ip-address 0.0.0.0
   ```

3. **Update Connection String**
   ```env
   DATABASE_URL=mssql+pyodbc://sqladmin:<password>@emailautomation-sql.database.windows.net/emailautomation?driver=ODBC+Driver+17+for+SQL+Server
   ```

### Azure Key Vault Integration

1. **Create Key Vault**
   ```bash
   az keyvault create \
     --name emailautomation-kv \
     --resource-group emailautomation-rg \
     --location eastus
   ```

2. **Store Secrets**
   ```bash
   az keyvault secret set --vault-name emailautomation-kv --name "microsoft-tenant-id" --value "<tenant-id>"
   az keyvault secret set --vault-name emailautomation-kv --name "microsoft-client-id" --value "<client-id>"
   az keyvault secret set --vault-name emailautomation-kv --name "microsoft-client-secret" --value "<client-secret>"
   ```

3. **Update Application** (add to requirements.txt):
   ```
   azure-keyvault-secrets
   azure-identity
   ```

4. **Modify config.py**:
   ```python
   from azure.keyvault.secrets import SecretClient
   from azure.identity import DefaultAzureCredential

   class Config:
       def __init__(self):
           if os.getenv('AZURE_KEY_VAULT_URL'):
               self._load_from_keyvault()
           else:
               self._load_from_env()
       
       def _load_from_keyvault(self):
           credential = DefaultAzureCredential()
           client = SecretClient(
               vault_url=os.getenv('AZURE_KEY_VAULT_URL'),
               credential=credential
           )
           
           self.microsoft_tenant_id = client.get_secret("microsoft-tenant-id").value
           # ... other secrets
   ```

### VM Deployment

1. **Create VM**
   ```bash
   az vm create \
     --resource-group emailautomation-rg \
     --name emailautomation-vm \
     --image UbuntuLTS \
     --admin-username azureuser \
     --generate-ssh-keys \
     --size Standard_B2s
   ```

2. **Configure VM**
   ```bash
   # SSH to VM
   ssh azureuser@<vm-ip>
   
   # Install dependencies
   sudo apt update
   sudo apt install python3.10 python3.10-venv git -y
   
   # Deploy application (same as single server steps)
   ```

### App Service Deployment

1. **Create App Service Plan**
   ```bash
   az appservice plan create \
     --name emailautomation-plan \
     --resource-group emailautomation-rg \
     --sku B1 \
     --is-linux
   ```

2. **Create Web App**
   ```bash
   az webapp create \
     --resource-group emailautomation-rg \
     --plan emailautomation-plan \
     --name emailautomation-app \
     --runtime "PYTHON|3.10"
   ```

3. **Configure App Settings**
   ```bash
   az webapp config appsettings set \
     --resource-group emailautomation-rg \
     --name emailautomation-app \
     --settings \
       MICROSOFT_TENANT_ID="<tenant-id>" \
       MICROSOFT_CLIENT_ID="<client-id>" \
       MICROSOFT_CLIENT_SECRET="<client-secret>"
   ```

4. **Deploy Code**
   ```bash
   az webapp deployment source config \
     --resource-group emailautomation-rg \
     --name emailautomation-app \
     --repo-url <your-git-repo> \
     --branch main \
     --manual-integration
   ```

## 🔒 Security Configuration

### Network Security
- **Firewall**: Allow only necessary ports (443 for HTTPS)
- **VPN**: Consider VPN access for management
- **Private Endpoints**: Use Azure Private Endpoints for database

### Application Security
- **Secrets Management**: Use Azure Key Vault or similar
- **HTTPS Only**: Enforce HTTPS for all communications
- **Authentication**: Secure admin interfaces
- **Logging**: Enable comprehensive logging

### Database Security
- **Encryption**: Enable encryption at rest and in transit
- **Access Control**: Use least-privilege access
- **Backup**: Regular automated backups
- **Monitoring**: Enable threat detection

## 📊 Monitoring & Logging

### Application Insights (Azure)
```python
# Add to requirements.txt
opencensus-ext-azure
opencensus-ext-logging

# Add to main.py
from opencensus.ext.azure.log_exporter import AzureLogHandler
import logging

logger = logging.getLogger(__name__)
logger.addHandler(AzureLogHandler(
    connection_string='InstrumentationKey=<your-key>'
))
```

### Log Management
- **Centralized Logging**: Use Azure Monitor or ELK stack
- **Log Rotation**: Configure log rotation
- **Alerting**: Set up alerts for errors

### Health Checks
```bash
# Add health check endpoint
curl http://localhost:8000/health

# Monitor with external service
# - Azure Application Insights
# - Pingdom
# - StatusCake
```

## 🔄 Backup & Recovery

### Database Backup
```bash
# Azure SQL - Automated backups enabled by default
# Manual backup
az sql db export \
  --resource-group emailautomation-rg \
  --server emailautomation-sql \
  --name emailautomation \
  --admin-user sqladmin \
  --admin-password <password> \
  --storage-key <storage-key> \
  --storage-key-type StorageAccessKey \
  --storage-uri https://storage.blob.core.windows.net/backups/backup.bacpac
```

### Application Backup
- **Code**: Version control (Git)
- **Configuration**: Secure configuration backup
- **Logs**: Archive old logs to storage

### Disaster Recovery
1. **RTO/RPO**: Define recovery objectives
2. **Backup Testing**: Regular restore testing
3. **Documentation**: Maintain recovery procedures
4. **Automation**: Automate recovery processes

## 🚀 Performance Optimization

### Database Optimization
- **Indexing**: Ensure proper indexes
- **Connection Pooling**: Use connection pooling
- **Query Optimization**: Monitor slow queries

### Application Optimization
- **Async Operations**: Use async/await properly
- **Memory Management**: Monitor memory usage
- **Rate Limiting**: Optimize rate limiting settings

### Infrastructure Optimization
- **Scaling**: Implement auto-scaling
- **Caching**: Add caching where appropriate
- **CDN**: Use CDN for static assets

## 📋 Deployment Checklist

### Pre-Deployment
- [ ] Azure App Registration configured
- [ ] Permissions granted and consented
- [ ] Environment variables configured
- [ ] Database connection tested
- [ ] Email templates customized
- [ ] Rate limits configured appropriately

### Deployment
- [ ] Application deployed
- [ ] Service/daemon configured
- [ ] Database initialized
- [ ] Health checks passing
- [ ] Monitoring configured
- [ ] Backups configured

### Post-Deployment
- [ ] Send test emails
- [ ] Monitor logs for errors
- [ ] Verify reply detection
- [ ] Test sequence workflows
- [ ] Document any customizations
- [ ] Train operators

### Production Readiness
- [ ] Load testing completed
- [ ] Security review passed
- [ ] Monitoring alerts configured
- [ ] Backup/recovery tested
- [ ] Documentation updated
- [ ] Support procedures defined

## 🆘 Troubleshooting Deployment

### Common Issues

**Service Won't Start**
```bash
# Check logs
journalctl -u email-automation -f

# Check permissions
ls -la /home/emailautomation/email_automation/
```

**Database Connection Issues**
```bash
# Test connection
python -c "from db.database import DatabaseManager; import asyncio; asyncio.run(DatabaseManager('your-connection-string').initialize())"
```

**Authentication Failures**
```bash
# Validate configuration
python main.py validate
```

**Performance Issues**
- Monitor CPU/memory usage
- Check database performance
- Review rate limiting settings
- Analyze application logs

For additional support, refer to the main README.md troubleshooting section.