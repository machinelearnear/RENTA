# AI Analysis

The AI analysis module integrates with AWS Bedrock to generate intelligent investment summaries.

## AIAnalyzer

::: renta.ai.AIAnalyzer
    options:
      show_root_heading: true
      show_source: true
      heading_level: 3

### Usage Examples

```python
from renta.ai import AIAnalyzer
from renta.config import ConfigManager
from renta.security import SecurityManager

config = ConfigManager()
security_manager = SecurityManager(config)
analyzer = AIAnalyzer(config, security_manager)

# Generate summaries for enriched properties
summaries = analyzer.analyze_properties(enriched_properties)

# Use custom prompt template
summaries = analyzer.analyze_properties(
    enriched_properties, 
    prompt_name="investment_focus"
)

# Dry run mode (no API calls)
config.set('aws.bedrock.dry_run', True)
summaries = analyzer.analyze_properties(enriched_properties)  # Logs prompts only
```

## PromptManager

::: renta.ai.PromptManager
    options:
      show_root_heading: true
      show_source: true
      heading_level: 3

### Usage Examples

```python
from renta.ai import PromptManager
from renta.config import ConfigManager

config = ConfigManager()
prompt_manager = PromptManager(config)

# Load default prompt template
template = prompt_manager.load_prompt("default")

# Render prompt with property context
context = {
    'property': {
        'title': '2 ambientes en Palermo',
        'price_usd': 95000,
        'surface_m2': 45,
        'airbnb_avg_price_entire_home': 85.50
    }
}
rendered_prompt = prompt_manager.render_prompt(template, context)

# Register custom prompt
custom_template = """
Analiza esta propiedad para inversión:
Título: {{ property.title }}
Precio: USD {{ property.price_usd }}
Potencial de alquiler: USD {{ property.airbnb_avg_price_entire_home }}/noche
"""
prompt_manager.register_custom_prompt("custom", custom_template)
```

## AWS Bedrock Integration

### Supported Models

RENTA supports various AWS Bedrock models:

```python
# Inference Profiles (Recommended)
models = {
    "claude_sonnet_4_5": "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
    "claude_3_7_sonnet": "us.anthropic.claude-3-7-sonnet-20250219-v1:0", 
    "claude_sonnet_4": "us.anthropic.claude-sonnet-4-20250514-v1:0",
    "claude_3_5_haiku": "us.anthropic.claude-3-5-haiku-20241022-v1:0"
}

# Direct Model Access
direct_models = {
    "claude_sonnet_4_5": "anthropic.claude-sonnet-4-5-20250929-v1:0",
    "claude_3_7_sonnet": "anthropic.claude-3-7-sonnet-20250219-v1:0",
    "claude_3_haiku": "anthropic.claude-3-haiku-20240307-v1:0"
}
```

### Configuration

```yaml
aws:
  region: "us-east-1"
  bedrock:
    model_id: "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
    max_tokens: 1024
    temperature: 0.7
    max_retries: 3
    timeout_seconds: 30
    dry_run: false  # Set to true for testing without API calls
```

### Authentication

```python
# Method 1: Environment variables
import os
os.environ['AWS_ACCESS_KEY_ID'] = 'your_access_key'
os.environ['AWS_SECRET_ACCESS_KEY'] = 'your_secret_key'
os.environ['AWS_REGION'] = 'us-east-1'

# Method 2: AWS credentials file (~/.aws/credentials)
# [default]
# aws_access_key_id = your_access_key
# aws_secret_access_key = your_secret_key
# region = us-east-1

# Method 3: IAM Role (recommended for production)
# No configuration needed - uses instance role automatically
```

## Prompt Templates

### Default Template Structure

```yaml
# prompts/investment_summary.yaml
system_prompt: |
  Sos un analista inmobiliario experto en Buenos Aires que ayuda a inversores.
  Respondé siempre en español rioplatense con tono profesional pero cercano.
  
user_prompt: |
  Analizá esta propiedad para inversión inmobiliaria:
  
  **Datos de la Propiedad:**
  - Título: {{ property.title }}
  - Precio: USD {{ property.price_usd | default('No especificado') }}
  - Superficie: {{ property.surface_m2 | default('No especificado') }} m²
  - Ubicación: {{ property.address }}
  - Ambientes: {{ property.rooms | default('No especificado') }}
  - Baños: {{ property.bathrooms | default('No especificado') }}
  
  **Datos de Airbnb Cercanos:**
  {% if property.airbnb_avg_price_entire_home %}
  - Precio promedio depto completo: USD {{ property.airbnb_avg_price_entire_home }}/noche
  {% endif %}
  {% if property.airbnb_avg_price_private_room %}
  - Precio promedio habitación privada: USD {{ property.airbnb_avg_price_private_room }}/noche
  {% endif %}
  - Probabilidad de ocupación: {{ property.airbnb_occupancy_probability | default('No disponible') }}
  - Score promedio de reviews: {{ property.airbnb_avg_review_score | default('No disponible') }}
  
  Proporcioná un análisis de inversión conciso (máximo 200 palabras) que incluya:
  1. Evaluación del precio por m²
  2. Potencial de alquiler turístico
  3. Ventajas y desventajas de la ubicación
  4. Recomendación de inversión
```

### Custom Templates

```python
# Register inline template
investment_focus_template = """
Enfocate en el potencial de ROI de esta propiedad:

Precio de compra: USD {{ property.price_usd }}
Ingresos potenciales por Airbnb: USD {{ property.airbnb_avg_price_entire_home * 20 }}/mes
ROI estimado: {{ ((property.airbnb_avg_price_entire_home * 20 * 12) / property.price_usd * 100) | round(1) }}%

¿Es una buena inversión considerando el mercado actual?
"""

prompt_manager.register_custom_prompt("roi_focus", investment_focus_template)

# Use custom template
summaries = analyzer.analyze_properties(properties, prompt_name="roi_focus")
```

### Template Functions

RENTA provides custom Jinja2 functions for templates:

```jinja2
{# Currency formatting #}
Precio: {{ property.price_usd | currency('USD') }}

{# Percentage formatting #}
ROI: {{ roi_value | percentage(1) }}

{# Number formatting #}
Superficie: {{ property.surface_m2 | number(0) }} m²

{# Conditional formatting #}
{% if property.price_usd %}
  Precio por m²: {{ (property.price_usd / property.surface_m2) | currency('USD') }}/m²
{% else %}
  Precio: No especificado
{% endif %}

{# Calculate rental yield #}
{% set monthly_income = property.airbnb_avg_price_entire_home * 20 %}
{% set annual_yield = (monthly_income * 12 / property.price_usd * 100) | round(1) %}
Rendimiento anual estimado: {{ annual_yield }}%
```

## Response Processing

### Response Structure

```python
# AI analyzer returns list of dictionaries
summaries = [
    {
        'property_id': 'prop_123',
        'summary': 'Che, esta propiedad en Palermo está a 95.000 dólares...',
        'confidence': 0.85,
        'model_used': 'us.anthropic.claude-sonnet-4-5-20250929-v1:0',
        'tokens_used': 156,
        'processing_time_seconds': 2.3
    },
    # ... more summaries
]
```

### Language Validation

```python
def validate_spanish_response(text):
    """Validate that response is in Spanish."""
    spanish_indicators = [
        'che', 'está', 'dólares', 'pesos', 'barrio', 'zona',
        'inversión', 'alquiler', 'propiedad', 'departamento'
    ]
    
    text_lower = text.lower()
    matches = sum(1 for indicator in spanish_indicators if indicator in text_lower)
    
    # Consider valid if at least 2 Spanish indicators found
    return matches >= 2

# Automatic validation in AIAnalyzer
for summary in summaries:
    if not validate_spanish_response(summary['summary']):
        summary['confidence'] *= 0.5  # Reduce confidence for non-Spanish responses
```

## Error Handling

### Retry Logic

```python
from renta.exceptions import AIServiceConfigurationError
import time
import random

def bedrock_with_retry(analyzer, prompt, max_retries=3):
    """Call Bedrock with exponential backoff retry."""
    for attempt in range(max_retries):
        try:
            return analyzer.invoke_bedrock(prompt, system_prompt)
        
        except Exception as e:
            if attempt == max_retries - 1:
                raise AIServiceConfigurationError(f"All retries failed: {e}")
            
            # Exponential backoff with jitter
            delay = (2 ** attempt) + random.uniform(0, 1)
            time.sleep(delay)
            
            print(f"Retry {attempt + 1}/{max_retries} after {delay:.1f}s delay")
```

### Common Error Scenarios

```python
try:
    summaries = analyzer.analyze_properties(properties)
    
except AIServiceConfigurationError as e:
    if "AccessDeniedException" in str(e):
        print("AWS credentials or Bedrock access issue")
        print("1. Check AWS credentials")
        print("2. Verify Bedrock model access in AWS Console")
        
    elif "ThrottlingException" in str(e):
        print("Rate limit exceeded")
        print("Consider reducing batch size or adding delays")
        
    elif "ValidationException" in str(e):
        print("Invalid request parameters")
        print("Check model ID and request parameters")
        
except Exception as e:
    print(f"Unexpected error: {e}")
```

## Performance Optimization

### Batch Processing

```python
def process_properties_in_batches(analyzer, properties, batch_size=10):
    """Process properties in batches to manage API rate limits."""
    all_summaries = []
    
    for i in range(0, len(properties), batch_size):
        batch = properties.iloc[i:i+batch_size]
        
        try:
            batch_summaries = analyzer.analyze_properties(batch)
            all_summaries.extend(batch_summaries)
            
            # Rate limiting between batches
            time.sleep(1)
            
        except Exception as e:
            print(f"Batch {i//batch_size + 1} failed: {e}")
            # Continue with next batch
            
    return all_summaries
```

### Caching Responses

```python
import hashlib
import json
import os

class ResponseCache:
    """Cache AI responses to avoid duplicate API calls."""
    
    def __init__(self, cache_dir="~/.renta/ai_cache"):
        self.cache_dir = os.path.expanduser(cache_dir)
        os.makedirs(self.cache_dir, exist_ok=True)
    
    def get_cache_key(self, property_data, prompt_name):
        """Generate cache key from property data and prompt."""
        cache_data = {
            'property_id': property_data.get('id'),
            'price_usd': property_data.get('price_usd'),
            'airbnb_metrics': {
                'avg_price': property_data.get('airbnb_avg_price_entire_home'),
                'occupancy': property_data.get('airbnb_occupancy_probability')
            },
            'prompt_name': prompt_name
        }
        
        cache_str = json.dumps(cache_data, sort_keys=True)
        return hashlib.md5(cache_str.encode()).hexdigest()
    
    def get(self, cache_key):
        """Get cached response."""
        cache_file = os.path.join(self.cache_dir, f"{cache_key}.json")
        if os.path.exists(cache_file):
            with open(cache_file, 'r') as f:
                return json.load(f)
        return None
    
    def set(self, cache_key, response):
        """Cache response."""
        cache_file = os.path.join(self.cache_dir, f"{cache_key}.json")
        with open(cache_file, 'w') as f:
            json.dump(response, f)

# Use caching
cache = ResponseCache()

def analyze_with_cache(analyzer, properties, prompt_name="default"):
    """Analyze properties with response caching."""
    summaries = []
    
    for _, property_row in properties.iterrows():
        cache_key = cache.get_cache_key(property_row.to_dict(), prompt_name)
        cached_response = cache.get(cache_key)
        
        if cached_response:
            summaries.append(cached_response)
        else:
            # Generate new summary
            property_df = pd.DataFrame([property_row])
            new_summaries = analyzer.analyze_properties(property_df, prompt_name=prompt_name)
            
            if new_summaries:
                summary = new_summaries[0]
                cache.set(cache_key, summary)
                summaries.append(summary)
    
    return summaries
```

## Cost Management

### Token Estimation

```python
def estimate_tokens(text):
    """Rough token estimation (1 token ≈ 4 characters for Spanish)."""
    return len(text) // 4

def estimate_cost(properties, model_id="us.anthropic.claude-sonnet-4-5-20250929-v1:0"):
    """Estimate API costs for property analysis."""
    
    # Model pricing (per 1M tokens)
    pricing = {
        "us.anthropic.claude-sonnet-4-5-20250929-v1:0": {"input": 3.0, "output": 12.0},
        "us.anthropic.claude-3-5-haiku-20241022-v1:0": {"input": 0.25, "output": 1.25}
    }
    
    if model_id not in pricing:
        return "Unknown model pricing"
    
    # Estimate tokens per property
    avg_input_tokens = 300  # Prompt + property data
    avg_output_tokens = 200  # Summary response
    
    total_input_tokens = len(properties) * avg_input_tokens
    total_output_tokens = len(properties) * avg_output_tokens
    
    input_cost = (total_input_tokens / 1_000_000) * pricing[model_id]["input"]
    output_cost = (total_output_tokens / 1_000_000) * pricing[model_id]["output"]
    
    return {
        "total_properties": len(properties),
        "estimated_input_tokens": total_input_tokens,
        "estimated_output_tokens": total_output_tokens,
        "estimated_input_cost": round(input_cost, 4),
        "estimated_output_cost": round(output_cost, 4),
        "estimated_total_cost": round(input_cost + output_cost, 4)
    }

# Example usage
cost_estimate = estimate_cost(properties)
print(f"Estimated cost: ${cost_estimate['estimated_total_cost']}")
```