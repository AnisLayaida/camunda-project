"""
Insurance Process External Task Worker

Handles external tasks for the insurance application workflow as shown in the BPMN:

BPMN Flow:
1. Insurance Application Received (Start Event)
2. Determine Riskgroup (Business Rule Task - calls DMN)
3. Gateway routes based on riskRating:
   - Green → Approved → Message sent to policyholder → End
   - Yellow → Checks Application (User Task) → Accepted? → Approved/Rejected
   - Red → Rejected → Message sent to policyholder → End

External Tasks handled by this worker:
- determine-riskgroup: Calculate risk rating (Green/Yellow/Red)
- send-policyholder-message: Send email notification (approval or rejection)
- inform-manager: Notify manager about Yellow-rated applications
- request-documents: Handle document request subprocess
"""

import logging
import time
import os
import sys
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from typing import Dict, Any, Optional, List
import requests
from requests.exceptions import RequestException

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger('insurance-worker')

# Configuration
CAMUNDA_URL = os.getenv('CAMUNDA_URL', 'http://localhost:8080/engine-rest')
WORKER_ID = os.getenv('WORKER_ID', f'insurance-worker-{os.getpid()}')
LOCK_DURATION = int(os.getenv('LOCK_DURATION', '300000'))
POLL_INTERVAL = int(os.getenv('POLL_INTERVAL', '5'))
MAX_TASKS = int(os.getenv('MAX_TASKS', '5'))

# Email Configuration
SMTP_HOST = os.getenv('SMTP_HOST', 'email-smtp.eu-west-2.amazonaws.com')
SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))
SMTP_USERNAME = os.getenv('SMTP_USERNAME', '')
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD', '')
EMAIL_FROM = os.getenv('EMAIL_FROM', 'noreply@insurance-company.com')
EMAIL_ENABLED = os.getenv('EMAIL_ENABLED', 'false').lower() == 'true'
MANAGER_EMAIL = os.getenv('MANAGER_EMAIL', 'underwriting@insurance-company.com')
SLACK_WEBHOOK_URL = os.getenv('SLACK_WEBHOOK_URL', '')

TOPICS = [
    {'topicName': 'determine-riskgroup', 'lockDuration': LOCK_DURATION,
     'variables': ['age', 'carMake', 'carModel', 'region', 'applicantName', 'applicantEmail']},
    {'topicName': 'send-policyholder-message', 'lockDuration': LOCK_DURATION,
     'variables': ['applicantName', 'applicantEmail', 'riskRating', 'approved', 'premium', 'policyNumber', 'rejectionReason']},
    {'topicName': 'inform-manager', 'lockDuration': LOCK_DURATION,
     'variables': ['applicantName', 'applicantEmail', 'riskRating', 'riskScore', 'applicationId', 'calculatedPremium']},
    {'topicName': 'request-documents', 'lockDuration': LOCK_DURATION,
     'variables': ['applicantName', 'applicantEmail', 'missingDocuments', 'applicationId']}
]


class EmailService:
    def __init__(self):
        self.enabled = EMAIL_ENABLED
        self.smtp_host = SMTP_HOST
        self.smtp_port = SMTP_PORT
        self.username = SMTP_USERNAME
        self.password = SMTP_PASSWORD
        self.from_address = EMAIL_FROM
    
    def send_email(self, to: str, subject: str, html_body: str, text_body: str = None) -> bool:
        if not self.enabled:
            logger.info(f"[EMAIL MOCK] To: {to}, Subject: {subject}")
            return True
        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.from_address
            msg['To'] = to
            if text_body:
                msg.attach(MIMEText(text_body, 'plain'))
            msg.attach(MIMEText(html_body, 'html'))
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                if self.username and self.password:
                    server.login(self.username, self.password)
                server.sendmail(self.from_address, to, msg.as_string())
            logger.info(f"Email sent to {to}")
            return True
        except Exception as e:
            logger.error(f"Email failed to {to}: {e}")
            return False
    
    def send_approval_email(self, to: str, name: str, policy_number: str, premium: float) -> bool:
        subject = f"Insurance Application Approved - Policy #{policy_number}"
        html = f"""
        <html><body style="font-family:Arial,sans-serif;">
        <div style="max-width:600px;margin:0 auto;padding:20px;">
            <div style="background:#28a745;color:white;padding:20px;text-align:center;">
                <h1>Congratulations!</h1>
            </div>
            <div style="padding:20px;background:#f9f9f9;">
                <p>Dear {name},</p>
                <p>Your insurance application has been <strong>approved</strong>.</p>
                <div style="background:#fff;padding:15px;border-left:4px solid #28a745;margin:15px 0;">
                    <p><strong>Policy Number:</strong> {policy_number}</p>
                    <p><strong>Annual Premium:</strong> £{premium:,.2f}</p>
                </div>
                <p>Complete payment within 14 days to activate your policy.</p>
                <p>Best regards,<br>The Insurance Team</p>
            </div>
        </div></body></html>"""
        text = f"Dear {name},\n\nYour application has been APPROVED.\nPolicy: {policy_number}\nPremium: £{premium:,.2f}"
        return self.send_email(to, subject, html, text)
    
    def send_rejection_email(self, to: str, name: str, reason: str) -> bool:
        subject = "Update on Your Insurance Application"
        html = f"""
        <html><body style="font-family:Arial,sans-serif;">
        <div style="max-width:600px;margin:0 auto;padding:20px;">
            <div style="background:#6c757d;color:white;padding:20px;text-align:center;">
                <h1>Application Update</h1>
            </div>
            <div style="padding:20px;background:#f9f9f9;">
                <p>Dear {name},</p>
                <p>We regret to inform you that we are unable to offer coverage at this time.</p>
                <div style="background:#fff;padding:15px;border-left:4px solid #dc3545;margin:15px 0;">
                    <p><strong>Reason:</strong> {reason}</p>
                </div>
                <p>You may reapply after 90 days.</p>
                <p>Best regards,<br>The Insurance Team</p>
            </div>
        </div></body></html>"""
        text = f"Dear {name},\n\nYour application was not approved.\nReason: {reason}"
        return self.send_email(to, subject, html, text)
    
    def send_manager_notification(self, app_id: str, name: str, rating: str, score: float, premium: float) -> bool:
        subject = f"[ACTION] Review Required - {app_id}"
        html = f"""
        <html><body>
        <div style="background:#fff3cd;border:1px solid #ffc107;padding:15px;">
            <strong>Manual Review Required</strong>
        </div>
        <table style="margin:15px 0;">
            <tr><td><strong>Application:</strong></td><td>{app_id}</td></tr>
            <tr><td><strong>Applicant:</strong></td><td>{name}</td></tr>
            <tr><td><strong>Risk Rating:</strong></td><td style="color:#ffc107;font-weight:bold;">{rating}</td></tr>
            <tr><td><strong>Risk Score:</strong></td><td>{score:.1f}/100</td></tr>
            <tr><td><strong>Premium:</strong></td><td>£{premium:,.2f}</td></tr>
        </table>
        <p>Please review within 2 business days.</p>
        </body></html>"""
        return self.send_email(MANAGER_EMAIL, subject, html)
    
    def send_document_request(self, to: str, name: str, docs: List[str], app_id: str) -> bool:
        subject = f"Documents Required - {app_id}"
        doc_list = "".join([f"<li>{d.replace('_',' ').title()}</li>" for d in docs])
        html = f"""
        <html><body style="font-family:Arial,sans-serif;">
        <h2>Additional Documents Required</h2>
        <p>Dear {name},</p>
        <p>Please submit the following within 7 days:</p>
        <ul>{doc_list}</ul>
        <p>Best regards,<br>The Insurance Team</p>
        </body></html>"""
        return self.send_email(to, subject, html)


class CamundaClient:
    def __init__(self, base_url: str, worker_id: str):
        self.base_url = base_url.rstrip('/')
        self.worker_id = worker_id
        self.session = requests.Session()
        username = os.getenv('CAMUNDA_USERNAME')
        password = os.getenv('CAMUNDA_PASSWORD')
        if username and password:
            self.session.auth = (username, password)
        self.session.headers.update({'Content-Type': 'application/json', 'Accept': 'application/json'})
    
    def fetch_and_lock(self, topics: List[Dict], max_tasks: int = 5) -> List[Dict]:
        url = f"{self.base_url}/external-task/fetchAndLock"
        payload = {'workerId': self.worker_id, 'maxTasks': max_tasks, 'usePriority': True,
                   'asyncResponseTimeout': 30000, 'topics': topics}
        try:
            response = self.session.post(url, json=payload, timeout=35)
            response.raise_for_status()
            return response.json()
        except RequestException as e:
            logger.error(f"Fetch error: {e}")
            return []
    
    def complete_task(self, task_id: str, variables: Optional[Dict] = None) -> bool:
        url = f"{self.base_url}/external-task/{task_id}/complete"
        payload = {'workerId': self.worker_id}
        if variables:
            payload['variables'] = self._format_variables(variables)
        try:
            response = self.session.post(url, json=payload, timeout=10)
            response.raise_for_status()
            logger.info(f"Task {task_id} completed")
            return True
        except RequestException as e:
            logger.error(f"Complete error: {e}")
            return False
    
    def handle_failure(self, task_id: str, error: str, retries: int = 3, timeout: int = 10000) -> bool:
        url = f"{self.base_url}/external-task/{task_id}/failure"
        payload = {'workerId': self.worker_id, 'errorMessage': error[:500], 'retries': retries, 'retryTimeout': timeout}
        try:
            response = self.session.post(url, json=payload, timeout=10)
            response.raise_for_status()
            return True
        except RequestException:
            return False
    
    def handle_bpmn_error(self, task_id: str, code: str, msg: str = "") -> bool:
        url = f"{self.base_url}/external-task/{task_id}/bpmnError"
        payload = {'workerId': self.worker_id, 'errorCode': code, 'errorMessage': msg}
        try:
            response = self.session.post(url, json=payload, timeout=10)
            response.raise_for_status()
            return True
        except RequestException:
            return False
    
    @staticmethod
    def _format_variables(variables: Dict) -> Dict:
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
                elif isinstance(value, (dict, list)):
                    var_type = 'Json'
                    value = json.dumps(value)
                formatted[key] = {'value': value, 'type': var_type}
        return formatted


class TaskHandlers:
    def __init__(self):
        self.email = EmailService()
    
    def determine_riskgroup(self, variables: Dict) -> Dict:
        """Calculate risk rating for the gateway."""
        logger.info("Processing: Determine Riskgroup")
        age = int(variables.get('age', {}).get('value', 30))
        car_make = str(variables.get('carMake', {}).get('value', 'Unknown')).lower()
        car_model = str(variables.get('carModel', {}).get('value', 'Unknown')).lower()
        region = str(variables.get('region', {}).get('value', 'Unknown')).lower()
        name = variables.get('applicantName', {}).get('value', 'Unknown')
        
        logger.info(f"Evaluating: {name}, age={age}, vehicle={car_make} {car_model}")
        
        score = 50
        if age < 21: score += 35
        elif age < 25: score += 25
        elif age < 30: score += 10
        elif 30 <= age < 60: score -= 15
        elif age >= 70: score += 20
        
        if any(m in car_make for m in ['ferrari', 'lamborghini', 'porsche']): score += 30
        elif any(m in car_make for m in ['bmw', 'mercedes', 'audi']): score += 15
        elif any(m in car_make for m in ['toyota', 'honda', 'volvo']): score -= 10
        
        if any(kw in car_model for kw in ['sport', 'gt', 'turbo', 'amg', 'rs']): score += 15
        if any(a in region for a in ['london', 'manchester', 'birmingham']): score += 15
        elif any(a in region for a in ['rural', 'village']): score -= 10
        
        score = max(0, min(100, score))
        
        if score <= 35:
            rating, mult, base = 'Green', 0.85, 400
        elif score <= 65:
            rating, mult, base = 'Yellow', 1.3, 500
        else:
            rating, mult, base = 'Red', 2.5, 600
        
        premium = round(base * mult, 2)
        policy = f"POL-{datetime.now().strftime('%Y%m%d')}-{os.urandom(3).hex().upper()}"
        app_id = f"APP-{os.urandom(4).hex().upper()}"
        
        logger.info(f"Result: score={score}, rating={rating}, premium=£{premium}")
        
        return {
            'riskRating': rating,
            'riskScore': score,
            'calculatedPremium': premium,
            'policyNumber': policy,
            'applicationId': app_id,
            'assessmentTimestamp': datetime.utcnow().isoformat() + 'Z'
        }
    
    def send_policyholder_message(self, variables: Dict) -> Dict:
        """Send approval or rejection email."""
        logger.info("Processing: Send Policyholder Message")
        name = variables.get('applicantName', {}).get('value', 'Customer')
        email = variables.get('applicantEmail', {}).get('value', '')
        approved = variables.get('approved', {}).get('value', False)
        
        if isinstance(approved, str):
            approved = approved.lower() == 'true'
        
        if approved:
            premium = float(variables.get('calculatedPremium', {}).get('value', 500))
            policy = variables.get('policyNumber', {}).get('value', 'POL-UNKNOWN')
            logger.info(f"Sending APPROVAL to {email}")
            success = self.email.send_approval_email(email, name, policy, premium)
            notif_type = 'APPROVAL'
        else:
            reason = variables.get('rejectionReason', {}).get('value', 
                'Application did not meet underwriting criteria.')
            logger.info(f"Sending REJECTION to {email}")
            success = self.email.send_rejection_email(email, name, reason)
            notif_type = 'REJECTION'
        
        return {
            'emailSent': success,
            'notificationType': notif_type,
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        }
    
    def inform_manager(self, variables: Dict) -> Dict:
        """Notify manager for Yellow applications."""
        logger.info("Processing: Inform Manager")
        name = variables.get('applicantName', {}).get('value', 'Unknown')
        rating = variables.get('riskRating', {}).get('value', 'Yellow')
        score = float(variables.get('riskScore', {}).get('value', 50))
        app_id = variables.get('applicationId', {}).get('value', 'UNKNOWN')
        premium = float(variables.get('calculatedPremium', {}).get('value', 500))
        
        logger.info(f"Notifying manager about {app_id}")
        success = self.email.send_manager_notification(app_id, name, rating, score, premium)
        
        return {
            'managerNotified': success,
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        }
    
    def request_documents(self, variables: Dict) -> Dict:
        """Send document request email."""
        logger.info("Processing: Request Documents")
        name = variables.get('applicantName', {}).get('value', 'Customer')
        email = variables.get('applicantEmail', {}).get('value', '')
        app_id = variables.get('applicationId', {}).get('value', 'UNKNOWN')
        docs = variables.get('missingDocuments', {}).get('value', [])
        
        if isinstance(docs, str):
            try: docs = json.loads(docs)
            except: docs = [docs]
        if not docs:
            docs = ['driving_license', 'proof_of_address', 'vehicle_registration']
        
        logger.info(f"Requesting docs from {email}: {docs}")
        success = self.email.send_document_request(email, name, docs, app_id)
        
        return {
            'documentRequestSent': success,
            'requestedDocuments': docs,
            'timestamp': datetime.utcnow().isoformat() + 'Z'
        }


class InsuranceWorker:
    def __init__(self):
        self.client = CamundaClient(CAMUNDA_URL, WORKER_ID)
        self.handlers = TaskHandlers()
        self.handler_map = {
            'determine-riskgroup': self.handlers.determine_riskgroup,
            'send-policyholder-message': self.handlers.send_policyholder_message,
            'inform-manager': self.handlers.inform_manager,
            'request-documents': self.handlers.request_documents
        }
        self.running = True
    
    def process_task(self, task: Dict) -> None:
        task_id = task['id']
        topic = task['topicName']
        variables = task.get('variables', {})
        retries = task.get('retries', 3)
        
        logger.info(f"Processing {task_id} from '{topic}'")
        handler = self.handler_map.get(topic)
        if not handler:
            self.client.handle_failure(task_id, f"Unknown topic: {topic}", retries=0)
            return
        
        try:
            result = handler(variables)
            self.client.complete_task(task_id, variables=result)
        except ValueError as e:
            self.client.handle_bpmn_error(task_id, 'VALIDATION_ERROR', str(e))
        except Exception as e:
            logger.exception(f"Error in {task_id}")
            self.client.handle_failure(task_id, str(e), retries=max(0, (retries or 3) - 1))
    
    def run(self) -> None:
        logger.info("=" * 50)
        logger.info(f"Insurance Worker: {WORKER_ID}")
        logger.info(f"Camunda: {CAMUNDA_URL}")
        logger.info(f"Topics: {[t['topicName'] for t in TOPICS]}")
        logger.info(f"Email: {'ENABLED' if EMAIL_ENABLED else 'MOCK MODE'}")
        logger.info("=" * 50)
        
        while self.running:
            try:
                tasks = self.client.fetch_and_lock(TOPICS, MAX_TASKS)
                for task in tasks:
                    self.process_task(task)
                if not tasks:
                    time.sleep(POLL_INTERVAL)
            except KeyboardInterrupt:
                self.running = False
            except Exception as e:
                logger.exception(f"Loop error: {e}")
                time.sleep(POLL_INTERVAL)
        logger.info("Worker stopped")
    
    def stop(self):
        self.running = False


def main():
    worker = InsuranceWorker()
    try:
        worker.run()
    except KeyboardInterrupt:
        worker.stop()


if __name__ == '__main__':
    main()