#!/bin/bash
# Installation script for Microsoft 365 Email Automation System
# Supports Ubuntu/Debian and CentOS/RHEL

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
APP_USER="emailautomation"
APP_DIR="/home/$APP_USER/email_automation"
SERVICE_NAME="email-automation"
PYTHON_VERSION="3.10"

# Functions
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

detect_os() {
    if [[ -f /etc/os-release ]]; then
        . /etc/os-release
        OS=$ID
        VERSION=$VERSION_ID
    else
        log_error "Cannot detect operating system"
        exit 1
    fi
    
    log_info "Detected OS: $OS $VERSION"
}

check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "This script must be run as root"
        exit 1
    fi
}

install_dependencies_ubuntu() {
    log_info "Installing dependencies for Ubuntu/Debian..."
    
    apt-get update
    apt-get install -y \
        software-properties-common \
        curl \
        wget \
        git \
        unzip \
        python3.10 \
        python3.10-venv \
        python3.10-dev \
        python3-pip \
        build-essential \
        libssl-dev \
        libffi-dev \
        unixodbc-dev
    
    # Install Microsoft ODBC Driver
    curl https://packages.microsoft.com/keys/microsoft.asc | apt-key add -
    curl https://packages.microsoft.com/config/ubuntu/$(lsb_release -rs)/prod.list > /etc/apt/sources.list.d/mssql-release.list
    apt-get update
    ACCEPT_EULA=Y apt-get install -y msodbcsql17
}

install_dependencies_centos() {
    log_info "Installing dependencies for CentOS/RHEL..."
    
    yum update -y
    yum install -y \
        epel-release \
        curl \
        wget \
        git \
        unzip \
        python3 \
        python3-pip \
        python3-devel \
        gcc \
        gcc-c++ \
        make \
        openssl-devel \
        libffi-devel \
        unixODBC-devel
    
    # Install Microsoft ODBC Driver
    curl https://packages.microsoft.com/config/rhel/8/prod.repo > /etc/yum.repos.d/mssql-release.repo
    yum remove -y unixODBC-utf16 unixODBC-utf16-devel
    ACCEPT_EULA=Y yum install -y msodbcsql17
}

create_user() {
    log_info "Creating application user: $APP_USER"
    
    if id "$APP_USER" &>/dev/null; then
        log_warning "User $APP_USER already exists"
    else
        useradd -m -s /bin/bash "$APP_USER"
        log_success "Created user $APP_USER"
    fi
}

setup_application() {
    log_info "Setting up application..."
    
    # Create application directory
    if [[ ! -d "$APP_DIR" ]]; then
        mkdir -p "$APP_DIR"
        chown "$APP_USER:$APP_USER" "$APP_DIR"
    fi
    
    # Switch to app user for setup
    sudo -u "$APP_USER" bash << EOF
cd "$APP_DIR"

# Clone repository (if not already present)
if [[ ! -f "main.py" ]]; then
    log_info "Please copy the application files to $APP_DIR"
    exit 1
fi

# Create virtual environment
if [[ ! -d "venv" ]]; then
    python3.10 -m venv venv
    log_success "Created virtual environment"
fi

# Activate virtual environment and install dependencies
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
log_success "Installed Python dependencies"

# Create configuration file if it doesn't exist
if [[ ! -f ".env" ]]; then
    cp .env.example .env
    log_warning "Created .env file from template. Please configure it before starting the service."
fi

# Create log directory
mkdir -p logs
EOF
}

install_systemd_service() {
    log_info "Installing systemd service..."
    
    # Copy service file
    if [[ -f "deployment/systemd/$SERVICE_NAME.service" ]]; then
        cp "deployment/systemd/$SERVICE_NAME.service" "/etc/systemd/system/"
        
        # Reload systemd
        systemctl daemon-reload
        
        # Enable service
        systemctl enable "$SERVICE_NAME"
        
        log_success "Installed and enabled systemd service"
    else
        log_error "Service file not found: deployment/systemd/$SERVICE_NAME.service"
        exit 1
    fi
}

setup_firewall() {
    log_info "Configuring firewall..."
    
    # Check if ufw is available (Ubuntu)
    if command -v ufw &> /dev/null; then
        # Allow SSH
        ufw allow ssh
        
        # Allow monitoring port (optional)
        ufw allow 8080/tcp comment "Email Automation Monitoring"
        
        # Enable firewall
        ufw --force enable
        
        log_success "Configured UFW firewall"
    
    # Check if firewalld is available (CentOS/RHEL)
    elif command -v firewall-cmd &> /dev/null; then
        # Allow monitoring port
        firewall-cmd --permanent --add-port=8080/tcp
        firewall-cmd --reload
        
        log_success "Configured firewalld"
    else
        log_warning "No firewall management tool found. Please configure firewall manually."
    fi
}

create_backup_script() {
    log_info "Creating backup script..."
    
    cat > "/usr/local/bin/backup-email-automation" << 'EOF'
#!/bin/bash
# Backup script for Email Automation System

BACKUP_DIR="/var/backups/email-automation"
APP_DIR="/home/emailautomation/email_automation"
DATE=$(date +%Y%m%d_%H%M%S)

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Backup database
if [[ -f "$APP_DIR/email_automation.db" ]]; then
    cp "$APP_DIR/email_automation.db" "$BACKUP_DIR/email_automation_$DATE.db"
    echo "Database backed up to $BACKUP_DIR/email_automation_$DATE.db"
fi

# Backup configuration
if [[ -f "$APP_DIR/.env" ]]; then
    cp "$APP_DIR/.env" "$BACKUP_DIR/env_$DATE.backup"
    echo "Configuration backed up to $BACKUP_DIR/env_$DATE.backup"
fi

# Backup logs
if [[ -d "$APP_DIR/logs" ]]; then
    tar -czf "$BACKUP_DIR/logs_$DATE.tar.gz" -C "$APP_DIR" logs/
    echo "Logs backed up to $BACKUP_DIR/logs_$DATE.tar.gz"
fi

# Clean old backups (keep last 7 days)
find "$BACKUP_DIR" -name "*.db" -mtime +7 -delete
find "$BACKUP_DIR" -name "*.backup" -mtime +7 -delete
find "$BACKUP_DIR" -name "*.tar.gz" -mtime +7 -delete

echo "Backup completed: $DATE"
EOF

    chmod +x "/usr/local/bin/backup-email-automation"
    
    # Add to crontab for daily backups
    (crontab -l 2>/dev/null; echo "0 2 * * * /usr/local/bin/backup-email-automation") | crontab -
    
    log_success "Created backup script and scheduled daily backups"
}

setup_log_rotation() {
    log_info "Setting up log rotation..."
    
    cat > "/etc/logrotate.d/email-automation" << EOF
$APP_DIR/logs/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    create 644 $APP_USER $APP_USER
    postrotate
        systemctl reload $SERVICE_NAME > /dev/null 2>&1 || true
    endscript
}
EOF
    
    log_success "Configured log rotation"
}

print_next_steps() {
    log_success "Installation completed successfully!"
    echo
    echo "Next steps:"
    echo "1. Configure the application:"
    echo "   sudo -u $APP_USER nano $APP_DIR/.env"
    echo
    echo "2. Validate configuration:"
    echo "   sudo -u $APP_USER bash -c 'cd $APP_DIR && source venv/bin/activate && python main.py validate'"
    echo
    echo "3. Start the service:"
    echo "   systemctl start $SERVICE_NAME"
    echo
    echo "4. Check service status:"
    echo "   systemctl status $SERVICE_NAME"
    echo
    echo "5. View logs:"
    echo "   journalctl -u $SERVICE_NAME -f"
    echo
    echo "6. Enable monitoring (optional):"
    echo "   sudo -u $APP_USER bash -c 'cd $APP_DIR && source venv/bin/activate && python monitoring.py'"
    echo
    log_info "For more information, see the README.md file"
}

# Main installation process
main() {
    log_info "Starting Email Automation System installation..."
    
    check_root
    detect_os
    
    case $OS in
        ubuntu|debian)
            install_dependencies_ubuntu
            ;;
        centos|rhel|fedora)
            install_dependencies_centos
            ;;
        *)
            log_error "Unsupported operating system: $OS"
            exit 1
            ;;
    esac
    
    create_user
    setup_application
    install_systemd_service
    setup_firewall
    create_backup_script
    setup_log_rotation
    
    print_next_steps
}

# Run main function
main "$@"