#!/bin/bash
# =============================================================================
# CAMUNDA INSURANCE PROCESS - END-TO-END TEST SCRIPT
# =============================================================================
#
# This script tests all three paths through the insurance process:
# 1. GREEN path (Auto-approve)
# 2. YELLOW path (Manual review)
# 3. RED path (Auto-reject)
#
# Prerequisites:
# - Camunda running on the specified URL
# - BPMN and DMN deployed
# - Python workers running
#
# Usage: ./test_process.sh [CAMUNDA_URL]
# =============================================================================

set -e

# Configuration
CAMUNDA_URL="${1:-http://localhost:8080}"
API_URL="${CAMUNDA_URL}/engine-rest"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}=============================================${NC}"
echo -e "${BLUE}  CAMUNDA INSURANCE PROCESS TEST SUITE${NC}"
echo -e "${BLUE}=============================================${NC}"
echo ""
echo "Camunda URL: ${CAMUNDA_URL}"
echo ""

# -----------------------------------------------------------------------------
# Helper Functions
# -----------------------------------------------------------------------------

check_camunda() {
    echo -n "Checking Camunda availability... "
    if curl -sf "${API_URL}/engine" > /dev/null; then
        echo -e "${GREEN}OK${NC}"
        return 0
    else
        echo -e "${RED}FAILED${NC}"
        echo "Error: Cannot connect to Camunda at ${CAMUNDA_URL}"
        exit 1
    fi
}

check_deployment() {
    echo -n "Checking process deployment... "
    PROCESS_COUNT=$(curl -sf "${API_URL}/process-definition/count" | grep -o '"count":[0-9]*' | cut -d: -f2)
    if [ "$PROCESS_COUNT" -gt 0 ]; then
        echo -e "${GREEN}OK${NC} ($PROCESS_COUNT process definitions found)"
        return 0
    else
        echo -e "${RED}FAILED${NC}"
        echo "Error: No process definitions deployed. Deploy BPMN first."
        exit 1
    fi
}

start_process() {
    local NAME="$1"
    local AGE="$2"
    local CAR_MAKE="$3"
    local CAR_MODEL="$4"
    local EXPECTED_RATING="$5"
    
    echo ""
    echo -e "${BLUE}Starting process instance:${NC}"
    echo "  Name: $NAME"
    echo "  Age: $AGE"
    echo "  Car: $CAR_MAKE $CAR_MODEL"
    echo "  Expected Rating: $EXPECTED_RATING"
    
    RESPONSE=$(curl -sf -X POST "${API_URL}/process-definition/key/insurance_process/start" \
        -H "Content-Type: application/json" \
        -d "{
            \"variables\": {
                \"applicantName\": {\"value\": \"$NAME\", \"type\": \"String\"},
                \"applicantEmail\": {\"value\": \"${NAME// /.}@test.com\", \"type\": \"String\"},
                \"age\": {\"value\": $AGE, \"type\": \"Integer\"},
                \"carMake\": {\"value\": \"$CAR_MAKE\", \"type\": \"String\"},
                \"carModel\": {\"value\": \"$CAR_MODEL\", \"type\": \"String\"},
                \"region\": {\"value\": \"London\", \"type\": \"String\"}
            }
        }")
    
    INSTANCE_ID=$(echo "$RESPONSE" | grep -o '"id":"[^"]*"' | head -1 | cut -d'"' -f4)
    
    if [ -n "$INSTANCE_ID" ]; then
        echo -e "  Instance ID: ${GREEN}$INSTANCE_ID${NC}"
        echo "$INSTANCE_ID"
    else
        echo -e "  ${RED}Failed to start process${NC}"
        echo ""
    fi
}

check_instance_status() {
    local INSTANCE_ID="$1"
    
    # Check if instance still exists (completed instances are removed)
    INSTANCE=$(curl -sf "${API_URL}/process-instance/$INSTANCE_ID" 2>/dev/null || echo "")
    
    if [ -z "$INSTANCE" ] || echo "$INSTANCE" | grep -q "does not exist"; then
        echo "COMPLETED"
    else
        # Check for active activities
        ACTIVITIES=$(curl -sf "${API_URL}/process-instance/$INSTANCE_ID/activity-instances")
        echo "$ACTIVITIES" | grep -o '"activityName":"[^"]*"' | head -1 | cut -d'"' -f4
    fi
}

get_variable() {
    local INSTANCE_ID="$1"
    local VAR_NAME="$2"
    
    RESULT=$(curl -sf "${API_URL}/process-instance/$INSTANCE_ID/variables/$VAR_NAME" 2>/dev/null || echo "")
    if [ -n "$RESULT" ]; then
        echo "$RESULT" | grep -o '"value":"[^"]*"' | cut -d'"' -f4
    else
        echo "N/A"
    fi
}

# -----------------------------------------------------------------------------
# Main Tests
# -----------------------------------------------------------------------------

echo ""
echo -e "${BLUE}=== PREREQUISITES ===${NC}"
check_camunda
check_deployment

echo ""
echo -e "${BLUE}=============================================${NC}"
echo -e "${BLUE}  TEST 1: GREEN PATH (Auto-Approve)${NC}"
echo -e "${BLUE}=============================================${NC}"
echo ""
echo "Scenario: 40-year-old with Toyota Corolla"
echo "Expected: Green rating -> Auto-approve -> Send approval email -> End"

GREEN_ID=$(start_process "Alice Green" 40 "Toyota" "Corolla" "Green")

if [ -n "$GREEN_ID" ]; then
    sleep 3
    STATUS=$(check_instance_status "$GREEN_ID")
    echo ""
    echo "  Status after 3s: $STATUS"
    
    if [ "$STATUS" = "COMPLETED" ]; then
        echo -e "  Result: ${GREEN}PASSED${NC} - Process completed as expected"
    else
        echo -e "  Result: ${YELLOW}IN PROGRESS${NC} - Current activity: $STATUS"
    fi
fi

echo ""
echo -e "${BLUE}=============================================${NC}"
echo -e "${BLUE}  TEST 2: YELLOW PATH (Manual Review)${NC}"
echo -e "${BLUE}=============================================${NC}"
echo ""
echo "Scenario: 25-year-old with BMW X3"
echo "Expected: Yellow rating -> User Task (Review Application)"

YELLOW_ID=$(start_process "Bob Yellow" 25 "BMW" "X3" "Yellow")

if [ -n "$YELLOW_ID" ]; then
    sleep 3
    STATUS=$(check_instance_status "$YELLOW_ID")
    echo ""
    echo "  Status after 3s: $STATUS"
    
    # Check for user tasks
    TASKS=$(curl -sf "${API_URL}/task?processInstanceId=$YELLOW_ID")
    TASK_COUNT=$(echo "$TASKS" | grep -o '"id"' | wc -l)
    
    if [ "$TASK_COUNT" -gt 0 ]; then
        TASK_ID=$(echo "$TASKS" | grep -o '"id":"[^"]*"' | head -1 | cut -d'"' -f4)
        TASK_NAME=$(echo "$TASKS" | grep -o '"name":"[^"]*"' | head -1 | cut -d'"' -f4)
        echo "  User Task Found: $TASK_NAME"
        echo "  Task ID: $TASK_ID"
        echo -e "  Result: ${GREEN}PASSED${NC} - Waiting for manual review as expected"
        
        echo ""
        echo "  To complete this task (approve):"
        echo "  curl -X POST '${API_URL}/task/$TASK_ID/complete' \\"
        echo "    -H 'Content-Type: application/json' \\"
        echo "    -d '{\"variables\":{\"accepted\":{\"value\":true,\"type\":\"Boolean\"}}}'"
    else
        echo -e "  Result: ${YELLOW}UNEXPECTED${NC} - No user task found"
    fi
fi

echo ""
echo -e "${BLUE}=============================================${NC}"
echo -e "${BLUE}  TEST 3: RED PATH (Auto-Reject)${NC}"
echo -e "${BLUE}=============================================${NC}"
echo ""
echo "Scenario: 22-year-old with Porsche 911"
echo "Expected: Red rating -> Rejected -> Send rejection email -> End"

RED_ID=$(start_process "Charlie Red" 22 "Porsche" "911" "Red")

if [ -n "$RED_ID" ]; then
    sleep 3
    STATUS=$(check_instance_status "$RED_ID")
    echo ""
    echo "  Status after 3s: $STATUS"
    
    if [ "$STATUS" = "COMPLETED" ]; then
        echo -e "  Result: ${GREEN}PASSED${NC} - Process completed (rejected) as expected"
    else
        echo -e "  Result: ${YELLOW}IN PROGRESS${NC} - Current activity: $STATUS"
    fi
fi

echo ""
echo -e "${BLUE}=============================================${NC}"
echo -e "${BLUE}  SUMMARY${NC}"
echo -e "${BLUE}=============================================${NC}"
echo ""

# Count active instances
ACTIVE=$(curl -sf "${API_URL}/process-instance/count" | grep -o '"count":[0-9]*' | cut -d: -f2)
echo "Active process instances: $ACTIVE"

# Count external tasks
EXT_TASKS=$(curl -sf "${API_URL}/external-task/count" | grep -o '"count":[0-9]*' | cut -d: -f2)
echo "Pending external tasks: $EXT_TASKS"

# Count user tasks
USER_TASKS=$(curl -sf "${API_URL}/task/count" | grep -o '"count":[0-9]*' | cut -d: -f2)
echo "Pending user tasks: $USER_TASKS"

# Count incidents
INCIDENTS=$(curl -sf "${API_URL}/incident/count" | grep -o '"count":[0-9]*' | cut -d: -f2)
if [ "$INCIDENTS" -gt 0 ]; then
    echo -e "Incidents: ${RED}$INCIDENTS${NC} (check Cockpit!)"
else
    echo -e "Incidents: ${GREEN}$INCIDENTS${NC}"
fi

echo ""
echo -e "${BLUE}=============================================${NC}"
echo -e "${BLUE}  TEST COMPLETE${NC}"
echo -e "${BLUE}=============================================${NC}"
echo ""
echo "Next steps:"
echo "1. Check Camunda Cockpit: ${CAMUNDA_URL}/camunda/app/cockpit/"
echo "2. Check worker logs: docker logs -f python-workers"
echo "3. Complete user tasks: ${CAMUNDA_URL}/camunda/app/tasklist/"