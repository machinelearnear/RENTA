"""
AI analysis system for RENTA library.

Provides AWS Bedrock integration for generating AI-powered investment summaries
with configurable model parameters, retry logic, and response validation.
Also includes prompt template management with Jinja2 support.
"""

import json
import os
import re
import time
import random
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass
import pandas as pd
import boto3
from botocore.exceptions import ClientError, NoCredentialsError, BotoCoreError
import structlog
import yaml
import jinja2
import importlib.resources

from .exceptions import AIServiceConfigurationError, ConfigurationError
from .config import ConfigManager
from .utils.retry import RetryConfig

logger = structlog.get_logger(__name__)


class PromptManager:
    """Manages AI prompt templates with Jinja2 support.
    
    Provides template loading from files and configuration, prompt registration,
    and context preparation for property data analysis.
    """
    
    def __init__(self, config: ConfigManager):
        """Initialize PromptManager with prompt configuration.
        
        Args:
            config: ConfigManager instance with prompt configuration
        """
        self.config = config
        self._custom_prompts: Dict[str, str] = {}
        self._jinja_env = jinja2.Environment(
            loader=jinja2.BaseLoader(),
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True
        )
        
        # Load custom prompts from configuration
        self._load_custom_prompts_from_config()
        
        logger.info(
            "PromptManager initialized",
            custom_prompts=list(self._custom_prompts.keys())
        )
    
    def load_prompt(self, prompt_name: str) -> Dict[str, str]:
        """Load prompt template by name.
        
        Args:
            prompt_name: Name/identifier of the prompt template
            
        Returns:
            Dictionary with 'user_prompt' and 'system_prompt' keys
            
        Raises:
            ConfigurationError: If prompt cannot be loaded
        """
        logger.debug("Loading prompt", prompt_name=prompt_name)
        
        # Check custom prompts first
        if prompt_name in self._custom_prompts:
            return self._parse_prompt_content(self._custom_prompts[prompt_name])
        
        # Try to load from package resources
        try:
            prompt_path = self.config.get('prompts.default', 'prompts/investment_summary.yaml')
            if prompt_name == 'default':
                return self._load_prompt_from_package(prompt_path)
            else:
                # Try to load specific prompt file
                prompt_file = f"prompts/{prompt_name}.yaml"
                return self._load_prompt_from_package(prompt_file)
                
        except Exception as e:
            logger.warning(
                "Failed to load prompt from package, using fallback",
                prompt_name=prompt_name,
                error=str(e)
            )
            return self._get_fallback_prompt()
    
    def render_prompt(self, template: str, context: Dict[str, Any]) -> str:
        """Render Jinja2 template with property context.
        
        Args:
            template: Jinja2 template string
            context: Property context dictionary
            
        Returns:
            Rendered prompt string
            
        Raises:
            ConfigurationError: If template rendering fails
        """
        try:
            jinja_template = self._jinja_env.from_string(template)
            return jinja_template.render(**context)
        except jinja2.TemplateError as e:
            raise ConfigurationError(
                f"Failed to render prompt template: {e}",
                details={"template_error": str(e), "context_keys": list(context.keys())}
            )
    
    def register_custom_prompt(self, name: str, template: str) -> None:
        """Register custom prompt template.
        
        Args:
            name: Prompt name/identifier
            template: Prompt template content (YAML string or template string)
        """
        self._custom_prompts[name] = template
        logger.info("Registered custom prompt", name=name)
    
    def list_available_prompts(self) -> List[str]:
        """List all available prompt names.
        
        Returns:
            List of available prompt identifiers
        """
        prompts = ['default']  # Always available
        prompts.extend(self._custom_prompts.keys())
        
        # Try to discover prompts from package
        try:
            # This would list prompts from the package in a real implementation
            # For now, we'll just return what we have
            pass
        except Exception:
            pass
        
        return list(set(prompts))
    
    def _load_custom_prompts_from_config(self) -> None:
        """Load custom prompts from configuration."""
        custom_prompts = self.config.get('prompts.custom', {})
        
        for name, path_or_content in custom_prompts.items():
            try:
                if isinstance(path_or_content, str) and os.path.exists(path_or_content):
                    # Load from file
                    with open(path_or_content, 'r', encoding='utf-8') as f:
                        content = f.read()
                    self._custom_prompts[name] = content
                else:
                    # Treat as inline content
                    self._custom_prompts[name] = str(path_or_content)
                    
                logger.debug("Loaded custom prompt from config", name=name)
                
            except Exception as e:
                logger.warning(
                    "Failed to load custom prompt from config",
                    name=name,
                    error=str(e)
                )
    
    def _load_prompt_from_package(self, prompt_path: str) -> Dict[str, str]:
        """Load prompt from package resources.
        
        Args:
            prompt_path: Path to prompt file within package
            
        Returns:
            Dictionary with user_prompt and system_prompt
        """
        try:
            # Extract filename from path for importlib.resources
            if '/' in prompt_path:
                package_path, filename = prompt_path.rsplit('/', 1)
                package_name = f'renta.{package_path.replace("/", ".")}'
            else:
                package_name = 'renta'
                filename = prompt_path
            
            with importlib.resources.open_text(package_name, filename) as f:
                content = f.read()
            return self._parse_prompt_content(content)
        except Exception as e:
            raise ConfigurationError(
                f"Failed to load prompt from package: {prompt_path}",
                details={"path": prompt_path, "error": str(e)}
            )
    
    def _parse_prompt_content(self, content: str) -> Dict[str, str]:
        """Parse prompt content from YAML or plain text.
        
        Args:
            content: Prompt content as string
            
        Returns:
            Dictionary with user_prompt and system_prompt keys
        """
        try:
            # Try to parse as YAML first
            parsed = yaml.safe_load(content)
            
            if isinstance(parsed, dict):
                return {
                    'user_prompt': parsed.get('user_prompt', ''),
                    'system_prompt': parsed.get('system_prompt', '')
                }
            else:
                # Treat as plain text user prompt
                return {
                    'user_prompt': content,
                    'system_prompt': ''
                }
                
        except yaml.YAMLError:
            # Not valid YAML, treat as plain text
            return {
                'user_prompt': content,
                'system_prompt': ''
            }
    
    def _get_fallback_prompt(self) -> Dict[str, str]:
        """Get fallback prompt when loading fails.
        
        Returns:
            Dictionary with basic fallback prompts
        """
        return {
            'user_prompt': """
Analiza esta propiedad para inversión inmobiliaria en Buenos Aires:

**Datos de la Propiedad:**
- ID: {{ property_id }}
- Título: {{ title }}
- Precio: USD {{ "{:,.0f}".format(price_usd) }} (ARS {{ "{:,.0f}".format(price_ars) }})
- Dirección: {{ address }}
- Superficie: {{ surface_m2 }} m²
- Ambientes: {{ rooms }} habitaciones, {{ bathrooms }} baños
- Precio por m²: USD {{ "{:.0f}".format(price_per_m2_usd) }}

{% if has_airbnb_data %}
**Datos de Airbnb (Potencial de Alquiler):**
- Precio promedio depto completo: USD {{ "{:.0f}".format(airbnb_avg_price_entire_home) }}/noche
- Probabilidad de ocupación: {{ airbnb_occupancy_probability }}
{% if estimated_rental_yield %}
- Rendimiento estimado anual: {{ "{:.1f}".format(estimated_rental_yield) }}%
{% endif %}
{% else %}
**Datos de Airbnb:** No se encontraron datos cercanos
{% endif %}

Proporciona un análisis conciso (máximo 200 palabras) que incluya:
1. Evaluación del precio y ubicación
2. Potencial de inversión y alquiler
3. Recomendación (comprar/no comprar/investigar más)
4. Factores de riesgo principales

Responde en español argentino con tono profesional pero accesible.
""",
            'system_prompt': (
                "Eres un analista inmobiliario experto en Buenos Aires. "
                "Proporciona análisis de inversión concisos y profesionales en español rioplatense. "
                "Enfócate en aspectos financieros, ubicación y potencial de alquiler."
            )
        }


class AIAnalyzer:
    """Generates AI-powered investment summaries using AWS Bedrock.
    
    Provides integration with AWS Bedrock Claude models for analyzing property
    investment opportunities with configurable parameters and robust error handling.
    """
    
    def __init__(self, config: ConfigManager, security_manager=None):
        """Initialize AIAnalyzer with AWS configuration.
        
        Args:
            config: ConfigManager instance with AWS and AI configuration
            security_manager: Optional SecurityManager for credential handling
            
        Raises:
            AIServiceConfigurationError: If AWS configuration is invalid
        """
        self.config = config
        self.security_manager = security_manager
        self.retry_config = RetryConfig(
            max_attempts=config.get('aws.bedrock.max_retries', 3)
        )
        
        # Initialize prompt manager
        self.prompt_manager = PromptManager(config)
        
        # Initialize AWS Bedrock client with security manager if available
        self._bedrock_client = None
        self._initialize_bedrock_client()
        
        # Cache model configuration
        self.model_id = config.get('aws.bedrock.model_id', 'us.anthropic.claude-sonnet-4-5-20250929-v1:0')
        self.max_tokens = config.get('aws.bedrock.max_tokens', 1024)
        self.temperature = config.get('aws.bedrock.temperature', 0.7)
        
        # Dry run mode for testing
        self.dry_run = config.get('debug.dry_run', False)
        
        logger.info(
            "AIAnalyzer initialized",
            model_id=self.model_id,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            dry_run=self.dry_run
        )
    
    def analyze_properties(
        self, 
        enriched_properties: pd.DataFrame, 
        prompt_name: str = "default"
    ) -> List[Dict[str, Any]]:
        """Generate summaries for properties.
        
        Args:
            enriched_properties: DataFrame with properties enriched with Airbnb data
            prompt_name: Name of prompt template to use
            
        Returns:
            List of dictionaries with property_id, summary, and confidence
            
        Raises:
            AIServiceConfigurationError: If Bedrock service fails
            ConfigurationError: If prompt template is invalid
        """
        logger.info(
            "Starting AI analysis",
            property_count=len(enriched_properties),
            prompt_name=prompt_name
        )
        
        results = []
        
        for idx, property_row in enriched_properties.iterrows():
            try:
                # Prepare context for this property
                context = self._prepare_property_context(property_row)
                
                # Generate summary
                summary_result = self._generate_property_summary(context, prompt_name)
                
                results.append({
                    'property_id': property_row.get('id', f'property_{idx}'),
                    'summary': summary_result['summary'],
                    'confidence': summary_result['confidence']
                })
                
                logger.debug(
                    "Generated summary for property",
                    property_id=property_row.get('id', f'property_{idx}'),
                    summary_length=len(summary_result['summary'])
                )
                
            except Exception as e:
                logger.error(
                    "Failed to generate summary for property",
                    property_id=property_row.get('id', f'property_{idx}'),
                    error=str(e)
                )
                
                # Add error result
                results.append({
                    'property_id': property_row.get('id', f'property_{idx}'),
                    'summary': f"Error generating summary: {str(e)}",
                    'confidence': 0.0
                })
        
        logger.info(
            "AI analysis completed",
            total_properties=len(enriched_properties),
            successful_summaries=len([r for r in results if r['confidence'] > 0])
        )
        
        return results
    
    def invoke_bedrock(self, prompt: str, system_prompt: str = "") -> str:
        """Call AWS Bedrock API with retry logic.
        
        Args:
            prompt: User prompt for the model
            system_prompt: Optional system prompt
            
        Returns:
            Model response as string
            
        Raises:
            AIServiceConfigurationError: If Bedrock service fails after retries
        """
        if self.dry_run:
            return self._handle_dry_run(prompt, system_prompt)
        
        # Prepare request body
        request_body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        }
        
        if system_prompt:
            request_body["system"] = system_prompt
        
        # Retry logic with exponential backoff
        last_exception = None
        
        for attempt in range(self.retry_config.max_attempts):
            try:
                logger.debug(
                    "Invoking Bedrock",
                    attempt=attempt + 1,
                    model_id=self.model_id
                )
                
                response = self._bedrock_client.invoke_model(
                    modelId=self.model_id,
                    body=json.dumps(request_body),
                    contentType="application/json",
                    accept="application/json"
                )
                
                # Parse response
                response_body = json.loads(response['body'].read())
                
                if 'content' in response_body and response_body['content']:
                    content = response_body['content'][0]['text']
                    
                    # Validate response language
                    if not self.validate_response_language(content):
                        logger.warning(
                            "Response language validation failed",
                            response_preview=content[:100]
                        )
                    
                    logger.debug(
                        "Bedrock response received",
                        response_length=len(content)
                    )
                    
                    return content
                else:
                    raise AIServiceConfigurationError(
                        "Invalid response format from Bedrock",
                        details={"response_body": response_body}
                    )
                    
            except ClientError as e:
                error_code = e.response.get('Error', {}).get('Code', 'Unknown')
                
                if error_code in ['ThrottlingException', 'ServiceUnavailableException']:
                    # Retryable errors
                    last_exception = e
                    if attempt < self.retry_config.max_attempts - 1:
                        delay = self.retry_config.calculate_delay(attempt)
                        logger.warning(
                            "Bedrock API throttled, retrying",
                            attempt=attempt + 1,
                            delay=delay,
                            error_code=error_code
                        )
                        time.sleep(delay)
                        continue
                elif error_code in ['AccessDeniedException', 'UnauthorizedOperation']:
                    # Authentication errors - don't retry
                    raise AIServiceConfigurationError(
                        f"AWS authentication error: {e}",
                        details={"error_code": error_code, "aws_error": str(e)}
                    )
                else:
                    # Other client errors - don't retry
                    raise AIServiceConfigurationError(
                        f"AWS Bedrock client error: {e}",
                        details={"error_code": error_code, "aws_error": str(e)}
                    )
                    
            except (BotoCoreError, NoCredentialsError) as e:
                # Configuration errors - don't retry
                raise AIServiceConfigurationError(
                    f"AWS configuration error: {e}",
                    details={"error_type": type(e).__name__, "aws_error": str(e)}
                )
                
            except Exception as e:
                # Unexpected errors
                last_exception = e
                if attempt < self.retry_config.max_attempts - 1:
                    delay = self.retry_config.calculate_delay(attempt)
                    logger.warning(
                        "Unexpected error invoking Bedrock, retrying",
                        attempt=attempt + 1,
                        delay=delay,
                        error=str(e)
                    )
                    time.sleep(delay)
                    continue
        
        # All retries exhausted
        raise AIServiceConfigurationError(
            f"Bedrock API failed after {self.retry_config.max_attempts} attempts: {last_exception}",
            details={"last_error": str(last_exception), "max_attempts": self.retry_config.max_attempts}
        )
    
    def validate_response_language(self, response: str) -> bool:
        """Validate response is in Spanish.
        
        Args:
            response: Model response text
            
        Returns:
            True if response appears to be in Spanish
        """
        # Simple heuristic: check for common Spanish words and patterns
        spanish_indicators = [
            r'\b(el|la|los|las|un|una|de|del|en|con|por|para|que|es|son|está|están)\b',
            r'\b(propiedad|inversión|alquiler|ubicación|precio|metros|habitaciones|baños)\b',
            r'\b(muy|más|menos|mejor|peor|bueno|malo|excelente|recomendable)\b',
            r'ción\b',  # Common Spanish suffix
            r'ñ',       # Spanish character
        ]
        
        # Count matches
        matches = 0
        total_words = len(response.split())
        
        for pattern in spanish_indicators:
            matches += len(re.findall(pattern, response, re.IGNORECASE))
        
        # Consider valid if at least 10% of words are Spanish indicators
        # or if response is very short (< 20 words) and has any Spanish indicators
        if total_words < 20:
            return matches > 0
        else:
            return matches / total_words >= 0.1
    
    def _initialize_bedrock_client(self) -> None:
        """Initialize AWS Bedrock client with configuration.
        
        Raises:
            AIServiceConfigurationError: If client initialization fails
        """
        try:
            region = self.config.get('aws.region', 'us-east-1')
            
            # Use security manager for credential handling if available
            if self.security_manager:
                aws_session = self.security_manager.credential_manager.get_aws_session()
                self._bedrock_client = aws_session.client('bedrock-runtime')
                logger.info(
                    "Bedrock client initialized with security manager",
                    region=region
                )
            else:
                # Fallback to direct boto3 client creation
                self._bedrock_client = boto3.client(
                    'bedrock-runtime',
                    region_name=region
                )
                logger.info(
                    "Bedrock client initialized directly",
                    region=region
                )
            
        except NoCredentialsError:
            raise AIServiceConfigurationError(
                "AWS credentials not found. Please configure AWS credentials via "
                "environment variables, shared credentials file, or IAM role.",
                details={"region": self.config.get('aws.region', 'us-east-1')}
            )
        except Exception as e:
            raise AIServiceConfigurationError(
                f"Failed to initialize Bedrock client: {e}",
                details={"error_type": type(e).__name__}
            )
    
    def _prepare_property_context(self, property_row: pd.Series) -> Dict[str, Any]:
        """Prepare context dictionary for property analysis.
        
        Args:
            property_row: Single property record from DataFrame
            
        Returns:
            Dictionary with property context for prompt rendering
        """
        context = {
            'property_id': property_row.get('id', 'N/A'),
            'title': property_row.get('title', 'N/A'),
            'price_usd': property_row.get('price_usd', 0),
            'price_ars': property_row.get('price_ars', 0),
            'address': property_row.get('address', 'N/A'),
            'rooms': property_row.get('rooms', 0),
            'bathrooms': property_row.get('bathrooms', 0),
            'surface_m2': property_row.get('surface_m2', 0),
            'views_per_day': property_row.get('views_per_day', 0),
            
            # Airbnb enrichment data
            'airbnb_avg_price_entire_home': property_row.get('airbnb_avg_price_entire_home'),
            'airbnb_avg_price_private_room': property_row.get('airbnb_avg_price_private_room'),
            'airbnb_occupancy_probability': property_row.get('airbnb_occupancy_probability', 'unknown'),
            'airbnb_avg_review_score': property_row.get('airbnb_avg_review_score'),
            'match_status': property_row.get('match_status', 'unknown'),
            
            # Calculated metrics
            'has_airbnb_data': property_row.get('match_status') == 'matched',
            'price_per_m2_usd': (
                property_row.get('price_usd', 0) / property_row.get('surface_m2', 1)
                if property_row.get('surface_m2', 0) > 0 else 0
            ),
        }
        
        # Add rental yield estimation if we have Airbnb data
        if context['has_airbnb_data'] and context['airbnb_avg_price_entire_home']:
            monthly_rental = context['airbnb_avg_price_entire_home'] * 30
            annual_rental = monthly_rental * 12
            if context['price_usd'] > 0:
                context['estimated_rental_yield'] = (annual_rental / context['price_usd']) * 100
            else:
                context['estimated_rental_yield'] = 0
        else:
            context['estimated_rental_yield'] = None
        
        return context
    
    def _generate_property_summary(
        self, 
        context: Dict[str, Any], 
        prompt_name: str
    ) -> Dict[str, Any]:
        """Generate AI summary for a single property.
        
        Args:
            context: Property context dictionary
            prompt_name: Name of prompt template to use
            
        Returns:
            Dictionary with summary and confidence score
        """
        try:
            # Load and render prompt template
            prompt_templates = self.prompt_manager.load_prompt(prompt_name)
            
            user_prompt = self.prompt_manager.render_prompt(
                prompt_templates['user_prompt'], 
                context
            )
            system_prompt = prompt_templates['system_prompt']
            
            # Generate response
            response = self.invoke_bedrock(user_prompt, system_prompt)
            
            # Validate response format
            validation_result = self.validate_response_format(response)
            
            # Calculate confidence score (adjusted by validation)
            base_confidence = self._calculate_confidence(response, context)
            
            # Adjust confidence based on validation
            if not validation_result['is_valid']:
                base_confidence *= 0.7  # Reduce confidence for invalid responses
            
            if len(validation_result['issues']) > 0:
                base_confidence *= max(0.5, 1.0 - (len(validation_result['issues']) * 0.1))
            
            result = {
                'summary': response.strip(),
                'confidence': max(0.0, min(1.0, base_confidence))
            }
            
            # Add validation info in debug mode
            if self.config.get('debug.enable_request_logging', False):
                result['validation'] = validation_result
            
            return result
            
        except Exception as e:
            logger.error(
                "Failed to generate summary",
                property_id=context.get('property_id'),
                error=str(e)
            )
            raise
    

    
    def _calculate_confidence(self, response: str, context: Dict[str, Any]) -> float:
        """Calculate confidence score for the generated summary.
        
        Args:
            response: Generated summary text
            context: Property context used for generation
            
        Returns:
            Confidence score between 0.0 and 1.0
        """
        confidence = 0.5  # Base confidence
        
        # Increase confidence based on response quality indicators
        if len(response) > 50:  # Reasonable length
            confidence += 0.1
        
        if len(response) > 100:  # Good length
            confidence += 0.1
        
        # Check for key analysis elements
        analysis_keywords = [
            'precio', 'ubicación', 'inversión', 'alquiler', 'recomend',
            'riesgo', 'potencial', 'rendimiento'
        ]
        
        keyword_matches = sum(1 for keyword in analysis_keywords 
                            if keyword.lower() in response.lower())
        confidence += min(keyword_matches * 0.05, 0.2)
        
        # Increase confidence if we have Airbnb data
        if context['has_airbnb_data']:
            confidence += 0.1
        
        # Decrease confidence if response seems generic or has errors
        if 'error' in response.lower() or 'no disponible' in response.lower():
            confidence -= 0.3
        
        # Ensure confidence is within bounds
        return max(0.0, min(1.0, confidence))
    
    def _handle_dry_run(self, prompt: str, system_prompt: str = "") -> str:
        """Handle dry-run mode with detailed logging.
        
        Args:
            prompt: User prompt that would be sent
            system_prompt: System prompt that would be sent
            
        Returns:
            Mock response for dry-run mode
        """
        # Log prompt details for testing
        logger.info(
            "DRY RUN: Bedrock API call",
            prompt_length=len(prompt),
            system_prompt_length=len(system_prompt),
            model_id=self.model_id,
            max_tokens=self.max_tokens,
            temperature=self.temperature
        )
        
        # Log prompt content if debug logging is enabled
        if self.config.get('debug.enable_request_logging', False):
            logger.debug(
                "DRY RUN: Prompt content",
                user_prompt=prompt[:500] + "..." if len(prompt) > 500 else prompt,
                system_prompt=system_prompt[:200] + "..." if len(system_prompt) > 200 else system_prompt
            )
        
        # Return a realistic mock response in Spanish
        return (
            "Esta propiedad presenta una oportunidad de inversión interesante en el mercado porteño. "
            "El precio por metro cuadrado está dentro del rango esperado para la zona. "
            "El potencial de alquiler temporal es moderado según los datos de Airbnb cercanos. "
            "Recomendación: Investigar más sobre la ubicación específica y tendencias del barrio. "
            "Factores de riesgo: Fluctuaciones del mercado inmobiliario y regulaciones de alquileres temporales."
        )
    
    def validate_response_format(self, response: str) -> Dict[str, Any]:
        """Validate and analyze response format and content.
        
        Args:
            response: Model response to validate
            
        Returns:
            Dictionary with validation results
        """
        validation_result = {
            'is_valid': True,
            'issues': [],
            'metrics': {},
            'language_detected': 'unknown'
        }
        
        # Basic format checks
        if not response or not response.strip():
            validation_result['is_valid'] = False
            validation_result['issues'].append('Empty response')
            return validation_result
        
        # Length validation
        response_length = len(response.strip())
        validation_result['metrics']['length'] = response_length
        
        if response_length < 50:
            validation_result['issues'].append('Response too short (< 50 characters)')
        elif response_length > 1000:
            validation_result['issues'].append('Response too long (> 1000 characters)')
        
        # Language validation
        if self.validate_response_language(response):
            validation_result['language_detected'] = 'spanish'
        else:
            validation_result['issues'].append('Response does not appear to be in Spanish')
            validation_result['language_detected'] = 'other'
        
        # Content structure validation
        required_elements = [
            ('price_analysis', ['precio', 'costo', 'valor']),
            ('location_analysis', ['ubicación', 'zona', 'barrio']),
            ('recommendation', ['recomend', 'suger', 'aconsej']),
            ('risk_factors', ['riesgo', 'factor', 'consider'])
        ]
        
        content_lower = response.lower()
        for element_name, keywords in required_elements:
            found = any(keyword in content_lower for keyword in keywords)
            validation_result['metrics'][f'has_{element_name}'] = found
            if not found:
                validation_result['issues'].append(f'Missing {element_name.replace("_", " ")}')
        
        # Investment terminology check
        investment_terms = [
            'inversión', 'rentabilidad', 'rendimiento', 'alquiler', 
            'mercado', 'revalorización', 'oportunidad'
        ]
        
        term_count = sum(1 for term in investment_terms if term in content_lower)
        validation_result['metrics']['investment_terms_count'] = term_count
        
        if term_count < 2:
            validation_result['issues'].append('Insufficient investment terminology')
        
        # Overall validation
        if len(validation_result['issues']) > 2:
            validation_result['is_valid'] = False
        
        return validation_result
    
    def get_api_call_parameters(self) -> Dict[str, Any]:
        """Get current API call parameters for testing and debugging.
        
        Returns:
            Dictionary with current Bedrock API parameters
        """
        return {
            'model_id': self.model_id,
            'max_tokens': self.max_tokens,
            'temperature': self.temperature,
            'region': self.config.get('aws.region', 'us-east-1'),
            'max_retries': self.retry_config.max_attempts,
            'dry_run': self.dry_run,
            'anthropic_version': 'bedrock-2023-05-31'
        }
    
    def test_prompt_rendering(self, prompt_name: str, sample_context: Dict[str, Any]) -> Dict[str, Any]:
        """Test prompt rendering without making API calls.
        
        Args:
            prompt_name: Name of prompt template to test
            sample_context: Sample property context for testing
            
        Returns:
            Dictionary with rendered prompts and validation results
        """
        try:
            # Load and render prompt
            prompt_templates = self.prompt_manager.load_prompt(prompt_name)
            
            rendered_user_prompt = self.prompt_manager.render_prompt(
                prompt_templates['user_prompt'], 
                sample_context
            )
            
            rendered_system_prompt = prompt_templates['system_prompt']
            
            # Validate rendered prompts
            validation_results = {
                'user_prompt_length': len(rendered_user_prompt),
                'system_prompt_length': len(rendered_system_prompt),
                'has_template_variables': '{{' in prompt_templates['user_prompt'],
                'rendering_successful': True,
                'context_keys_used': []
            }
            
            # Check which context keys were actually used
            for key in sample_context.keys():
                if f'{{{{{key}}}}}' in prompt_templates['user_prompt']:
                    validation_results['context_keys_used'].append(key)
            
            return {
                'prompt_name': prompt_name,
                'rendered_user_prompt': rendered_user_prompt,
                'rendered_system_prompt': rendered_system_prompt,
                'validation': validation_results,
                'api_parameters': self.get_api_call_parameters()
            }
            
        except Exception as e:
            return {
                'prompt_name': prompt_name,
                'error': str(e),
                'validation': {
                    'rendering_successful': False,
                    'error_type': type(e).__name__
                }
            }