"""
Risk Assessment External Task Worker

This worker specializes in risk assessment tasks that may require:
- Integration with external risk scoring services
- Machine learning model inference
- Database lookups for historical data
- Credit score integration
- Claims history analysis

The worker is designed to be horizontally scalable and stateless.
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
from dataclasses import dataclass
from enum import Enum

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger('risk-worker')

# Configuration
CAMUNDA_URL = os.getenv('CAMUNDA_URL', 'http://localhost:8080/engine-rest')
WORKER_ID = os.getenv('WORKER_ID', f'risk-worker-{os.getpid()}')
LOCK_DURATION = int(os.getenv('LOCK_DURATION', '600000'))
POLL_INTERVAL = int(os.getenv('POLL_INTERVAL', '5'))
MAX_TASKS = int(os.getenv('MAX_TASKS', '3'))


class RiskLevel(Enum):
    VERY_LOW = 'VERY_LOW'
    LOW = 'LOW'
    MEDIUM = 'MEDIUM'
    HIGH = 'HIGH'
    VERY_HIGH = 'VERY_HIGH'
    UNINSURABLE = 'UNINSURABLE'


@dataclass
class RiskFactor:
    name: str
    category: str
    raw_value: Any
    score: float
    weight: float
    contribution: float
    description: str


class CamundaClient:
    def __init__(self, base_url: str, worker_id: str):
        self.base_url = base_url.rstrip('/')
        self.worker_id = worker_id
        self.session = requests.Session()
        
        username = os.getenv('CAMUNDA_USERNAME')
        password = os.getenv('CAMUNDA_PASSWORD')
        if username and password:
            self.session.auth = (username, password)
        
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        })
    
    def fetch_and_lock(self, topics: List[Dict], max_tasks: int = 3) -> List[Dict]:
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
            return response.json()
        except RequestException as e:
            logger.error(f"Error fetching tasks: {e}")
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
            logger.error(f"Error completing task: {e}")
            return False
    
    def handle_failure(self, task_id: str, error_message: str,
                       retries: int = 3, retry_timeout: int = 10000) -> bool:
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
            return True
        except RequestException as e:
            logger.error(f"Error reporting failure: {e}")
            return False
    
    def handle_bpmn_error(self, task_id: str, error_code: str, error_message: str = "") -> bool:
        url = f"{self.base_url}/external-task/{task_id}/bpmnError"
        payload = {
            'workerId': self.worker_id,
            'errorCode': error_code,
            'errorMessage': error_message
        }
        try:
            response = self.session.post(url, json=payload, timeout=10)
            response.raise_for_status()
            return True
        except RequestException as e:
            logger.error(f"Error throwing BPMN error: {e}")
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


class RiskCalculator:
    """Multi-factor risk calculation engine."""
    
    WEIGHTS = {
        'driver_age': 0.20,
        'driving_experience': 0.10,
        'vehicle_make': 0.12,
        'vehicle_model': 0.08,
        'vehicle_age': 0.08,
        'region': 0.12,
        'claims_history': 0.18,
        'annual_mileage': 0.07,
        'storage_type': 0.05
    }
    
    @staticmethod
    def calculate_age_risk(age: int) -> RiskFactor:
        if age < 18:
            score, desc = 100, "Underage - cannot be insured"
        elif age < 21:
            score, desc = 90, "Very young driver - highest risk"
        elif age < 25:
            score, desc = 75, "Young driver - elevated risk"
        elif age < 30:
            score, desc = 55, "Young adult - moderate risk"
        elif age < 50:
            score, desc = 30, "Prime age - lowest risk"
        elif age < 60:
            score, desc = 40, "Mature driver - low risk"
        elif age < 70:
            score, desc = 55, "Senior - moderate risk"
        elif age < 75:
            score, desc = 70, "Elderly - elevated risk"
        else:
            score, desc = 85, "Very elderly - high risk"
        
        weight = RiskCalculator.WEIGHTS['driver_age']
        return RiskFactor('Driver Age', 'Driver', age, score, weight, score * weight, desc)
    
    @staticmethod
    def calculate_vehicle_make_risk(make: str) -> RiskFactor:
        make_lower = make.lower()
        risk_table = {
            'ferrari': (95, "Exotic - extreme risk"),
            'lamborghini': (95, "Exotic - extreme risk"),
            'porsche': (80, "Sports car - high risk"),
            'bmw': (58, "Premium - moderate risk"),
            'mercedes': (56, "Premium - moderate risk"),
            'audi': (54, "Premium - moderate risk"),
            'tesla': (55, "Electric performance - moderate"),
            'toyota': (28, "Reliable - low risk"),
            'honda': (30, "Reliable - low risk"),
            'volvo': (25, "Safety focused - lowest risk"),
            'ford': (45, "Mainstream - average"),
            'hyundai': (38, "Mainstream - low-moderate"),
            'kia': (40, "Mainstream - low-moderate"),
            'mazda': (35, "Reliable - low risk"),
            'subaru': (38, "AWD - low-moderate risk"),
        }
        score, desc = risk_table.get(make_lower, (50, "Unknown - average assumed"))
        weight = RiskCalculator.WEIGHTS['vehicle_make']
        return RiskFactor('Vehicle Make', 'Vehicle', make, score, weight, score * weight, desc)
    
    @staticmethod
    def calculate_vehicle_model_risk(model: str) -> RiskFactor:
        model_lower = model.lower()
        performance_keywords = ['sport', 'gt', 'turbo', 'rs', 'amg', 'm3', 'm5', 'type r', 'sti', 'nismo']
        economy_keywords = ['hybrid', 'eco', 'base', 'family', 'standard']
        
        score, desc = 50, "Standard variant"
        for kw in performance_keywords:
            if kw in model_lower:
                score, desc = 75, f"Performance variant ({kw}) - elevated risk"
                break
        for kw in economy_keywords:
            if kw in model_lower:
                score, desc = 35, f"Economy variant ({kw}) - reduced risk"
                break
        
        weight = RiskCalculator.WEIGHTS['vehicle_model']
        return RiskFactor('Vehicle Model', 'Vehicle', model, score, weight, score * weight, desc)
    
    @staticmethod
    def calculate_region_risk(region: str) -> RiskFactor:
        region_lower = region.lower()
        high_risk = ['london', 'manchester', 'birmingham', 'liverpool', 'leeds']
        medium_risk = ['bristol', 'sheffield', 'nottingham', 'leicester', 'newcastle']
        low_risk = ['rural', 'village', 'countryside', 'scotland', 'wales', 'cornwall']
        
        score, desc = 50, "Average region - standard risk"
        for area in high_risk:
            if area in region_lower:
                score, desc = 75, f"Urban area ({area}) - high theft/accident rate"
                break
        for area in medium_risk:
            if area in region_lower:
                score, desc = 60, f"City area ({area}) - moderate risk"
                break
        for area in low_risk:
            if area in region_lower:
                score, desc = 30, "Rural/low-traffic area - reduced risk"
                break
        
        weight = RiskCalculator.WEIGHTS['region']
        return RiskFactor('Region', 'Geographic', region, score, weight, score * weight, desc)
    
    @staticmethod
    def calculate_claims_history_risk(claims_count: int, years: int = 5) -> RiskFactor:
        if claims_count == 0:
            score, desc = 10, f"No claims in {years} years - excellent"
        elif claims_count == 1:
            score, desc = 40, "1 claim - minor impact"
        elif claims_count == 2:
            score, desc = 60, "2 claims - moderate concern"
        elif claims_count <= 4:
            score, desc = 80, f"{claims_count} claims - significant risk"
        else:
            score, desc = 95, f"{claims_count} claims - very high risk"
        
        weight = RiskCalculator.WEIGHTS['claims_history']
        return RiskFactor('Claims History', 'Historical', claims_count, score, weight, score * weight, desc)
    
    def calculate_comprehensive_risk(self, age: int, car_make: str, car_model: str,
                                      region: str, claims_count: int = 0,
                                      driving_years: int = None) -> Dict[str, Any]:
        factors = [
            self.calculate_age_risk(age),
            self.calculate_vehicle_make_risk(car_make),
            self.calculate_vehicle_model_risk(car_model),
            self.calculate_region_risk(region),
            self.calculate_claims_history_risk(claims_count)
        ]
        
        if driving_years is not None:
            if driving_years < 1:
                exp_score, exp_desc = 85, "New driver - very limited experience"
            elif driving_years < 2:
                exp_score, exp_desc = 70, "Novice driver - limited experience"
            elif driving_years < 5:
                exp_score, exp_desc = 50, "Developing driver - moderate experience"
            elif driving_years < 10:
                exp_score, exp_desc = 35, "Experienced driver - good track record"
            else:
                exp_score, exp_desc = 25, "Very experienced driver"
            
            weight = self.WEIGHTS['driving_experience']
            factors.append(RiskFactor('Driving Experience', 'Driver', driving_years,
                                       exp_score, weight, exp_score * weight, exp_desc))
        
        total_weight = sum(f.weight for f in factors)
        overall_score = sum(f.contribution for f in factors) / total_weight if total_weight > 0 else 50
        
        if overall_score <= 25:
            risk_level = RiskLevel.VERY_LOW
        elif overall_score <= 40:
            risk_level = RiskLevel.LOW
        elif overall_score <= 55:
            risk_level = RiskLevel.MEDIUM
        elif overall_score <= 70:
            risk_level = RiskLevel.HIGH
        elif overall_score <= 85:
            risk_level = RiskLevel.VERY_HIGH
        else:
            risk_level = RiskLevel.UNINSURABLE
        
        # Map to BPMN gateway values
        if risk_level in [RiskLevel.VERY_LOW, RiskLevel.LOW]:
            risk_rating, action, multiplier = 'Green', 'AUTO_APPROVE', 0.85
        elif risk_level in [RiskLevel.MEDIUM, RiskLevel.HIGH]:
            risk_rating, action = 'Yellow', 'MANUAL_REVIEW'
            multiplier = 1.25 if risk_level == RiskLevel.MEDIUM else 1.75
        else:
            risk_rating = 'Red'
            action = 'REJECT' if risk_level == RiskLevel.UNINSURABLE else 'HIGH_RISK_REVIEW'
            multiplier = 2.5
        
        confidence = min(0.95, 0.6 + (len(factors) / len(self.WEIGHTS)) * 0.35)
        
        logger.info(f"Risk: score={overall_score:.1f}, level={risk_level.value}, rating={risk_rating}")
        
        return {
            'riskRating': risk_rating,
            'overallScore': round(overall_score, 2),
            'riskLevel': risk_level.value,
            'factors': [{
                'name': f.name, 'category': f.category, 'rawValue': str(f.raw_value),
                'score': round(f.score, 2), 'weight': round(f.weight, 3),
                'contribution': round(f.contribution, 2), 'description': f.description
            } for f in factors],
            'premiumMultiplier': round(multiplier, 2),
            'recommendedAction': action,
            'confidence': round(confidence, 3),
            'assessmentTimestamp': datetime.utcnow().isoformat() + 'Z'
        }


class RiskWorker:
    TOPICS = [
        {'topicName': 'calculate-detailed-risk', 'lockDuration': LOCK_DURATION,
         'variables': ['age', 'carMake', 'carModel', 'region', 'claimsCount', 'drivingYears']},
        {'topicName': 'evaluate-premium', 'lockDuration': LOCK_DURATION,
         'variables': ['riskScore', 'basePremium', 'coverageLevel', 'deductible']},
        {'topicName': 'check-fraud-indicators', 'lockDuration': LOCK_DURATION,
         'variables': ['applicantId', 'applicationData']},
        {'topicName': 'validate-risk-data', 'lockDuration': LOCK_DURATION,
         'variables': ['age', 'carMake', 'carModel', 'region']}
    ]
    
    def __init__(self):
        self.client = CamundaClient(CAMUNDA_URL, WORKER_ID)
        self.calculator = RiskCalculator()
        self.running = True
    
    def handle_calculate_risk(self, variables: Dict) -> Dict:
        age = int(variables.get('age', {}).get('value', 30))
        car_make = str(variables.get('carMake', {}).get('value', 'Unknown'))
        car_model = str(variables.get('carModel', {}).get('value', 'Unknown'))
        region = str(variables.get('region', {}).get('value', 'Unknown'))
        claims_count = int(variables.get('claimsCount', {}).get('value', 0))
        driving_years = variables.get('drivingYears', {}).get('value')
        if driving_years is not None:
            driving_years = int(driving_years)
        
        logger.info(f"Calculating risk: age={age}, vehicle={car_make} {car_model}, region={region}")
        return self.calculator.calculate_comprehensive_risk(
            age, car_make, car_model, region, claims_count, driving_years)
    
    def handle_evaluate_premium(self, variables: Dict) -> Dict:
        risk_score = float(variables.get('riskScore', {}).get('value', 50))
        base_premium = float(variables.get('basePremium', {}).get('value', 500))
        coverage_level = str(variables.get('coverageLevel', {}).get('value', 'standard'))
        deductible = float(variables.get('deductible', {}).get('value', 500))
        
        logger.info(f"Evaluating premium: base={base_premium}, risk_score={risk_score}")
        
        if risk_score <= 30:
            risk_mult = 0.8
        elif risk_score <= 50:
            risk_mult = 1.0
        elif risk_score <= 70:
            risk_mult = 1.4
        else:
            risk_mult = 2.0
        
        coverage_mult = {'basic': 0.7, 'standard': 1.0, 'comprehensive': 1.5, 'premium': 2.0}.get(
            coverage_level.lower(), 1.0)
        
        deduct_disc = 0.85 if deductible >= 1000 else 0.90 if deductible >= 750 else 0.95 if deductible >= 500 else 1.0
        
        final_premium = max(200, base_premium * risk_mult * coverage_mult * deduct_disc)
        
        return {
            'calculatedPremium': round(final_premium, 2),
            'riskMultiplier': risk_mult,
            'coverageMultiplier': coverage_mult,
            'deductibleDiscount': deduct_disc,
            'premiumBreakdown': {
                'base': base_premium,
                'afterRisk': round(base_premium * risk_mult, 2),
                'afterCoverage': round(base_premium * risk_mult * coverage_mult, 2),
                'final': round(final_premium, 2)
            },
            'calculationTimestamp': datetime.utcnow().isoformat() + 'Z'
        }
    
    def handle_fraud_check(self, variables: Dict) -> Dict:
        applicant_id = str(variables.get('applicantId', {}).get('value', 'Unknown'))
        logger.info(f"Checking fraud indicators for {applicant_id}")
        fraud_score = 10
        return {
            'fraudCheckPassed': fraud_score < 50,
            'fraudScore': fraud_score,
            'fraudIndicators': [],
            'requiresManualReview': fraud_score >= 30,
            'checkTimestamp': datetime.utcnow().isoformat() + 'Z'
        }
    
    def handle_validate_data(self, variables: Dict) -> Dict:
        errors, warnings = [], []
        
        age = variables.get('age', {}).get('value')
        if age is None:
            errors.append("Age is required")
        elif int(age) < 17:
            errors.append("Driver must be at least 17 years old")
        elif int(age) > 100:
            warnings.append("Please verify age - value seems high")
        
        car_make = variables.get('carMake', {}).get('value')
        if not car_make or car_make.lower() == 'unknown':
            errors.append("Vehicle make is required")
        
        region = variables.get('region', {}).get('value')
        if not region or region.lower() == 'unknown':
            warnings.append("Region not specified - using default rates")
        
        return {
            'dataValid': len(errors) == 0,
            'validationErrors': errors,
            'validationWarnings': warnings,
            'validationTimestamp': datetime.utcnow().isoformat() + 'Z'
        }
    
    def process_task(self, task: Dict) -> None:
        task_id = task['id']
        topic = task['topicName']
        variables = task.get('variables', {})
        retries = task.get('retries', 3)
        
        logger.info(f"Processing task {task_id} from topic '{topic}'")
        
        handlers = {
            'calculate-detailed-risk': self.handle_calculate_risk,
            'evaluate-premium': self.handle_evaluate_premium,
            'check-fraud-indicators': self.handle_fraud_check,
            'validate-risk-data': self.handle_validate_data
        }
        
        handler = handlers.get(topic)
        if not handler:
            logger.error(f"No handler for topic '{topic}'")
            self.client.handle_failure(task_id, f"Unknown topic: {topic}", retries=0)
            return
        
        try:
            result = handler(variables)
            self.client.complete_task(task_id, variables=result)
        except ValueError as e:
            logger.error(f"Validation error: {e}")
            self.client.handle_bpmn_error(task_id, 'VALIDATION_ERROR', str(e))
        except Exception as e:
            logger.exception(f"Error processing task {task_id}")
            self.client.handle_failure(task_id, str(e), retries=max(0, (retries or 3) - 1))
    
    def run(self) -> None:
        logger.info(f"Risk worker {WORKER_ID} starting...")
        logger.info(f"Connecting to Camunda at {CAMUNDA_URL}")
        logger.info(f"Topics: {[t['topicName'] for t in self.TOPICS]}")
        
        while self.running:
            try:
                tasks = self.client.fetch_and_lock(self.TOPICS, MAX_TASKS)
                for task in tasks:
                    self.process_task(task)
                if not tasks:
                    time.sleep(POLL_INTERVAL)
            except KeyboardInterrupt:
                logger.info("Shutdown requested...")
                self.running = False
            except Exception as e:
                logger.exception(f"Worker loop error: {e}")
                time.sleep(POLL_INTERVAL)
        
        logger.info("Risk worker stopped")
    
    def stop(self) -> None:
        self.running = False


def main():
    worker = RiskWorker()
    try:
        worker.run()
    except KeyboardInterrupt:
        worker.stop()


if __name__ == '__main__':
    main()