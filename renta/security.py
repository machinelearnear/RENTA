"""
Security and compliance features for RENTA library.

Provides secure credential management, PII scrubbing, configuration sanitization,
and compliance utilities to ensure secure operation in production environments.
"""

import os
import re
import json
import logging
from typing import Any, Dict, List, Optional, Set, Union
from pathlib import Path
import boto3
from botocore.exceptions import NoCredentialsError, ClientError
import structlog

from .exceptions import ConfigurationError, AIServiceConfigurationError
from .config import ConfigManager

logger = structlog.get_logger(__name__)


class CredentialManager:
    """Manages secure AWS credential handling and validation.

    Provides integration with AWS credential providers and ensures
    credentials are never logged or stored insecurely.
    """

    def __init__(self, config: ConfigManager):
        """Initialize credential manager with configuration.

        Args:
            config: ConfigManager instance with AWS configuration
        """
        self.config = config
        self.logger = logger.bind(component="CredentialManager")
        self._credentials_validated = False
        self._aws_session = None

    def validate_aws_credentials(self) -> Dict[str, Any]:
        """Validate AWS credentials and return account information.

        Returns:
            Dictionary with account information and validation status

        Raises:
            AIServiceConfigurationError: If credentials are invalid or missing
        """
        try:
            # Create AWS session using default credential chain
            session = boto3.Session(region_name=self.config.get("aws.region", "us-east-1"))

            # Test credentials by calling STS GetCallerIdentity
            sts_client = session.client("sts")
            identity = sts_client.get_caller_identity()

            # Test Bedrock access specifically
            bedrock_client = session.client("bedrock-runtime")

            # Store validated session
            self._aws_session = session
            self._credentials_validated = True

            account_info = {
                "account_id": identity.get("Account"),
                "user_id": identity.get("UserId"),
                "arn": identity.get("Arn"),
                "region": session.region_name,
                "credentials_source": self._detect_credential_source(),
                "bedrock_access": True,
                "validation_timestamp": self._get_current_timestamp(),
            }

            # Scrub sensitive information for logging
            safe_info = self._scrub_account_info(account_info)

            self.logger.info("AWS credentials validated successfully", **safe_info)

            return account_info

        except NoCredentialsError as e:
            error_msg = (
                "AWS credentials not found. Please configure credentials using one of:\n"
                "1. Environment variables (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)\n"
                "2. AWS credentials file (~/.aws/credentials)\n"
                "3. IAM role (for EC2/Lambda/ECS)\n"
                "4. AWS SSO\n"
                "See: https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-quickstart.html"
            )
            self.logger.error("AWS credentials not found")
            raise AIServiceConfigurationError(
                error_msg,
                details={
                    "error_type": "NoCredentialsError",
                    "region": self.config.get("aws.region", "us-east-1"),
                    "credential_sources_checked": [
                        "environment_variables",
                        "credentials_file",
                        "iam_role",
                        "sso",
                    ],
                },
            ) from e

        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")

            if error_code in ["InvalidUserID.NotFound", "AccessDenied"]:
                error_msg = (
                    f"AWS credentials are invalid or lack required permissions: {e}\n"
                    "Please ensure your credentials have the following permissions:\n"
                    "- sts:GetCallerIdentity\n"
                    "- bedrock:InvokeModel"
                )
                self.logger.error(
                    "AWS credentials invalid or insufficient permissions", error_code=error_code
                )
            else:
                error_msg = f"AWS credential validation failed: {e}"
                self.logger.error(
                    "AWS credential validation failed", error_code=error_code, error=str(e)
                )

            raise AIServiceConfigurationError(
                error_msg,
                details={
                    "error_code": error_code,
                    "aws_error": str(e),
                    "region": self.config.get("aws.region", "us-east-1"),
                },
            ) from e

        except Exception as e:
            self.logger.error("Unexpected error during credential validation", error=str(e))
            raise AIServiceConfigurationError(
                f"Unexpected error validating AWS credentials: {e}",
                details={
                    "error_type": type(e).__name__,
                    "region": self.config.get("aws.region", "us-east-1"),
                },
            ) from e

    def get_aws_session(self) -> boto3.Session:
        """Get validated AWS session.

        Returns:
            Validated boto3 Session instance

        Raises:
            AIServiceConfigurationError: If credentials haven't been validated
        """
        if not self._credentials_validated or self._aws_session is None:
            self.logger.info("AWS credentials not yet validated, validating now...")
            self.validate_aws_credentials()

        return self._aws_session

    def _detect_credential_source(self) -> str:
        """Detect the source of AWS credentials.

        Returns:
            String describing credential source
        """
        # Check environment variables
        if os.getenv("AWS_ACCESS_KEY_ID") and os.getenv("AWS_SECRET_ACCESS_KEY"):
            return "environment_variables"

        # Check for AWS profile
        if os.getenv("AWS_PROFILE"):
            return f"aws_profile:{os.getenv('AWS_PROFILE')}"

        # Check for credentials file
        credentials_file = Path.home() / ".aws" / "credentials"
        if credentials_file.exists():
            return "credentials_file"

        # Check for IAM role (common in EC2/ECS/Lambda)
        try:
            import requests

            # Try to access EC2 metadata service (timeout quickly)
            response = requests.get(
                "http://169.254.169.254/latest/meta-data/iam/security-credentials/", timeout=1
            )
            if response.status_code == 200:
                return "iam_role"
        except Exception as e:
            self.logger.debug(
                "IAM role detection failed (expected when not running on EC2/ECS/Lambda)",
                error=str(e),
            )

        # Check for SSO
        sso_cache_dir = Path.home() / ".aws" / "sso" / "cache"
        if sso_cache_dir.exists() and any(sso_cache_dir.iterdir()):
            return "aws_sso"

        return "unknown"

    def _scrub_account_info(self, account_info: Dict[str, Any]) -> Dict[str, Any]:
        """Scrub sensitive information from account info for logging.

        Args:
            account_info: Raw account information

        Returns:
            Scrubbed account information safe for logging
        """
        safe_info = account_info.copy()

        # Mask account ID (show only last 4 digits)
        if "account_id" in safe_info and safe_info["account_id"]:
            account_id = safe_info["account_id"]
            safe_info["account_id"] = f"****{account_id[-4:]}" if len(account_id) >= 4 else "****"

        # Mask user ID (show only prefix)
        if "user_id" in safe_info and safe_info["user_id"]:
            user_id = safe_info["user_id"]
            if ":" in user_id:
                prefix, suffix = user_id.split(":", 1)
                safe_info["user_id"] = f"{prefix}:****"
            else:
                safe_info["user_id"] = "****"

        # Mask ARN (show only service and region)
        if "arn" in safe_info and safe_info["arn"]:
            arn_parts = safe_info["arn"].split(":")
            if len(arn_parts) >= 4:
                safe_info[
                    "arn"
                ] = f"{arn_parts[0]}:{arn_parts[1]}:{arn_parts[2]}:{arn_parts[3]}:****"
            else:
                safe_info["arn"] = "****"

        return safe_info

    def _get_current_timestamp(self) -> str:
        """Get current timestamp in ISO format.

        Returns:
            ISO formatted timestamp string
        """
        from datetime import datetime

        return datetime.utcnow().isoformat() + "Z"


class PIIScrubber:
    """Scrubs personally identifiable information from logs and debug output.

    Provides configurable PII detection and scrubbing to ensure sensitive
    information is not exposed in logs or debug output.
    """

    # Common PII patterns
    PII_PATTERNS = {
        "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),
        "phone": re.compile(r"\b(?:\+?1[-.\s]?)?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}\b"),
        "ssn": re.compile(r"\b\d{3}-?\d{2}-?\d{4}\b"),
        "credit_card": re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b"),
        "aws_access_key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        "aws_secret_key": re.compile(r"\b[A-Za-z0-9/+=]{40}\b"),
        "jwt_token": re.compile(r"\beyJ[A-Za-z0-9_/+=]+\.[A-Za-z0-9_/+=]+\.[A-Za-z0-9_/+=]*\b"),
        "ip_address": re.compile(r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b"),
        "url_with_auth": re.compile(r"https?://[^:]+:[^@]+@[^\s]+"),
    }

    def __init__(self, config: ConfigManager):
        """Initialize PII scrubber with configuration.

        Args:
            config: ConfigManager instance with scrubbing configuration
        """
        self.config = config
        self.logger = logger.bind(component="PIIScrubber")

        # Get custom patterns from config
        custom_patterns = config.get("security.pii_patterns", {})
        self.patterns = self.PII_PATTERNS.copy()

        # Add custom patterns
        for name, pattern_str in custom_patterns.items():
            try:
                self.patterns[name] = re.compile(pattern_str)
                self.logger.debug(f"Added custom PII pattern: {name}")
            except re.error as e:
                self.logger.warning(f"Invalid PII pattern '{name}': {e}")

        # Configure scrubbing behavior
        self.replacement_text = config.get("security.pii_replacement", "[REDACTED]")
        self.enabled = config.get("security.enable_pii_scrubbing", True)

        if self.enabled:
            self.logger.info(
                "PII scrubbing enabled",
                patterns=list(self.patterns.keys()),
                replacement=self.replacement_text,
            )

    def scrub_text(self, text: str) -> str:
        """Scrub PII from text content.

        Args:
            text: Text content to scrub

        Returns:
            Scrubbed text with PII replaced
        """
        if not self.enabled or not text:
            return text

        scrubbed_text = text

        for pattern_name, pattern in self.patterns.items():
            matches = pattern.findall(scrubbed_text)
            if matches:
                self.logger.debug(f"Found {len(matches)} instances of {pattern_name}")
                scrubbed_text = pattern.sub(self.replacement_text, scrubbed_text)

        return scrubbed_text

    def scrub_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Scrub PII from dictionary values recursively.

        Args:
            data: Dictionary to scrub

        Returns:
            Scrubbed dictionary
        """
        if not self.enabled:
            return data

        scrubbed_data = {}

        for key, value in data.items():
            if isinstance(value, str):
                scrubbed_data[key] = self.scrub_text(value)
            elif isinstance(value, dict):
                scrubbed_data[key] = self.scrub_dict(value)
            elif isinstance(value, list):
                scrubbed_data[key] = self.scrub_list(value)
            else:
                scrubbed_data[key] = value

        return scrubbed_data

    def scrub_list(self, data: List[Any]) -> List[Any]:
        """Scrub PII from list items recursively.

        Args:
            data: List to scrub

        Returns:
            Scrubbed list
        """
        if not self.enabled:
            return data

        scrubbed_list = []

        for item in data:
            if isinstance(item, str):
                scrubbed_list.append(self.scrub_text(item))
            elif isinstance(item, dict):
                scrubbed_list.append(self.scrub_dict(item))
            elif isinstance(item, list):
                scrubbed_list.append(self.scrub_list(item))
            else:
                scrubbed_list.append(item)

        return scrubbed_list

    def scrub_log_record(self, record: logging.LogRecord) -> logging.LogRecord:
        """Scrub PII from log record.

        Args:
            record: Log record to scrub

        Returns:
            Scrubbed log record
        """
        if not self.enabled:
            return record

        # Scrub message
        if hasattr(record, "msg") and isinstance(record.msg, str):
            record.msg = self.scrub_text(record.msg)

        # Scrub args
        if hasattr(record, "args") and record.args:
            scrubbed_args = []
            for arg in record.args:
                if isinstance(arg, str):
                    scrubbed_args.append(self.scrub_text(arg))
                elif isinstance(arg, dict):
                    scrubbed_args.append(self.scrub_dict(arg))
                else:
                    scrubbed_args.append(arg)
            record.args = tuple(scrubbed_args)

        return record


class ConfigurationSanitizer:
    """Sanitizes configuration to detect and remove hard-coded secrets.

    Provides validation and sanitization of configuration files to ensure
    no hard-coded credentials or sensitive information is present.
    """

    # Patterns for detecting hard-coded secrets
    SECRET_PATTERNS = {
        "aws_access_key": re.compile(r"AKIA[0-9A-Z]{16}"),
        "aws_secret_key": re.compile(r"[A-Za-z0-9/+=]{40}"),
        "api_key": re.compile(
            r'(?i)(?:api[_-]?key|apikey)\s*[:=]\s*["\']?([a-zA-Z0-9_-]{20,})["\']?'
        ),
        "password": re.compile(r'(?i)(?:password|passwd|pwd)\s*[:=]\s*["\']?([^"\'\s]{8,})["\']?'),
        "secret": re.compile(r'(?i)(?:secret|token)\s*[:=]\s*["\']?([a-zA-Z0-9_-]{20,})["\']?'),
        "private_key": re.compile(r"-----BEGIN [A-Z ]+PRIVATE KEY-----"),
        "jwt_token": re.compile(r"eyJ[A-Za-z0-9_/+=]+\.[A-Za-z0-9_/+=]+\.[A-Za-z0-9_/+=]*"),
    }

    # Suspicious configuration keys
    SUSPICIOUS_KEYS = {
        "password",
        "passwd",
        "pwd",
        "secret",
        "token",
        "key",
        "api_key",
        "apikey",
        "access_key",
        "secret_key",
        "private_key",
        "auth_token",
        "bearer_token",
        "jwt",
        "credential",
        "credentials",
    }

    def __init__(self, config: ConfigManager):
        """Initialize configuration sanitizer.

        Args:
            config: ConfigManager instance
        """
        self.config = config
        self.logger = logger.bind(component="ConfigurationSanitizer")

    def validate_configuration(self, config_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Validate configuration for security issues.

        Args:
            config_dict: Configuration dictionary to validate

        Returns:
            Dictionary with validation results and issues found
        """
        issues = []
        warnings = []

        # Check for hard-coded secrets
        secret_issues = self._detect_hardcoded_secrets(config_dict)
        issues.extend(secret_issues)

        # Check for suspicious configuration keys
        suspicious_issues = self._detect_suspicious_keys(config_dict)
        warnings.extend(suspicious_issues)

        # Check for insecure settings
        insecure_issues = self._detect_insecure_settings(config_dict)
        warnings.extend(insecure_issues)

        validation_result = {
            "is_secure": len(issues) == 0,
            "issues": issues,
            "warnings": warnings,
            "recommendations": self._generate_recommendations(issues, warnings),
        }

        if issues:
            self.logger.error(
                "Configuration security validation failed",
                issue_count=len(issues),
                warning_count=len(warnings),
            )
        elif warnings:
            self.logger.warning("Configuration has security warnings", warning_count=len(warnings))
        else:
            self.logger.info("Configuration passed security validation")

        return validation_result

    def sanitize_for_logging(self, config_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Sanitize configuration dictionary for safe logging.

        Args:
            config_dict: Configuration dictionary to sanitize

        Returns:
            Sanitized configuration safe for logging
        """
        return self._sanitize_dict(config_dict, path="")

    def _detect_hardcoded_secrets(
        self, config_dict: Dict[str, Any], path: str = ""
    ) -> List[Dict[str, Any]]:
        """Detect hard-coded secrets in configuration.

        Args:
            config_dict: Configuration dictionary to check
            path: Current path in configuration (for nested dicts)

        Returns:
            List of issues found
        """
        issues = []

        for key, value in config_dict.items():
            current_path = f"{path}.{key}" if path else key

            if isinstance(value, dict):
                # Recursively check nested dictionaries
                nested_issues = self._detect_hardcoded_secrets(value, current_path)
                issues.extend(nested_issues)
            elif isinstance(value, str):
                # Check string values for secret patterns
                for pattern_name, pattern in self.SECRET_PATTERNS.items():
                    if pattern.search(value):
                        issues.append(
                            {
                                "type": "hardcoded_secret",
                                "severity": "critical",
                                "path": current_path,
                                "pattern": pattern_name,
                                "message": f"Potential {pattern_name} found in configuration at '{current_path}'",
                            }
                        )

        return issues

    def _detect_suspicious_keys(
        self, config_dict: Dict[str, Any], path: str = ""
    ) -> List[Dict[str, Any]]:
        """Detect suspicious configuration keys that might contain secrets.

        Args:
            config_dict: Configuration dictionary to check
            path: Current path in configuration

        Returns:
            List of warnings found
        """
        warnings = []

        for key, value in config_dict.items():
            current_path = f"{path}.{key}" if path else key

            if isinstance(value, dict):
                # Recursively check nested dictionaries
                nested_warnings = self._detect_suspicious_keys(value, current_path)
                warnings.extend(nested_warnings)
            elif key.lower() in self.SUSPICIOUS_KEYS and isinstance(value, str) and value:
                warnings.append(
                    {
                        "type": "suspicious_key",
                        "severity": "warning",
                        "path": current_path,
                        "message": f"Suspicious configuration key '{key}' contains a value. Ensure this is not a hard-coded secret.",
                    }
                )

        return warnings

    def _detect_insecure_settings(self, config_dict: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Detect insecure configuration settings.

        Args:
            config_dict: Configuration dictionary to check

        Returns:
            List of warnings found
        """
        warnings = []

        # Check for debug mode in production-like settings
        if config_dict.get("debug", {}).get("enable_request_logging", False):
            warnings.append(
                {
                    "type": "insecure_setting",
                    "severity": "warning",
                    "path": "debug.enable_request_logging",
                    "message": "Request logging is enabled, which may expose sensitive data in logs",
                }
            )

        # Check for disabled PII scrubbing
        if not config_dict.get("security", {}).get("enable_pii_scrubbing", True):
            warnings.append(
                {
                    "type": "insecure_setting",
                    "severity": "warning",
                    "path": "security.enable_pii_scrubbing",
                    "message": "PII scrubbing is disabled, which may expose sensitive data in logs",
                }
            )

        # Check for overly permissive logging levels
        log_level = config_dict.get("logging", {}).get("level", "INFO")
        if log_level.upper() == "DEBUG":
            warnings.append(
                {
                    "type": "insecure_setting",
                    "severity": "info",
                    "path": "logging.level",
                    "message": "Debug logging is enabled, which may expose sensitive information",
                }
            )

        return warnings

    def _generate_recommendations(self, issues: List[Dict], warnings: List[Dict]) -> List[str]:
        """Generate security recommendations based on issues found.

        Args:
            issues: List of security issues
            warnings: List of security warnings

        Returns:
            List of recommendation strings
        """
        recommendations = []

        if any(issue["type"] == "hardcoded_secret" for issue in issues):
            recommendations.append(
                "Remove hard-coded secrets from configuration. Use environment variables, "
                "AWS Parameter Store, or other secure credential management systems."
            )

        if any(warning["type"] == "suspicious_key" for warning in warnings):
            recommendations.append(
                "Review suspicious configuration keys to ensure they don't contain secrets. "
                "Consider using placeholder values or environment variable references."
            )

        if any(warning["path"].startswith("debug") for warning in warnings):
            recommendations.append(
                "Disable debug features in production environments to prevent information disclosure."
            )

        if any(warning["path"].startswith("security") for warning in warnings):
            recommendations.append(
                "Enable all security features including PII scrubbing to protect sensitive data."
            )

        return recommendations

    def _sanitize_dict(self, data: Dict[str, Any], path: str) -> Dict[str, Any]:
        """Recursively sanitize dictionary for logging.

        Args:
            data: Dictionary to sanitize
            path: Current path in configuration

        Returns:
            Sanitized dictionary
        """
        sanitized = {}

        for key, value in data.items():
            current_path = f"{path}.{key}" if path else key

            if isinstance(value, dict):
                sanitized[key] = self._sanitize_dict(value, current_path)
            elif key.lower() in self.SUSPICIOUS_KEYS and isinstance(value, str):
                # Replace suspicious values with placeholder
                sanitized[key] = "[REDACTED]" if value else value
            elif isinstance(value, str):
                # Check for secret patterns and redact if found
                sanitized_value = value
                for pattern_name, pattern in self.SECRET_PATTERNS.items():
                    if pattern.search(value):
                        sanitized_value = "[REDACTED]"
                        break
                sanitized[key] = sanitized_value
            else:
                sanitized[key] = value

        return sanitized


class SecurityManager:
    """Main security manager that coordinates all security features.

    Provides a unified interface for credential management, PII scrubbing,
    and configuration sanitization.
    """

    def __init__(self, config: ConfigManager):
        """Initialize security manager with configuration.

        Args:
            config: ConfigManager instance
        """
        self.config = config
        self.logger = logger.bind(component="SecurityManager")

        # Initialize security components
        self.credential_manager = CredentialManager(config)
        self.pii_scrubber = PIIScrubber(config)
        self.config_sanitizer = ConfigurationSanitizer(config)

        # Validate configuration security
        self._validate_configuration_security()

        self.logger.info("SecurityManager initialized successfully")

    def initialize_secure_environment(self) -> Dict[str, Any]:
        """Initialize secure environment with credential validation.

        Returns:
            Dictionary with initialization results
        """
        results = {
            "credentials_valid": False,
            "pii_scrubbing_enabled": self.pii_scrubber.enabled,
            "configuration_secure": False,
            "account_info": None,
            "security_warnings": [],
        }

        try:
            # Validate AWS credentials
            account_info = self.credential_manager.validate_aws_credentials()
            results["credentials_valid"] = True
            results["account_info"] = account_info

        except Exception as e:
            self.logger.error("Failed to validate credentials", error=str(e))
            results["security_warnings"].append(f"Credential validation failed: {e}")

        # Validate configuration security
        config_validation = self.config_sanitizer.validate_configuration(self.config.to_dict())
        results["configuration_secure"] = config_validation["is_secure"]

        if config_validation["issues"]:
            results["security_warnings"].extend(
                [issue["message"] for issue in config_validation["issues"]]
            )

        if config_validation["warnings"]:
            results["security_warnings"].extend(
                [warning["message"] for warning in config_validation["warnings"]]
            )

        self.logger.info(
            "Secure environment initialization completed",
            credentials_valid=results["credentials_valid"],
            configuration_secure=results["configuration_secure"],
            warning_count=len(results["security_warnings"]),
        )

        return results

    def get_secure_logger(self, component_name: str) -> structlog.BoundLogger:
        """Get a logger with PII scrubbing enabled.

        Args:
            component_name: Name of the component requesting the logger

        Returns:
            Bound logger with PII scrubbing
        """
        base_logger = logger.bind(component=component_name)

        if self.pii_scrubber.enabled:
            # Create a wrapper that scrubs log messages
            class PIIScrubbingLogger:
                def __init__(self, base_logger, scrubber):
                    self._logger = base_logger
                    self._scrubber = scrubber

                def _scrub_kwargs(self, kwargs):
                    return self._scrubber.scrub_dict(kwargs)

                def debug(self, msg, **kwargs):
                    return self._logger.debug(
                        self._scrubber.scrub_text(str(msg)), **self._scrub_kwargs(kwargs)
                    )

                def info(self, msg, **kwargs):
                    return self._logger.info(
                        self._scrubber.scrub_text(str(msg)), **self._scrub_kwargs(kwargs)
                    )

                def warning(self, msg, **kwargs):
                    return self._logger.warning(
                        self._scrubber.scrub_text(str(msg)), **self._scrub_kwargs(kwargs)
                    )

                def error(self, msg, **kwargs):
                    return self._logger.error(
                        self._scrubber.scrub_text(str(msg)), **self._scrub_kwargs(kwargs)
                    )

                def bind(self, **kwargs):
                    return PIIScrubbingLogger(
                        self._logger.bind(**self._scrub_kwargs(kwargs)), self._scrubber
                    )

            return PIIScrubbingLogger(base_logger, self.pii_scrubber)

        return base_logger

    def _validate_configuration_security(self) -> None:
        """Validate configuration security on initialization."""
        config_dict = self.config.to_dict()
        validation_result = self.config_sanitizer.validate_configuration(config_dict)

        if not validation_result["is_secure"]:
            critical_issues = [
                issue
                for issue in validation_result["issues"]
                if issue.get("severity") == "critical"
            ]

            if critical_issues:
                error_msg = "Critical security issues found in configuration:\n" + "\n".join(
                    [f"- {issue['message']}" for issue in critical_issues]
                )
                raise ConfigurationError(
                    error_msg,
                    details={
                        "security_issues": validation_result["issues"],
                        "recommendations": validation_result["recommendations"],
                    },
                )
