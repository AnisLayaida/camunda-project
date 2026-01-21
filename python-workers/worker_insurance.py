#!/usr/bin/env python3
"""
Insurance Process External Task Worker

Handles external tasks for the insurance application workflow.

External Tasks handled by this worker (matching BPMN topics):
- send-approval-email: Send approval notification to policyholder (Green path + Yellow approved)
- send-rejection-email: Send rejection notification to policyholder (Red path + Yellow rejected)  
- inform-manager: Notify manager when application takes > 2 days (Timer boundary event)
- request-documents-email: Send document request to applicant (Document subprocess)
- send-auto-rejection-email: Auto-reject when documents not received (Document subprocess timeout)
"""

import logging
import time
import os
import sys
import json
from datetime import datetime
from typing import Dict, Any, Optional, List
import requests
from requests.exceptions import RequestException

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger('insurance-worker')

# =============================================================================
# CONFIGURATION
# =============================================================================
CAMUNDA_URL = os.getenv('CAMUNDA_URL', 'http://localhost:8080/engine-rest')
CAMUNDA_USERNAME = os.getenv('CAMUNDA_USERNAME', '')
CAMUNDA_PASSWORD = os.getenv('CAMUNDA_PASSWORD', '')
WORKER_ID = os.getenv('WORKER_ID', f'insurance-worker-{os.getpid()}')
LOCK_DURATION = int(os.getenv('LOCK_DURATION', '300000'))
POLL_INTERVAL = int(os.getenv('POLL_INTERVAL', '5'))
MAX_TASKS = int(os.getenv('MAX_TASKS', '5'))

# Email Configuration
EMAIL_ENABLED = os.getenv('EMAIL_ENABLED', 'false').lower() == 'true'
SMTP_HOST = os.getenv('SMTP_HOST', 'localhost')
SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))
SMTP_USERNAME = os.getenv('SMTP_USERNAME', '')
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD', '')
EMAIL_FROM = os.getenv('EMAIL_FROM', 'noreply@insurance-company.com')
MANAGER_EMAIL = os.getenv('MANAGER_EMAIL', 'manager@insurance-company.com')

# =============================================================================
# TOPIC DEFINITIONS - MUST MATCH BPMN camunda:topic attributes
# =============================================================================
TOPICS = [
    {
        'topicName': 'send-approval-email',
        'lockDuration': LOCK_DURATION,
        'variables': ['applicantName', 'applicantEmail', 'rating', 'carMake', 'carModel']
    },
    {
        'topicName': 'send-rejection-email', 
        'lockDuration': LOCK_DURATION,
        'variables': ['applicantName', 'applicantEmail', 'rating', 'rejectionReason']
    },
    {
        'topicName': 'inform-manager',
        'lockDuration': LOCK_DURATION,
        'variables': ['applicantName', 'applicantEmail', 'rating', 'age', 'carMake', 'carModel']
    },
    {
        'topicName': 'request-documents-email',
        'lockDuration': LOCK_DURATION,
        'variables': ['applicantName', 'applicantEmail', 'missingDocuments']
    },
    {
        'topicName': 'send-auto-rejection-email',
        'lockDuration': LOCK_DURATION,
        'variables': ['applicantName', 'applicantEmail']
    }
]


# =============================================================================
# EMAIL SERVICE (Mock when EMAIL_ENABLED=false)
# =============================================================================
class EmailService:
    """Handles email sending with mock mode for testing."""
    
    def __init__(self):
        self.enabled = EMAIL_ENABLED
        logger.info(f"Email Service initialized - Mode: {'LIVE' if self.enabled else 'MOCK'}")
    
    def send_email(self, to: str, subject: str, body: str) -> bool:
        """Send email or log mock email."""
        if not self.enabled:
            logger.info("=" * 60)
            logger.info("[MOCK EMAIL]")
            logger.info(f"  To: {to}")
            logger.info(f"  Subject: {subject}")
            logger.info(f"  Body Preview: {body[:200]}...")
            logger.info("=" * 60)
            return True
        
        # Real email sending would go here
        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart
            
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = EMAIL_FROM
            msg['To'] = to
            msg.attach(MIMEText(body, 'html'))
            
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
                server.starttls()
                if SMTP_USERNAME and SMTP_PASSWORD:
                    server.login(SMTP_USERNAME, SMTP_PASSWORD)
                server.sendmail(EMAIL_FROM, to, msg.as_string())
            
            logger.info(f"Email sent successfully to {to}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email to {to}: {e}")
            return False


# =============================================================================
# CAMUNDA CLIENT
# =============================================================================
class CamundaClient:
    """Client for Camunda REST API interactions."""
    
    def __init__(self, base_url: str, worker_id: str):
        self.base_url = base_url.rstrip('/')
        self.worker_id = worker_id
        self.session = requests.Session()
        
        # Setup authentication if provided
        if CAMUNDA_USERNAME and CAMUNDA_PASSWORD:
            self.session.auth = (CAMUNDA_USERNAME, CAMUNDA_PASSWORD)
            logger.info("Using Basic Authentication")
        
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        })
    
    def fetch_and_lock(self, topics: List[Dict], max_tasks: int = 5) -> List[Dict]:
        """Fetch and lock external tasks from Camunda."""
        url = f"{self.base_url}/external-task/fetchAndLock"
        payload = {
            'workerId': self.worker_id,
            'maxTasks': max_tasks,
            'usePriority': True,
            'asyncResponseTimeout': 30000,
            'topics': topics
        }
        
        try:
            response = self.session.post(url, json=payload, timeout=35)
            response.raise_for_status()
            tasks = response.json()
            if tasks:
                logger.info(f"Fetched {len(tasks)} task(s)")
            return tasks
        except RequestException as e:
            logger.error(f"Error fetching tasks: {e}")
            return []
    
    def complete_task(self, task_id: str, variables: Optional[Dict] = None) -> bool:
        """Mark a task as completed."""
        url = f"{self.base_url}/external-task/{task_id}/complete"
        payload = {'workerId': self.worker_id}
        
        if variables:
            payload['variables'] = self._format_variables(variables)
        
        try:
            response = self.session.post(url, json=payload, timeout=10)
            response.raise_for_status()
            logger.info(f"Task {task_id[:8]}... completed successfully")
            return True
        except RequestException as e:
            logger.error(f"Error completing task {task_id}: {e}")
            return False
    
    def handle_failure(self, task_id: str, error_message: str, 
                       retries: int = 3, retry_timeout: int = 10000) -> bool:
        """Report a task failure."""
        url = f"{self.base_url}/external-task/{task_id}/failure"
        payload = {
            'workerId': self.worker_id,
            'errorMessage': error_message[:500],
            'retries': retries,
            'retryTimeout': retry_timeout
        }
        
        try:
            response = self.session.post(url, json=payload, timeout=10)
            response.raise_for_status()
            logger.warning(f"Task {task_id[:8]}... failed, {retries} retries remaining")
            return True
        except RequestException as e:
            logger.error(f"Error reporting failure: {e}")
            return False
    
    @staticmethod
    def _format_variables(variables: Dict) -> Dict:
        """Format variables for Camunda API."""
        formatted = {}
        for key, value in variables.items():
            if isinstance(value, dict) and 'value' in value:
                formatted[key] = value
            else:
                var_type = 'String'
                if isinstance(value, bool):
                    var_type = 'Boolean'
                elif isinstance(value, int):
                    var_type = 'Integer'
                elif isinstance(value, float):
                    var_type = 'Double'
                formatted[key] = {'value': value, 'type': var_type}
        return formatted


# =============================================================================
# TASK HANDLERS
# =============================================================================
class TaskHandlers:
    """Handlers for each external task topic."""
    
    def __init__(self):
        self.email = EmailService()
    
    def _get_var(self, variables: Dict, key: str, default: Any = '') -> Any:
        """Safely extract a variable value."""
        var = variables.get(key, {})
        if isinstance(var, dict):
            return var.get('value', default)
        return var or default
    
    # -------------------------------------------------------------------------
    # HANDLER: send-approval-email
    # -------------------------------------------------------------------------
    def handle_send_approval_email(self, variables: Dict) -> Dict:
        """Send approval email to policyholder."""
        name = self._get_var(variables, 'applicantName', 'Customer')
        email = self._get_var(variables, 'applicantEmail', 'unknown@example.com')
        rating = self._get_var(variables, 'rating', 'Green')
        car_make = self._get_var(variables, 'carMake', 'Unknown')
        car_model = self._get_var(variables, 'carModel', 'Unknown')
        
        logger.info(f"[APPROVAL] Processing for {name} ({email})")
        logger.info(f"  Rating: {rating}, Vehicle: {car_make} {car_model}")
        
        # Generate policy number
        policy_number = f"POL-{datetime.now().strftime('%Y%m%d')}-{os.urandom(3).hex().upper()}"
        
        subject = f"Your Insurance Application Has Been Approved! - {policy_number}"
        body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background: #28a745; color: white; padding: 20px; text-align: center;">
                <h1>Congratulations, {name}!</h1>
            </div>
            <div style="padding: 20px; background: #f9f9f9;">
                <p>We are pleased to inform you that your insurance application has been <strong>approved</strong>.</p>
                
                <div style="background: white; padding: 15px; border-left: 4px solid #28a745; margin: 15px 0;">
                    <p><strong>Policy Number:</strong> {policy_number}</p>
                    <p><strong>Vehicle:</strong> {car_make} {car_model}</p>
                    <p><strong>Risk Assessment:</strong> {rating}</p>
                </div>
                
                <p>Your policy documents will be sent separately. Please complete payment within 14 days to activate your coverage.</p>
                
                <p>Best regards,<br>The Insurance Team</p>
            </div>
        </body>
        </html>
        """
        
        success = self.email.send_email(email, subject, body)
        
        return {
            'emailSent': success,
            'policyNumber': policy_number,
            'notificationType': 'APPROVAL',
            'notificationTimestamp': datetime.utcnow().isoformat() + 'Z'
        }
    
    # -------------------------------------------------------------------------
    # HANDLER: send-rejection-email
    # -------------------------------------------------------------------------
    def handle_send_rejection_email(self, variables: Dict) -> Dict:
        """Send rejection email to policyholder."""
        name = self._get_var(variables, 'applicantName', 'Customer')
        email = self._get_var(variables, 'applicantEmail', 'unknown@example.com')
        rating = self._get_var(variables, 'rating', 'Red')
        reason = self._get_var(variables, 'rejectionReason', 
                               'Your application did not meet our underwriting criteria.')
        
        logger.info(f"[REJECTION] Processing for {name} ({email})")
        logger.info(f"  Rating: {rating}, Reason: {reason}")
        
        subject = "Update on Your Insurance Application"
        body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background: #6c757d; color: white; padding: 20px; text-align: center;">
                <h1>Application Update</h1>
            </div>
            <div style="padding: 20px; background: #f9f9f9;">
                <p>Dear {name},</p>
                
                <p>Thank you for your interest in our insurance services. After careful review of your application, 
                we regret to inform you that we are unable to offer coverage at this time.</p>
                
                <div style="background: white; padding: 15px; border-left: 4px solid #dc3545; margin: 15px 0;">
                    <p><strong>Reason:</strong> {reason}</p>
                </div>
                
                <p>You may reapply after 90 days if your circumstances change. If you believe this decision 
                was made in error, please contact our customer service team.</p>
                
                <p>Best regards,<br>The Insurance Team</p>
            </div>
        </body>
        </html>
        """
        
        success = self.email.send_email(email, subject, body)
        
        return {
            'emailSent': success,
            'notificationType': 'REJECTION',
            'notificationTimestamp': datetime.utcnow().isoformat() + 'Z'
        }
    
    # -------------------------------------------------------------------------
    # HANDLER: inform-manager
    # -------------------------------------------------------------------------
    def handle_inform_manager(self, variables: Dict) -> Dict:
        """Notify manager about application pending for too long."""
        name = self._get_var(variables, 'applicantName', 'Unknown')
        email = self._get_var(variables, 'applicantEmail', 'unknown@example.com')
        rating = self._get_var(variables, 'rating', 'Yellow')
        age = self._get_var(variables, 'age', 'N/A')
        car_make = self._get_var(variables, 'carMake', 'Unknown')
        car_model = self._get_var(variables, 'carModel', 'Unknown')
        
        logger.info(f"[MANAGER ALERT] Application pending > 2 days")
        logger.info(f"  Applicant: {name}, Rating: {rating}")
        
        subject = f"[ACTION REQUIRED] Pending Application - {name}"
        body = f"""
        <html>
        <body style="font-family: Arial, sans-serif;">
            <div style="background: #ffc107; padding: 15px; border-radius: 5px;">
                <strong>Manual Review Required</strong> - Application pending for more than 2 days
            </div>
            
            <table style="margin: 15px 0; border-collapse: collapse;">
                <tr><td style="padding: 8px; font-weight: bold;">Applicant:</td><td style="padding: 8px;">{name}</td></tr>
                <tr><td style="padding: 8px; font-weight: bold;">Email:</td><td style="padding: 8px;">{email}</td></tr>
                <tr><td style="padding: 8px; font-weight: bold;">Age:</td><td style="padding: 8px;">{age}</td></tr>
                <tr><td style="padding: 8px; font-weight: bold;">Vehicle:</td><td style="padding: 8px;">{car_make} {car_model}</td></tr>
                <tr><td style="padding: 8px; font-weight: bold;">Risk Rating:</td>
                    <td style="padding: 8px; color: #ffc107; font-weight: bold;">{rating}</td></tr>
            </table>
            
            <p>Please review this application in <a href="http://localhost:8080/camunda/app/tasklist/">Camunda Tasklist</a>.</p>
        </body>
        </html>
        """
        
        success = self.email.send_email(MANAGER_EMAIL, subject, body)
        
        return {
            'managerNotified': success,
            'notificationTimestamp': datetime.utcnow().isoformat() + 'Z'
        }
    
    # -------------------------------------------------------------------------
    # HANDLER: request-documents-email
    # -------------------------------------------------------------------------
    def handle_request_documents_email(self, variables: Dict) -> Dict:
        """Send document request email to applicant."""
        name = self._get_var(variables, 'applicantName', 'Customer')
        email = self._get_var(variables, 'applicantEmail', 'unknown@example.com')
        missing_docs = self._get_var(variables, 'missingDocuments', None)
        
        # Parse missing documents
        if missing_docs is None:
            docs_list = ['Driving License', 'Proof of Address', 'Vehicle Registration']
        elif isinstance(missing_docs, str):
            try:
                docs_list = json.loads(missing_docs)
            except json.JSONDecodeError:
                docs_list = [missing_docs]
        else:
            docs_list = list(missing_docs)
        
        logger.info(f"[DOCUMENT REQUEST] Processing for {name} ({email})")
        logger.info(f"  Documents: {docs_list}")
        
        docs_html = "".join([f"<li>{doc}</li>" for doc in docs_list])
        
        subject = "Additional Documents Required for Your Insurance Application"
        body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background: #17a2b8; color: white; padding: 20px; text-align: center;">
                <h1>Documents Required</h1>
            </div>
            <div style="padding: 20px; background: #f9f9f9;">
                <p>Dear {name},</p>
                
                <p>To continue processing your insurance application, we require the following documents:</p>
                
                <div style="background: white; padding: 15px; border-left: 4px solid #17a2b8; margin: 15px 0;">
                    <ul>{docs_html}</ul>
                </div>
                
                <p><strong>Please submit these documents within 7 days.</strong></p>
                
                <p>If we do not receive the required documents, your application may be automatically rejected.</p>
                
                <p>Best regards,<br>The Insurance Team</p>
            </div>
        </body>
        </html>
        """
        
        success = self.email.send_email(email, subject, body)
        
        return {
            'documentRequestSent': success,
            'requestedDocuments': json.dumps(docs_list),
            'requestTimestamp': datetime.utcnow().isoformat() + 'Z'
        }
    
    # -------------------------------------------------------------------------
    # HANDLER: send-auto-rejection-email
    # -------------------------------------------------------------------------
    def handle_send_auto_rejection_email(self, variables: Dict) -> Dict:
        """Send auto-rejection email when documents not received."""
        name = self._get_var(variables, 'applicantName', 'Customer')
        email = self._get_var(variables, 'applicantEmail', 'unknown@example.com')
        
        logger.info(f"[AUTO-REJECTION] Processing for {name} ({email})")
        
        subject = "Your Insurance Application - Documents Not Received"
        body = f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <div style="background: #dc3545; color: white; padding: 20px; text-align: center;">
                <h1>Application Closed</h1>
            </div>
            <div style="padding: 20px; background: #f9f9f9;">
                <p>Dear {name},</p>
                
                <p>Unfortunately, we did not receive the required documents within the specified timeframe.</p>
                
                <p>As a result, your insurance application has been <strong>automatically closed</strong>.</p>
                
                <p>If you still wish to obtain insurance coverage, you are welcome to submit a new application 
                with all required documentation.</p>
                
                <p>Best regards,<br>The Insurance Team</p>
            </div>
        </body>
        </html>
        """
        
        success = self.email.send_email(email, subject, body)
        
        return {
            'autoRejectionSent': success,
            'rejectionReason': 'Required documents not received within deadline',
            'notificationTimestamp': datetime.utcnow().isoformat() + 'Z'
        }


# =============================================================================
# MAIN WORKER CLASS
# =============================================================================
class InsuranceWorker:
    """Main worker class that polls and processes external tasks."""
    
    def __init__(self):
        self.client = CamundaClient(CAMUNDA_URL, WORKER_ID)
        self.handlers = TaskHandlers()
        self.running = True
        
        # Map topics to handler methods
        self.handler_map = {
            'send-approval-email': self.handlers.handle_send_approval_email,
            'send-rejection-email': self.handlers.handle_send_rejection_email,
            'inform-manager': self.handlers.handle_inform_manager,
            'request-documents-email': self.handlers.handle_request_documents_email,
            'send-auto-rejection-email': self.handlers.handle_send_auto_rejection_email,
        }
    
    def process_task(self, task: Dict) -> None:
        """Process a single external task."""
        task_id = task['id']
        topic = task['topicName']
        variables = task.get('variables', {})
        retries = task.get('retries', 3)
        
        logger.info(f"Processing task {task_id[:8]}... from topic '{topic}'")
        
        handler = self.handler_map.get(topic)
        if not handler:
            logger.error(f"No handler for topic '{topic}'")
            self.client.handle_failure(task_id, f"Unknown topic: {topic}", retries=0)
            return
        
        try:
            result = handler(variables)
            self.client.complete_task(task_id, variables=result)
        except Exception as e:
            logger.exception(f"Error processing task {task_id}")
            self.client.handle_failure(task_id, str(e), retries=max(0, (retries or 3) - 1))
    
    def run(self) -> None:
        """Main worker loop."""
        logger.info("=" * 60)
        logger.info("INSURANCE EXTERNAL TASK WORKER")
        logger.info("=" * 60)
        logger.info(f"Worker ID: {WORKER_ID}")
        logger.info(f"Camunda URL: {CAMUNDA_URL}")
        logger.info(f"Topics: {[t['topicName'] for t in TOPICS]}")
        logger.info(f"Email Mode: {'LIVE' if EMAIL_ENABLED else 'MOCK (simulated)'}")
        logger.info("=" * 60)
        
        while self.running:
            try:
                tasks = self.client.fetch_and_lock(TOPICS, MAX_TASKS)
                
                for task in tasks:
                    self.process_task(task)
                
                if not tasks:
                    time.sleep(POLL_INTERVAL)
                    
            except KeyboardInterrupt:
                logger.info("Shutdown requested...")
                self.running = False
            except Exception as e:
                logger.exception(f"Error in worker loop: {e}")
                time.sleep(POLL_INTERVAL)
        
        logger.info("Worker stopped")
    
    def stop(self) -> None:
        """Stop the worker gracefully."""
        self.running = False


def main():
    """Entry point."""
    worker = InsuranceWorker()
    try:
        worker.run()
    except KeyboardInterrupt:
        worker.stop()


if __name__ == '__main__':
    main()