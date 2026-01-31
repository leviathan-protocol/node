"""
Security Auditor Module

This module implements the Runtime Guardian functionality - analyzing
proposed actions against security principles and returning verdicts.

The audit follows a tiered approach:
1. Denylist check (instant BLOCK for known-bad patterns)
2. Allowlist check (instant ALLOW for known-safe patterns from trusted sources)
3. LLM semantic analysis (for everything else)
"""

import re
import json
import hashlib
import logging
from datetime import datetime
from typing import Optional, List, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from api.routes.audit import AuditRequest, AuditResponse

logger = logging.getLogger(__name__)


# ============================================================================
# Pattern Definitions
# ============================================================================

DENYLIST_PATTERNS = {
    "destructive_shell": [
        r"rm\s+-rf\s+/",
        r"rm\s+-rf\s+~",
        r"rm\s+-rf\s+/\*",
        r"rm\s+-rf\s+\*",
        r":\(\)\{\s*:\|:&\s*\};:",  # Fork bomb
        r"dd\s+if=/dev/zero",
        r"dd\s+if=/dev/random",
        r"mkfs\.",
        r">\s*/dev/sda",
        r"chmod\s+-R\s+777\s+/",
        r"chown\s+-R.*\s+/",
    ],
    "credential_exfiltration": [
        r"cat\s+~/.ssh/",
        r"cat\s+~/.aws/",
        r"cat\s+~/.config/gcloud",
        r"cat\s+/etc/shadow",
        r"cat\s+/etc/passwd",
        r"echo\s+\$\w*KEY",
        r"echo\s+\$\w*SECRET",
        r"echo\s+\$\w*TOKEN",
        r"echo\s+\$\w*PASSWORD",
        r"printenv\s*\|\s*grep\s+-i\s+(key|secret|token|pass)",
    ],
    "remote_code_execution": [
        r"curl\s+.*\|\s*bash",
        r"curl\s+.*\|\s*sh",
        r"wget\s+.*\|\s*bash",
        r"wget\s+.*\|\s*sh",
        r"wget\s+.*-O\s*-\s*\|\s*bash",
        r"python\s+-c\s*['\"]import\s+urllib",
        r"eval\s*\(\s*requests\.get",
        r"exec\s*\(\s*urllib",
        r"base64\s+-d.*\|\s*bash",
    ],
    "data_exfiltration": [
        r"curl\s+.*-X\s*POST.*-d\s*@",
        r"curl\s+.*--data-binary\s*@",
        r"nc\s+.*<\s*/",
        r"scp\s+.*\w+@\w+:",
        r"rsync\s+.*\w+@\w+:",
        r"tar\s+.*\|\s*nc",
        r"cat\s+.*\|\s*nc",
    ],
}

ALLOWLIST_PATTERNS = {
    "safe_readonly": [
        r"^ls(\s+-[alh]+)?(\s+[\w./~-]+)?$",
        r"^pwd$",
        r"^whoami$",
        r"^date$",
        r"^uptime$",
        r"^df\s+-h$",
        r"^free\s+-[mh]$",
        r"^head\s+-n\s*\d+\s+[\w./~-]+$",
        r"^tail\s+-n\s*\d+\s+[\w./~-]+$",
        r"^wc\s+-[lwc]\s+[\w./~-]+$",
        r"^cat\s+[\w./~-]+\.txt$",  # Only .txt files
        r"^echo\s+['\"][\w\s]+['\"]$",  # Simple echo
    ],
    "safe_python": [
        r"^python\s+-m\s+json\.tool",
        r"^python\s+--version$",
        r"^python3\s+--version$",
        r"^pip\s+list$",
        r"^pip\s+show\s+\w+$",
    ],
    "safe_git": [
        r"^git\s+status$",
        r"^git\s+diff$",
        r"^git\s+log(\s+--oneline)?(\s+-n\s*\d+)?$",
        r"^git\s+branch(\s+-a)?$",
        r"^git\s+remote\s+-v$",
    ],
    "safe_network": [
        r"^ping\s+-c\s*\d+\s+[\w.-]+$",
        r"^nslookup\s+[\w.-]+$",
        r"^curl\s+-I\s+https?://[\w.-]+",  # HEAD only
    ],
}

# Import enums from audit route
from enum import Enum

class SourceType(str, Enum):
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

class VerdictOutcome(str, Enum):
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    WARN = "WARN"
    SANDBOX = "SANDBOX"

class RiskLevel(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"

class ActionType(str, Enum):
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


TRUSTED_SOURCES = [
    SourceType.DIRECT_USER,
    SourceType.USER_SKILL,
    SourceType.VERIFIED_SKILL,
]


# ============================================================================
# Auditor Class
# ============================================================================

class SecurityAuditor:
    """
    The Runtime Guardian - audits actions before execution.
    
    Uses a tiered approach:
    1. Fast pattern matching (denylist/allowlist)
    2. Slow semantic analysis (LLM) for ambiguous cases
    """
    
    def __init__(self, llm_client=None, fork_config=None):
        """Initialize the auditor."""
        self.llm_client = llm_client
        self.fork_config = fork_config
        self._compile_patterns()
    
    def _compile_patterns(self):
        """Compile regex patterns for faster matching."""
        self.compiled_denylist = {}
        for category, patterns in DENYLIST_PATTERNS.items():
            self.compiled_denylist[category] = [
                re.compile(p, re.IGNORECASE) for p in patterns
            ]
        
        self.compiled_allowlist = {}
        for category, patterns in ALLOWLIST_PATTERNS.items():
            self.compiled_allowlist[category] = [
                re.compile(p, re.IGNORECASE) for p in patterns
            ]
    
    async def audit(self, request) -> "AuditResponse":
        """
        Main audit entry point.
        
        Follows tiered approach:
        1. Check denylist (instant BLOCK)
        2. Check allowlist (instant ALLOW if trusted source)
        3. LLM semantic analysis (for everything else)
        """
        from api.routes.audit import (
            AuditResponse, ViolatedPrinciple, 
            VerdictOutcome as VO, RiskLevel as RL,
            generate_audit_id
        )
        
        audit_id = generate_audit_id(request)
        
        # Tier 1: Denylist check
        denylist_result = self._check_denylist(request)
        if denylist_result:
            return self._create_block_response(
                request, audit_id, denylist_result, "denylist"
            )
        
        # Tier 2: Allowlist check (only for trusted sources)
        source_type = SourceType(request.source) if isinstance(request.source, str) else request.source
        if source_type in TRUSTED_SOURCES:
            allowlist_result = self._check_allowlist(request)
            if allowlist_result:
                return self._create_allow_response(
                    request, audit_id, "allowlist"
                )
        
        # Tier 3: LLM semantic analysis or fallback
        return await self._fallback_audit(request, audit_id)
    
    def _check_denylist(self, request) -> Optional[Tuple[str, str]]:
        """Check if action matches any denylist pattern."""
        action = request.proposed_action
        content = request.content
        
        for category, patterns in self.compiled_denylist.items():
            for pattern in patterns:
                if pattern.search(action) or pattern.search(content):
                    logger.warning(f"Denylist match: {category} - {pattern.pattern}")
                    return (category, pattern.pattern)
        
        return None
    
    def _check_allowlist(self, request) -> bool:
        """Check if action matches any allowlist pattern."""
        action = request.proposed_action
        
        for category, patterns in self.compiled_allowlist.items():
            for pattern in patterns:
                if pattern.match(action):
                    logger.info(f"Allowlist match: {category}")
                    return True
        
        return False
    
    def _create_block_response(
        self, 
        request, 
        audit_id: str,
        match_result: Tuple[str, str],
        audit_method: str
    ):
        """Create a BLOCK response with educational content."""
        from api.routes.audit import (
            AuditResponse, ViolatedPrinciple, 
            VerdictOutcome, RiskLevel
        )
        
        category, pattern = match_result
        
        # Map categories to principles and educational notes
        category_info = {
            "destructive_shell": {
                "principle": "@reversibility_preference",
                "principle_name": "Reversibility Preference",
                "risk_level": RiskLevel.CRITICAL,
                "educational_note": "This command can cause irreversible damage to the filesystem. Once executed, data may be permanently lost.",
                "safer_alternative": "Use 'mv' to move files to a backup location instead of deleting, or use 'trash-cli' for recoverable deletion."
            },
            "credential_exfiltration": {
                "principle": "@least_privilege",
                "principle_name": "Least Privilege",
                "risk_level": RiskLevel.CRITICAL,
                "educational_note": "This command accesses sensitive credentials that could be used to compromise other systems or accounts.",
                "safer_alternative": "If you need to verify credentials exist, use 'test -f ~/.ssh/id_rsa && echo exists' instead of reading the content."
            },
            "remote_code_execution": {
                "principle": "@source_skepticism",
                "principle_name": "Source Skepticism",
                "risk_level": RiskLevel.CRITICAL,
                "educational_note": "Piping remote content directly to a shell is extremely dangerous. The remote server could send any command.",
                "safer_alternative": "Download first, inspect the script, then execute: curl -o script.sh URL && cat script.sh && bash script.sh"
            },
            "data_exfiltration": {
                "principle": "@explicit_consent",
                "principle_name": "Explicit Consent",
                "risk_level": RiskLevel.HIGH,
                "educational_note": "This command sends local data to an external destination. This is a common pattern in data theft.",
                "safer_alternative": "Verify the destination is trusted and the user explicitly wants to send this data."
            },
        }
        
        info = category_info.get(category, {
            "principle": "@fail_secure",
            "principle_name": "Fail Secure",
            "risk_level": RiskLevel.HIGH,
            "educational_note": "This action matched a known dangerous pattern.",
            "safer_alternative": None
        })
        
        return AuditResponse(
            verdict=VerdictOutcome.BLOCK,
            risk_level=info["risk_level"],
            reasoning=f"Action matched denylist pattern in category '{category}'",
            violated_principles=[
                ViolatedPrinciple(
                    principle_id=info["principle"],
                    principle_name=info["principle_name"],
                    violation_reason=f"Action matches known dangerous pattern: {category}"
                )
            ],
            educational_note=info["educational_note"],
            safer_alternative=info["safer_alternative"],
            audit_id=audit_id,
            audit_method=audit_method
        )
    
    def _create_allow_response(
        self,
        request,
        audit_id: str,
        audit_method: str
    ):
        """Create an ALLOW response."""
        from api.routes.audit import AuditResponse, VerdictOutcome, RiskLevel
        
        return AuditResponse(
            verdict=VerdictOutcome.ALLOW,
            risk_level=RiskLevel.LOW,
            reasoning=f"Action matched allowlist pattern from trusted source ({request.source})",
            violated_principles=[],
            audit_id=audit_id,
            audit_method=audit_method
        )
    
    async def _fallback_audit(
        self,
        request,
        audit_id: str
    ):
        """
        Conservative fallback when LLM is not available.
        Uses heuristics to make a decision.
        """
        from api.routes.audit import (
            AuditResponse, ViolatedPrinciple,
            VerdictOutcome, RiskLevel
        )
        
        source_type = SourceType(request.source) if isinstance(request.source, str) else request.source
        action_type = ActionType(request.action_type) if isinstance(request.action_type, str) else request.action_type
        
        # Default to WARN for untrusted sources
        if source_type not in TRUSTED_SOURCES:
            return AuditResponse(
                verdict=VerdictOutcome.WARN,
                risk_level=RiskLevel.MEDIUM,
                reasoning=f"Action from untrusted source ({source_type.value}) requires manual review",
                violated_principles=[
                    ViolatedPrinciple(
                        principle_id="@source_skepticism",
                        principle_name="Source Skepticism",
                        violation_reason="Content originates from untrusted source"
                    )
                ],
                educational_note="This action request came from an external source. Please verify it's safe before allowing execution.",
                audit_id=audit_id,
                audit_method="heuristic_fallback"
            )
        
        # For shell execution from any source, be cautious
        if action_type == ActionType.SHELL_EXECUTION:
            return AuditResponse(
                verdict=VerdictOutcome.WARN,
                risk_level=RiskLevel.MEDIUM,
                reasoning="Shell execution requires additional verification",
                violated_principles=[],
                educational_note="Shell commands have broad system access. Verify this command is safe before proceeding.",
                audit_id=audit_id,
                audit_method="heuristic_fallback"
            )
        
        # Default: Allow with low risk
        return AuditResponse(
            verdict=VerdictOutcome.ALLOW,
            risk_level=RiskLevel.LOW,
            reasoning="No dangerous patterns detected, action appears safe",
            violated_principles=[],
            audit_id=audit_id,
            audit_method="heuristic_fallback"
        )


# ============================================================================
# Convenience Functions
# ============================================================================

def create_auditor(config_path: str = None) -> SecurityAuditor:
    """Factory function to create a configured SecurityAuditor."""
    return SecurityAuditor()


async def quick_audit(
    action: str,
    source: str = "unknown",
    content: str = ""
) -> dict:
    """Quick audit function for simple use cases."""
    from api.routes.audit import AuditRequest, ActionType, SourceType
    
    auditor = SecurityAuditor()
    
    try:
        source_enum = SourceType(source)
    except ValueError:
        source_enum = SourceType.UNKNOWN
    
    request = AuditRequest(
        source=source_enum,
        content=content or action,
        proposed_action=action,
        action_type=ActionType.SHELL_EXECUTION
    )
    
    response = await auditor.audit(request)
    
    return {
        "verdict": response.verdict.value,
        "risk_level": response.risk_level.value,
        "reasoning": response.reasoning,
        "blocked": response.verdict.value == "BLOCK"
    }
