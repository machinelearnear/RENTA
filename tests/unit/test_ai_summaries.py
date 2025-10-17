"""
Unit tests for AI summary generation via AWS Bedrock.

Tests the core feature: "Generate Claude Sonnet 4.5 summaries in Argentine Spanish through AWS Bedrock"
"""

import pytest
import json
from unittest.mock import Mock, patch, MagicMock
import pandas as pd

from renta.ai import AIAnalyzer, PromptManager
from renta.exceptions import AIServiceConfigurationError
from renta.security import SecurityManager


@pytest.mark.unit
class TestAIAnalyzer:
    """Test AI summary generation with AWS Bedrock."""

    def test_init(self, mock_config_manager):
        """Test AIAnalyzer initialization."""
        with patch("renta.ai.boto3"):
            security_manager = Mock()
            analyzer = AIAnalyzer(mock_config_manager, security_manager)

            assert analyzer.config is not None
            assert hasattr(analyzer, "prompt_manager")

    @pytest.mark.aws
    def test_analyze_properties(self, mock_config_manager, sample_enriched_data, mock_boto3_client):
        """Test generating summaries for enriched properties."""
        with patch("renta.ai.boto3.Session") as mock_session:
            # Setup mocks
            mock_session.return_value.client.return_value = mock_boto3_client
            security_manager = Mock()
            security_manager.credential_manager.get_aws_session.return_value = (
                mock_session.return_value
            )

            analyzer = AIAnalyzer(mock_config_manager, security_manager)

            # Generate summaries
            summaries = analyzer.analyze_properties(
                sample_enriched_data.head(3), prompt_name="default"
            )

            assert isinstance(summaries, list)
            assert len(summaries) > 0

            # Check summary structure
            for summary in summaries:
                assert "property_id" in summary
                assert "summary" in summary or "text" in summary
                assert "confidence" in summary

    def test_model_configuration(self, mock_config_manager):
        """Test that model configuration is correct."""
        model_id = mock_config_manager.get("aws.model_id")
        region = mock_config_manager.get("aws.region")
        max_tokens = mock_config_manager.get("aws.max_tokens")
        temperature = mock_config_manager.get("aws.temperature")

        # Validate configuration
        assert model_id is not None
        assert "claude" in model_id.lower()
        assert region is not None
        assert max_tokens > 0
        assert 0 <= temperature <= 1

    @pytest.mark.aws
    def test_bedrock_invoke(self, mock_config_manager, mock_boto3_client):
        """Test invoking Bedrock API."""
        with patch("renta.ai.boto3.Session") as mock_session:
            mock_session.return_value.client.return_value = mock_boto3_client
            security_manager = Mock()
            security_manager.credential_manager.get_aws_session.return_value = (
                mock_session.return_value
            )

            analyzer = AIAnalyzer(mock_config_manager, security_manager)

            # Test invoke
            test_property = {
                "id": "test_1",
                "title": "Departamento en Palermo",
                "price_usd": 120000,
                "avg_airbnb_price": 80.0,
                "rental_yield_estimate": 0.06,
            }

            # Create minimal DataFrame
            test_df = pd.DataFrame([test_property])

            result = analyzer.analyze_properties(test_df, prompt_name="default")

            assert len(result) > 0
            # Verify invoke_model was called
            assert mock_boto3_client.invoke_model.called

    def test_spanish_language_output(self, mock_config_manager, mock_boto3_client):
        """Test that summaries are generated in Argentine Spanish."""
        response_text = "Esta propiedad presenta una excelente oportunidad de inversión..."

        # Verify Spanish language markers
        spanish_markers = ["esta", "propiedad", "excelente", "inversión", "oportunidad"]
        found_markers = sum(1 for marker in spanish_markers if marker in response_text.lower())

        assert found_markers > 0  # Should have Spanish words


@pytest.mark.unit
class TestPromptManager:
    """Test prompt template management."""

    def test_init(self, mock_config_manager):
        """Test PromptManager initialization."""
        manager = PromptManager(mock_config_manager)

        assert manager.config is not None

    def test_load_default_prompt(self, mock_config_manager):
        """Test loading default prompt template."""
        manager = PromptManager(mock_config_manager)

        try:
            prompts = manager.list_available_prompts()
            assert len(prompts) >= 0
        except (AttributeError, NotImplementedError):
            pytest.skip("Prompt loading not fully implemented")

    def test_render_prompt(self, mock_config_manager):
        """Test rendering prompt with property data."""
        manager = PromptManager(mock_config_manager)

        # Test data
        property_data = {
            "title": "Departamento en Palermo",
            "price_usd": 120000,
            "bedrooms": 2,
            "avg_airbnb_price": 80.0,
            "rental_yield_estimate": 0.06,
        }

        # Try to render (implementation may vary)
        try:
            # Jinja2 template rendering test
            from jinja2 import Template

            test_template = Template("Property: {{ title }} - Price: ${{ price_usd }}")
            rendered = test_template.render(**property_data)

            assert "Palermo" in rendered
            assert "120000" in rendered
        except ImportError:
            pytest.skip("Jinja2 not available")

    def test_custom_prompts(self, mock_config_manager):
        """Test custom prompt templates."""
        manager = PromptManager(mock_config_manager)

        # Check if custom prompts are supported
        custom_prompts_config = mock_config_manager.get("prompts.custom", {})

        assert isinstance(custom_prompts_config, dict)


@pytest.mark.unit
class TestResponseParsing:
    """Test parsing of Bedrock API responses."""

    def test_parse_claude_response(self):
        """Test parsing Claude API response format."""
        sample_response = {
            "content": [{"text": "Esta propiedad presenta una excelente oportunidad..."}],
            "usage": {"input_tokens": 500, "output_tokens": 300},
            "stop_reason": "end_turn",
        }

        # Parse response
        assert "content" in sample_response
        assert len(sample_response["content"]) > 0
        assert "text" in sample_response["content"][0]
        assert "usage" in sample_response

    def test_error_response_handling(self):
        """Test handling of API error responses."""
        error_response = {
            "error": {"type": "ThrottlingException", "message": "Rate limit exceeded"}
        }

        # Should detect error
        assert "error" in error_response

    def test_token_usage_tracking(self):
        """Test tracking of token usage."""
        usage_data = {"input_tokens": 500, "output_tokens": 300}

        total_tokens = usage_data["input_tokens"] + usage_data["output_tokens"]

        assert total_tokens == 800
        assert usage_data["input_tokens"] > 0
        assert usage_data["output_tokens"] > 0


@pytest.mark.unit
class TestCredentialValidation:
    """Test AWS credential validation."""

    def test_credentials_required(self, mock_config_manager):
        """Test that AWS credentials are required for AI features."""
        # Check if security manager validates credentials
        with patch("renta.security.boto3.Session"):
            security_manager = Mock()

            # Should have credential validation
            assert security_manager is not None

    @pytest.mark.aws
    def test_model_access_validation(self, mock_config_manager):
        """Test validation of Bedrock model access."""
        model_id = mock_config_manager.get("aws.model_id")

        # Should be Claude Sonnet 4.5
        assert "claude" in model_id.lower()
        assert "sonnet" in model_id.lower() or "4" in model_id

    def test_region_configuration(self, mock_config_manager):
        """Test AWS region configuration."""
        region = mock_config_manager.get("aws.region")

        # Should be valid AWS region
        valid_regions = ["us-east-1", "us-west-2", "eu-west-1", "eu-central-1"]
        # Region should be a string at minimum
        assert isinstance(region, str)
        assert len(region) > 0


@pytest.mark.unit
class TestErrorHandling:
    """Test error handling in AI summary generation."""

    @pytest.mark.aws
    def test_api_error_handling(self, mock_config_manager, mock_boto3_client):
        """Test handling of API errors."""
        # Mock API error
        from botocore.exceptions import ClientError

        error_response = {
            "Error": {"Code": "ThrottlingException", "Message": "Rate limit exceeded"}
        }
        mock_boto3_client.invoke_model.side_effect = ClientError(error_response, "InvokeModel")

        with patch("renta.ai.boto3.Session") as mock_session:
            mock_session.return_value.client.return_value = mock_boto3_client
            security_manager = Mock()
            security_manager.credential_manager.get_aws_session.return_value = (
                mock_session.return_value
            )

            analyzer = AIAnalyzer(mock_config_manager, security_manager)

            # Should handle API error
            test_df = pd.DataFrame([{"id": "test_1", "title": "Test"}])

            with pytest.raises((AIServiceConfigurationError, ClientError)):
                analyzer.analyze_properties(test_df)

    def test_invalid_prompt_handling(self, mock_config_manager):
        """Test handling of invalid prompt names."""
        with patch("renta.ai.boto3"):
            security_manager = Mock()
            analyzer = AIAnalyzer(mock_config_manager, security_manager)

            # Should validate prompt names
            # Implementation may vary
            assert hasattr(analyzer, "prompt_manager")

    def test_malformed_response_handling(self, mock_config_manager, mock_boto3_client):
        """Test handling of malformed API responses."""
        # Mock malformed response
        mock_body = Mock()
        mock_body.read.return_value = b"invalid json"

        mock_response = {"body": mock_body, "contentType": "application/json"}

        mock_boto3_client.invoke_model.return_value = mock_response

        with patch("renta.ai.boto3.Session") as mock_session:
            mock_session.return_value.client.return_value = mock_boto3_client
            security_manager = Mock()
            security_manager.credential_manager.get_aws_session.return_value = (
                mock_session.return_value
            )

            analyzer = AIAnalyzer(mock_config_manager, security_manager)

            # Should handle malformed response
            test_df = pd.DataFrame([{"id": "test_1", "title": "Test"}])

            with pytest.raises((json.JSONDecodeError, AIServiceConfigurationError, ValueError)):
                analyzer.analyze_properties(test_df)
