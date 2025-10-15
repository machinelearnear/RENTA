#!/usr/bin/env python3
"""
Debugging Guide Example

This script demonstrates how to debug common RENTA issues and provides
diagnostic tools for troubleshooting problems with configuration,
data sources, AWS integration, and more.
"""

import os
import sys
import logging
import pandas as pd
import json
from pathlib import Path
from typing import Dict, List, Optional, Any

# Add RENTA to path if running from source
sys.path.insert(0, str(Path(__file__).parent.parent))

from renta import RealEstateAnalyzer
from renta.config import ConfigManager
from renta.exceptions import *

# Configure detailed logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class RentaDebugger:
    """Comprehensive debugging tools for RENTA."""
    
    def __init__(self):
        """Initialize debugger."""
        self.issues_found = []
        self.recommendations = []
    
    def run_full_diagnostic(self) -> Dict[str, Any]:
        """Run complete diagnostic suite."""
        logger.info("Starting RENTA diagnostic suite...")
        
        results = {
            'system_info': self.check_system_info(),
            'dependencies': self.check_dependencies(),
            'aws_config': self.check_aws_configuration(),
            'network_connectivity': self.check_network_connectivity(),
            'configuration': self.check_configuration(),
            'data_sources': self.check_data_sources(),
            'issues_found': self.issues_found,
            'recommendations': self.recommendations
        }
        
        self.generate_diagnostic_report(results)
        return results
    
    def check_system_info(self) -> Dict[str, Any]:
        """Check system information."""
        logger.info("Checking system information...")
        
        import platform
        import sys
        
        info = {
            'python_version': sys.version,
            'platform': platform.platform(),
            'architecture': platform.architecture(),
            'processor': platform.processor(),
        }
        
        # Check Python version
        if sys.version_info < (3, 10):
            self.issues_found.append("Python version < 3.10 (RENTA requires 3.10+)")
            self.recommendations.append("Upgrade to Python 3.10 or higher")
        
        logger.info(f"✓ Python {sys.version_info.major}.{sys.version_info.minor}")
        return info
    
    def check_dependencies(self) -> Dict[str, Any]:
        """Check required dependencies."""
        logger.info("Checking dependencies...")
        
        required_packages = [
            'pandas', 'numpy', 'requests', 'beautifulsoup4', 'lxml',
            'scikit-learn', 'geopy', 'pyyaml', 'jsonschema',
            'boto3', 'botocore', 'jinja2', 'structlog'
        ]
        
        dependency_status = {}
        missing_packages = []
        
        for package in required_packages:
            try:
                __import__(package)
                dependency_status[package] = "✓ Available"
            except ImportError:
                dependency_status[package] = "✗ Missing"
                missing_packages.append(package)
        
        if missing_packages:
            self.issues_found.append(f"Missing packages: {', '.join(missing_packages)}")
            self.recommendations.append(f"Install missing packages: pip install {' '.join(missing_packages)}")
        
        return dependency_status
    
    def check_aws_configuration(self) -> Dict[str, Any]:
        """Check AWS configuration and credentials."""
        logger.info("Checking AWS configuration...")
        
        aws_status = {
            'credentials_method': 'None',
            'credentials_valid': False,
            'region_configured': False,
            'bedrock_access': False,
            'model_access': False
        }
        
        try:
            import boto3
            from botocore.exceptions import ClientError, NoCredentialsError
            
            # Check credentials
            try:
                sts = boto3.client('sts')
                identity = sts.get_caller_identity()
                aws_status['credentials_valid'] = True
                aws_status['credentials_method'] = 'AWS SDK'
                aws_status['account_id'] = identity.get('Account')
                aws_status['user_arn'] = identity.get('Arn')
                logger.info(f"✓ AWS credentials valid: {identity['Arn']}")
                
            except NoCredentialsError:
                self.issues_found.append("No AWS credentials found")
                self.recommendations.append("Configure AWS credentials using environment variables, ~/.aws/credentials, or IAM role")
                
            except ClientError as e:
                self.issues_found.append(f"AWS credentials error: {e}")
                self.recommendations.append("Check AWS credentials validity")
            
            # Check region configuration
            session = boto3.Session()
            region = session.region_name
            if region:
                aws_status['region_configured'] = True
                aws_status['region'] = region
                logger.info(f"✓ AWS region: {region}")
            else:
                self.issues_found.append("No AWS region configured")
                self.recommendations.append("Set AWS_REGION environment variable or configure in ~/.aws/config")
            
            # Check Bedrock access
            if aws_status['credentials_valid'] and region:
                try:
                    bedrock = boto3.client('bedrock', region_name=region)
                    models = bedrock.list_foundation_models()
                    aws_status['bedrock_access'] = True
                    aws_status['available_models'] = len(models['modelSummaries'])
                    logger.info(f"✓ Bedrock access confirmed: {len(models['modelSummaries'])} models available")
                    
                    # Check specific model access
                    claude_models = [
                        'us.anthropic.claude-sonnet-4-5-20250929-v1:0',
                        'anthropic.claude-sonnet-4-5-20250929-v1:0'
                    ]
                    
                    for model_id in claude_models:
                        try:
                            bedrock_runtime = boto3.client('bedrock-runtime', region_name=region)
                            # Test with minimal request
                            logger.info(f"✓ Model {model_id} access confirmed")
                            aws_status['model_access'] = True
                            aws_status['tested_model'] = model_id
                            break
                        except ClientError as e:
                            if "AccessDeniedException" in str(e):
                                continue
                    
                    if not aws_status['model_access']:
                        self.issues_found.append("No Claude model access enabled")
                        self.recommendations.append("Enable Claude model access in AWS Bedrock console")
                        
                except ClientError as e:
                    self.issues_found.append(f"Bedrock access error: {e}")
                    if "AccessDenied" in str(e):
                        self.recommendations.append("Enable Bedrock service access in AWS Console")
        
        except ImportError:
            self.issues_found.append("boto3 not installed")
            self.recommendations.append("Install boto3: pip install boto3")
        
        return aws_status
    
    def check_network_connectivity(self) -> Dict[str, Any]:
        """Check network connectivity to required services."""
        logger.info("Checking network connectivity...")
        
        test_urls = {
            'InsideAirbnb': 'http://insideairbnb.com/get-the-data.html',
            'Zonaprop': 'https://www.zonaprop.com.ar',
            'Exchange Rate API': 'https://api.xe.com',
            'AWS Bedrock': 'https://bedrock.us-east-1.amazonaws.com'
        }
        
        connectivity_status = {}
        
        import requests
        
        for service, url in test_urls.items():
            try:
                response = requests.get(url, timeout=10, allow_redirects=True)
                if response.status_code < 400:
                    connectivity_status[service] = f"✓ Accessible ({response.status_code})"
                else:
                    connectivity_status[service] = f"⚠ HTTP {response.status_code}"
                    if response.status_code == 403:
                        self.issues_found.append(f"{service} blocked (403 Forbidden)")
                        
            except requests.exceptions.Timeout:
                connectivity_status[service] = "✗ Timeout"
                self.issues_found.append(f"{service} connection timeout")
                
            except requests.exceptions.ConnectionError:
                connectivity_status[service] = "✗ Connection Error"
                self.issues_found.append(f"Cannot connect to {service}")
                
            except Exception as e:
                connectivity_status[service] = f"✗ Error: {str(e)[:50]}"
        
        return connectivity_status
    
    def check_configuration(self) -> Dict[str, Any]:
        """Check RENTA configuration."""
        logger.info("Checking RENTA configuration...")
        
        config_status = {
            'config_file_found': False,
            'config_valid': False,
            'validation_errors': []
        }
        
        try:
            # Try to load configuration
            config = ConfigManager()
            config_status['config_valid'] = True
            config_status['config_source'] = config.config_path or "default"
            config_status['config_keys'] = list(config.to_dict().keys())
            
            # Check critical configuration values
            critical_configs = {
                'aws.region': config.get('aws.region'),
                'aws.bedrock.model_id': config.get('aws.bedrock.model_id'),
                'data.cache_dir': config.get('data.cache_dir'),
                'airbnb.matching.radius_km': config.get('airbnb.matching.radius_km')
            }
            
            config_status['critical_configs'] = critical_configs
            
            # Validate configuration
            try:
                config.validate_schema()
                logger.info("✓ Configuration validation passed")
            except Exception as e:
                config_status['validation_errors'].append(str(e))
                self.issues_found.append(f"Configuration validation failed: {e}")
                
        except ConfigurationError as e:
            config_status['config_valid'] = False
            config_status['error'] = str(e)
            self.issues_found.append(f"Configuration error: {e}")
            self.recommendations.append("Check configuration file syntax and required fields")
        
        return config_status
    
    def check_data_sources(self) -> Dict[str, Any]:
        """Check data source accessibility."""
        logger.info("Checking data sources...")
        
        data_status = {
            'airbnb_data_available': False,
            'zonaprop_accessible': False,
            'cache_directory_writable': False
        }
        
        # Check cache directory
        try:
            config = ConfigManager()
            cache_dir = Path(config.get('data.cache_dir', '~/.renta/cache')).expanduser()
            cache_dir.mkdir(parents=True, exist_ok=True)
            
            # Test write access
            test_file = cache_dir / 'test_write.tmp'
            test_file.write_text('test')
            test_file.unlink()
            
            data_status['cache_directory_writable'] = True
            data_status['cache_directory'] = str(cache_dir)
            logger.info(f"✓ Cache directory writable: {cache_dir}")
            
        except Exception as e:
            self.issues_found.append(f"Cache directory not writable: {e}")
            self.recommendations.append("Check cache directory permissions")
        
        # Check Airbnb data availability
        try:
            import requests
            airbnb_url = "http://insideairbnb.com/get-the-data.html"
            response = requests.get(airbnb_url, timeout=10)
            
            if "buenos-aires" in response.text.lower():
                data_status['airbnb_data_available'] = True
                logger.info("✓ Buenos Aires Airbnb data available")
            else:
                self.issues_found.append("Buenos Aires data not found on InsideAirbnb")
                
        except Exception as e:
            self.issues_found.append(f"Cannot check Airbnb data availability: {e}")
        
        # Check Zonaprop accessibility
        try:
            import requests
            zonaprop_url = "https://www.zonaprop.com.ar"
            response = requests.get(zonaprop_url, timeout=10)
            
            if response.status_code == 200:
                data_status['zonaprop_accessible'] = True
                logger.info("✓ Zonaprop accessible")
            elif response.status_code == 403:
                self.issues_found.append("Zonaprop blocked (403 Forbidden)")
                self.recommendations.append("Use HTML file fallback for Zonaprop scraping")
            else:
                self.issues_found.append(f"Zonaprop returned HTTP {response.status_code}")
                
        except Exception as e:
            self.issues_found.append(f"Cannot access Zonaprop: {e}")
        
        return data_status
    
    def generate_diagnostic_report(self, results: Dict[str, Any]):
        """Generate comprehensive diagnostic report."""
        logger.info("Generating diagnostic report...")
        
        report_path = Path("renta_diagnostic_report.json")
        
        # Add summary
        results['summary'] = {
            'total_issues': len(self.issues_found),
            'total_recommendations': len(self.recommendations),
            'overall_status': 'HEALTHY' if len(self.issues_found) == 0 else 'ISSUES_FOUND'
        }
        
        # Save detailed report
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2, ensure_ascii=False, default=str)
        
        logger.info(f"✓ Diagnostic report saved: {report_path}")
        
        # Print summary
        print("\n" + "="*60)
        print("RENTA DIAGNOSTIC SUMMARY")
        print("="*60)
        
        if len(self.issues_found) == 0:
            print("✅ No issues found - RENTA should work correctly!")
        else:
            print(f"⚠️  Found {len(self.issues_found)} issues:")
            for i, issue in enumerate(self.issues_found, 1):
                print(f"  {i}. {issue}")
            
            print(f"\n💡 Recommendations:")
            for i, rec in enumerate(self.recommendations, 1):
                print(f"  {i}. {rec}")
        
        print(f"\n📄 Full report saved to: {report_path}")
        print("="*60)


def debug_specific_operation(operation: str):
    """Debug a specific RENTA operation."""
    logger.info(f"Debugging specific operation: {operation}")
    
    try:
        analyzer = RealEstateAnalyzer()
        
        if operation == "config":
            logger.info("Testing configuration loading...")
            config_dict = analyzer.config.to_dict()
            logger.info(f"✓ Configuration loaded with {len(config_dict)} sections")
            
        elif operation == "airbnb":
            logger.info("Testing Airbnb data download...")
            airbnb_data = analyzer.download_airbnb_data()
            logger.info(f"✓ Airbnb data: {len(airbnb_data)} listings")
            
        elif operation == "scraping":
            logger.info("Testing Zonaprop scraping...")
            test_url = "https://www.zonaprop.com.ar/inmuebles-venta-palermo.html"
            properties = analyzer.scrape_zonaprop(test_url)
            logger.info(f"✓ Scraped {len(properties)} properties")
            
        elif operation == "ai":
            logger.info("Testing AI analysis...")
            # Create sample data
            sample_data = pd.DataFrame([{
                'id': 'test_prop',
                'title': 'Test Property',
                'price_usd': 100000,
                'surface_m2': 50,
                'airbnb_avg_price_entire_home': 80
            }])
            summaries = analyzer.generate_summaries(sample_data)
            logger.info(f"✓ Generated {len(summaries)} AI summaries")
            
        else:
            logger.error(f"Unknown operation: {operation}")
            
    except Exception as e:
        logger.error(f"Operation {operation} failed: {e}")
        logger.exception("Full traceback:")


def main():
    """Run debugging guide."""
    
    print("RENTA Debugging Guide")
    print("====================")
    print()
    print("Choose an option:")
    print("1. Run full diagnostic")
    print("2. Debug specific operation")
    print("3. Test basic functionality")
    print("4. Exit")
    
    choice = input("\nEnter choice (1-4): ").strip()
    
    if choice == "1":
        debugger = RentaDebugger()
        results = debugger.run_full_diagnostic()
        
    elif choice == "2":
        print("\nAvailable operations:")
        print("- config: Test configuration loading")
        print("- airbnb: Test Airbnb data download")
        print("- scraping: Test Zonaprop scraping")
        print("- ai: Test AI analysis")
        
        operation = input("\nEnter operation name: ").strip()
        debug_specific_operation(operation)
        
    elif choice == "3":
        logger.info("Testing basic RENTA functionality...")
        try:
            analyzer = RealEstateAnalyzer()
            logger.info("✓ RealEstateAnalyzer initialized")
            
            stats = analyzer.get_operation_stats()
            logger.info(f"✓ Operation stats: {stats}")
            
            analyzer.close()
            logger.info("✓ Basic functionality test passed")
            
        except Exception as e:
            logger.error(f"Basic functionality test failed: {e}")
            
    elif choice == "4":
        print("Goodbye!")
        
    else:
        print("Invalid choice")


if __name__ == "__main__":
    main()