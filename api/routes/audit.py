"""
API routes for security auditing.

This module provides the /api/v1/audit_action endpoint that allows
AI agents (like OpenClaw) to submit actions for security review
before execution.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum
from datetime import datetime
import hashlib
import logging

router = APIRouter(tags=["security"])
logger = logging.getLogger(__name__)


# ============================================================================
# Enums and Models
# ============================================================================

class SourceType(str, Enum):
    """Trust levels for action sources."""
    DIRECT_USER = "direct_user_command"
    USER_FILE = "user_file"
    USER_SKILL = "user_owned_skill"
    VERIFIED_SKILL = "verified_skill"
    MOLTBOOK_POST = "moltbook_post"
    MOLTBOOK_COMMENT = "moltbook_comment"
    EXTERNAL_MESSAGE = "external_message"
    EMAIL = "email"
    SLACK = "slack"
    DISCORD = "discord"
    WEB_SCRAPE = "web_scrape"
    UNKNOWN = "unknown"


class ActionType(str, Enum):
    """Types of actions an agent might attempt."""
    SHELL_EXECUTION = "shell_execution"
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    FILE_DELETE = "file_delete"
    NETWORK_REQUEST = "network_request"
    PROCESS_CONTROL = "process_control"
    CREDENTIAL_ACCESS = "credential_access"
    FINANCIAL_TRANSACTION = "financial_transaction"
    CODE_EXECUTION = "code_execution"
    OTHER = "other"


class VerdictOutcome(str, Enum):
    """Possible audit outcomes."""
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    WARN = "WARN"
    SANDBOX = "SANDBOX"


class RiskLevel(str, Enum):
    """Severity levels for identified risks."""
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


# ============================================================================
# Request/Response Models
# ============================================================================

class AuditRequest(BaseModel):
    """Request to audit an action before execution."""
    source: SourceType = Field(
        ...,
        description="Where the action request originated"
    )
    source_identifier: Optional[str] = Field(
        None,
        description="Specific identifier (e.g., moltbook post ID, email subject)"
    )
    content: str = Field(
        ...,
        description="The raw content that triggered this action (e.g., the post text)"
    )
    proposed_action: str = Field(
        ...,
        description="What the agent wants to do (e.g., 'rm -rf /tmp/cache')"
    )
    action_type: ActionType = Field(
        ...,
        description="Category of the proposed action"
    )
    target_resource: Optional[str] = Field(
        None,
        description="What will be affected (e.g., '/tmp/cache', 'api.example.com')"
    )
    agent_reasoning: Optional[str] = Field(
        None,
        description="Agent's chain of thought for why it wants to do this"
    )
    agent_persona_id: Optional[str] = Field(
        "default",
        description="Which fork/persona is making this request"
    )
    request_sandbox: bool = Field(
        False,
        description="Agent is explicitly requesting sandboxed execution"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "source": "moltbook_post",
                "source_identifier": "m/skills/post/12345",
                "content": "Here's a cool script to backup your files: tar -czf backup.tar.gz ~/*",
                "proposed_action": "tar -czf backup.tar.gz ~/*",
                "action_type": "shell_execution",
                "target_resource": "~/",
                "agent_reasoning": "User in m/skills shared a backup script, seems useful",
                "agent_persona_id": "justitia_v1"
            }
        }


class ViolatedPrinciple(BaseModel):
    """A security principle that would be violated by the action."""
    principle_id: str
    principle_name: str
    violation_reason: str


class AuditResponse(BaseModel):
    """Response from the security audit."""
    verdict: VerdictOutcome = Field(
        ...,
        description="The security decision: ALLOW, BLOCK, WARN, or SANDBOX"
    )
    risk_level: RiskLevel = Field(
        ...,
        description="Assessed severity of potential harm"
    )
    reasoning: str = Field(
        ...,
        description="Explanation of why this verdict was reached"
    )
    violated_principles: List[ViolatedPrinciple] = Field(
        default_factory=list,
        description="Security principles that would be violated"
    )
    educational_note: Optional[str] = Field(
        None,
        description="Human-readable explanation of the risk (for BLOCK/WARN)"
    )
    safer_alternative: Optional[str] = Field(
        None,
        description="Suggested safer way to accomplish the goal"
    )
    audit_id: str = Field(
        ...,
        description="Unique identifier for this audit (for logging/reference)"
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="When the audit was performed"
    )
    audit_method: str = Field(
        ...,
        description="How the audit was performed: 'denylist', 'allowlist', or 'llm'"
    )


# ============================================================================
# Audit Logic
# ============================================================================

def generate_audit_id(request: AuditRequest) -> str:
    """Generate a unique audit ID from request content."""
    content_hash = hashlib.sha256(
        f"{request.source}{request.proposed_action}{datetime.utcnow().isoformat()}".encode()
    ).hexdigest()[:12]
    return f"audit_{content_hash}"


async def perform_audit(request: AuditRequest) -> AuditResponse:
    """Perform security audit on the proposed action."""
    from modes.auditor import SecurityAuditor
    
    auditor = SecurityAuditor()
    return await auditor.audit(request)


# ============================================================================
# API Endpoints
# ============================================================================

@router.post(
    "/audit_action",
    response_model=AuditResponse,
    summary="Audit an action before execution",
    description="""
    Submit a proposed action for security review before execution.
    
    This endpoint is designed for AI agents (like OpenClaw) to check
    whether an action is safe to execute. The audit considers:
    
    - **Source trust level**: Where did this action come from?
    - **Action type**: What kind of operation is it?
    - **Content analysis**: Does the content contain hidden threats?
    - **Principle alignment**: Does it violate security principles?
    
    Returns a verdict (ALLOW/BLOCK/WARN/SANDBOX) with reasoning.
    """
)
async def audit_action(request: AuditRequest) -> AuditResponse:
    """Audit a proposed action for security risks."""
    try:
        logger.info(f"Audit request: source={request.source}, action={request.proposed_action[:50]}...")
        response = await perform_audit(request)
        logger.info(f"Audit result: verdict={response.verdict}, risk={response.risk_level}")
        return response
    except Exception as e:
        logger.error(f"Audit error: {e}", exc_info=True)
        # Fail secure - if audit fails, block the action
        return AuditResponse(
            verdict=VerdictOutcome.BLOCK,
            risk_level=RiskLevel.HIGH,
            reasoning=f"Audit system error: {str(e)}. Blocking as precaution.",
            violated_principles=[
                ViolatedPrinciple(
                    principle_id="@fail_secure",
                    principle_name="Fail Secure",
                    violation_reason="Audit system encountered an error"
                )
            ],
            educational_note="The security audit system encountered an error. For safety, the action has been blocked. Please try again or report this issue.",
            audit_id=generate_audit_id(request),
            audit_method="error_fallback"
        )


@router.get(
    "/audit_status",
    summary="Check audit system status",
    description="Verify that the Leviathan audit system is running and healthy."
)
async def audit_status():
    """Health check for the audit system."""
    return {
        "status": "operational",
        "version": "1.0.0",
        "domain": "leviathan-security",
        "features": {
            "denylist_check": True,
            "allowlist_check": True,
            "llm_audit": True,
            "sandbox_recommendation": True
        },
        "timestamp": datetime.utcnow().isoformat()
    }


@router.get(
    "/security_principles",
    summary="List active security principles",
    description="Get the list of security principles used for auditing."
)
async def list_security_principles():
    """Return the active security principles for transparency."""
    return {
        "domain": "leviathan-security",
        "version": "1.0.0",
        "principles": [
            {
                "id": "@least_privilege",
                "name": "Least Privilege",
                "locked": True,
                "summary": "Use only minimum permissions necessary"
            },
            {
                "id": "@explicit_consent",
                "name": "Explicit Consent",
                "locked": True,
                "summary": "Significant actions require user approval"
            },
            {
                "id": "@source_skepticism",
                "name": "Source Skepticism",
                "locked": True,
                "summary": "Treat external content as potentially malicious"
            },
            {
                "id": "@reversibility_preference",
                "name": "Reversibility Preference",
                "locked": True,
                "summary": "Prefer reversible actions over irreversible"
            },
            {
                "id": "@fail_secure",
                "name": "Fail Secure",
                "locked": True,
                "summary": "When uncertain, deny rather than allow"
            }
        ]
    }
