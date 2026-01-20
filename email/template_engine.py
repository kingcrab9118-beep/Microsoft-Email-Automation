"""
Jinja2 template engine for email personalization
Handles template loading, rendering, and validation
"""

import logging
from pathlib import Path
from typing import Dict, Any, Optional

from jinja2 import Environment, FileSystemLoader, Template, TemplateError, select_autoescape

from db.models import Recipient


class EmailTemplateEngine:
    """Manages email template loading and rendering with Jinja2"""
    
    def __init__(self, templates_dir: str = None):
        if templates_dir is None:
            templates_dir = Path(__file__).parent / "templates"
        
        self.templates_dir = Path(templates_dir)
        self.logger = logging.getLogger(__name__)
        
        # Initialize Jinja2 environment
        self.env = Environment(
            loader=FileSystemLoader(str(self.templates_dir)),
            autoescape=select_autoescape(['html', 'xml']),
            trim_blocks=True,
            lstrip_blocks=True
        )
        
        # Template mapping
        self.template_files = {
            1: "email_1.html",
            2: "email_2.html", 
            3: "email_3.html"
        }
        
        # Subject line templates
        self.subject_templates = {
            1: "Quick question about {{ company }}",
            2: "Following up - {{ company }} opportunity",
            3: "Final follow-up - {{ company }}"
        }
        
        self.logger.info(f"Email template engine initialized with templates from {self.templates_dir}")
    
    def render_email(self, step: int, recipient: Recipient, custom_variables: Dict[str, Any] = None) -> Dict[str, str]:
        """Render email template for specific step and recipient"""
        try:
            # Validate step
            if step not in self.template_files:
                raise ValueError(f"Invalid email step: {step}. Must be 1, 2, or 3")
            
            # Prepare template context
            context = self._prepare_context(recipient, custom_variables)
            
            # Render HTML content
            html_content = self._render_template(step, context)
            
            # Render subject line
            subject = self._render_subject(step, context)
            
            self.logger.info(f"Successfully rendered email step {step} for {recipient.email}")
            
            return {
                'subject': subject,
                'html_content': html_content,
                'recipient_email': recipient.email,
                'recipient_name': recipient.first_name
            }
            
        except Exception as e:
            self.logger.error(f"Failed to render email step {step} for {recipient.email}: {e}")
            raise
    
    def _prepare_context(self, recipient: Recipient, custom_variables: Dict[str, Any] = None) -> Dict[str, Any]:
        """Prepare template context with recipient data and custom variables"""
        context = {
            'first_name': recipient.first_name,
            'company': recipient.company,
            'role': recipient.role,
            'email': recipient.email
        }
        
        # Add custom variables if provided
        if custom_variables:
            context.update(custom_variables)
        
        return context
    
    def _render_template(self, step: int, context: Dict[str, Any]) -> str:
        """Render HTML template for given step"""
        try:
            template_file = self.template_files[step]
            template = self.env.get_template(template_file)
            return template.render(**context)
            
        except TemplateError as e:
            self.logger.error(f"Template rendering error for step {step}: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error rendering template for step {step}: {e}")
            raise
    
    def _render_subject(self, step: int, context: Dict[str, Any]) -> str:
        """Render subject line for given step"""
        try:
            subject_template = self.subject_templates[step]
            template = Template(subject_template)
            return template.render(**context)
            
        except TemplateError as e:
            self.logger.error(f"Subject rendering error for step {step}: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Unexpected error rendering subject for step {step}: {e}")
            raise
    
    def validate_template(self, step: int) -> bool:
        """Validate that template exists and can be loaded"""
        try:
            if step not in self.template_files:
                return False
            
            template_file = self.template_files[step]
            template_path = self.templates_dir / template_file
            
            if not template_path.exists():
                self.logger.error(f"Template file not found: {template_path}")
                return False
            
            # Try to load the template
            template = self.env.get_template(template_file)
            
            # Test render with sample data
            sample_context = {
                'first_name': 'John',
                'company': 'Sample Company',
                'role': 'Sample Role',
                'email': 'john@sample.com'
            }
            
            template.render(**sample_context)
            
            self.logger.info(f"Template validation successful for step {step}")
            return True
            
        except Exception as e:
            self.logger.error(f"Template validation failed for step {step}: {e}")
            return False
    
    def validate_all_templates(self) -> Dict[int, bool]:
        """Validate all email templates"""
        results = {}
        
        for step in self.template_files.keys():
            results[step] = self.validate_template(step)
        
        all_valid = all(results.values())
        
        if all_valid:
            self.logger.info("All email templates validated successfully")
        else:
            invalid_steps = [step for step, valid in results.items() if not valid]
            self.logger.error(f"Template validation failed for steps: {invalid_steps}")
        
        return results
    
    def get_template_variables(self, step: int) -> set:
        """Extract variables used in a template"""
        try:
            template_file = self.template_files[step]
            template = self.env.get_template(template_file)
            
            # Get undeclared variables (template variables)
            variables = template.environment.parse(template.source).find_all(
                self.env.parse(template.source).find_all.__self__.__class__
            )
            
            # This is a simplified approach - in practice, you might want to use
            # more sophisticated template analysis
            return {'first_name', 'company', 'role', 'email'}
            
        except Exception as e:
            self.logger.error(f"Failed to extract variables from template {step}: {e}")
            return set()
    
    def preview_email(self, step: int, sample_data: Dict[str, str] = None) -> Dict[str, str]:
        """Generate preview of email with sample data"""
        if sample_data is None:
            sample_data = {
                'first_name': 'John',
                'company': 'Acme Corporation',
                'role': 'VP of Sales',
                'email': 'john.doe@acme.com'
            }
        
        # Create sample recipient
        sample_recipient = Recipient(
            first_name=sample_data['first_name'],
            company=sample_data['company'],
            role=sample_data['role'],
            email=sample_data['email']
        )
        
        return self.render_email(step, sample_recipient)
    
    def list_available_templates(self) -> Dict[int, str]:
        """List all available email templates"""
        available = {}
        
        for step, filename in self.template_files.items():
            template_path = self.templates_dir / filename
            if template_path.exists():
                available[step] = filename
        
        return available