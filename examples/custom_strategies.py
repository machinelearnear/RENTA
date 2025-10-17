#!/usr/bin/env python3
"""
Custom Strategies Example

This script demonstrates how to extend RENTA with custom matching strategies,
export formats, and analysis logic. Use these patterns to customize RENTA
for specific use cases or markets.
"""

import os
import sys
import logging
import pandas as pd
import numpy as np
from pathlib import Path
from typing import Dict, List, Optional, Any
import json

# Add RENTA to path if running from source
sys.path.insert(0, str(Path(__file__).parent.parent))

from renta import RealEstateAnalyzer
from renta.spatial import SpatialMatchingStrategy
from renta.export import BaseExporter
from renta.ai import PromptManager

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class InvestmentFocusedMatchingStrategy(SpatialMatchingStrategy):
    """Custom matching strategy focused on investment potential."""

    def match_properties(
        self, properties: pd.DataFrame, airbnb_listings: pd.DataFrame
    ) -> pd.DataFrame:
        """Match properties with investment-focused criteria."""
        logger.info("Using investment-focused matching strategy")

        # Start with basic spatial matching
        matches = super().match_properties(properties, airbnb_listings)

        if matches.empty:
            return matches

        # Apply investment-focused filters
        filtered_matches = []

        for _, match in matches.iterrows():
            # Get property and Airbnb data
            property_data = properties[properties["id"] == match["property_id"]].iloc[0]
            airbnb_data = airbnb_listings[airbnb_listings["id"] == match["airbnb_id"]].iloc[0]

            # Investment criteria
            investment_score = self.calculate_investment_score(property_data, airbnb_data)

            # Only include matches with good investment potential
            if investment_score >= 0.6:  # Threshold for investment viability
                match_dict = match.to_dict()
                match_dict["investment_score"] = investment_score
                filtered_matches.append(match_dict)

        result = pd.DataFrame(filtered_matches)
        logger.info(f"Investment filtering: {len(matches)} → {len(result)} matches")

        return result

    def calculate_investment_score(self, property_row: pd.Series, airbnb_row: pd.Series) -> float:
        """Calculate investment viability score (0-1)."""
        score_components = []

        # 1. Price per m² competitiveness (0-1)
        price_per_m2 = property_row.get("price_usd", 0) / property_row.get("surface_m2", 1)
        if price_per_m2 > 0:
            # Assume good price is under $2000/m² for Buenos Aires
            price_score = max(0, min(1, (2500 - price_per_m2) / 1000))
            score_components.append(("price_competitiveness", price_score, 0.3))

        # 2. Rental yield potential (0-1)
        nightly_rate = airbnb_row.get("price_usd_per_night", 0)
        property_price = property_row.get("price_usd", 0)
        if nightly_rate > 0 and property_price > 0:
            # Estimate monthly income (assume 20 nights/month occupancy)
            monthly_income = nightly_rate * 20
            annual_yield = (monthly_income * 12) / property_price
            # Good yield is 8%+ annually
            yield_score = min(1, annual_yield / 0.08)
            score_components.append(("rental_yield", yield_score, 0.4))

        # 3. Location quality (based on Airbnb review scores)
        location_score = airbnb_row.get("review_score_location", 0) / 5.0
        score_components.append(("location_quality", location_score, 0.2))

        # 4. Property engagement (views per day)
        views_per_day = property_row.get("views_per_day", 0)
        if views_per_day > 0:
            # High engagement is 50+ views/day
            engagement_score = min(1, views_per_day / 50)
            score_components.append(("market_interest", engagement_score, 0.1))

        # Calculate weighted average
        if score_components:
            weighted_sum = sum(score * weight for _, score, weight in score_components)
            total_weight = sum(weight for _, _, weight in score_components)
            final_score = weighted_sum / total_weight if total_weight > 0 else 0
        else:
            final_score = 0

        return final_score


class ROIAnalysisExporter(BaseExporter):
    """Custom exporter that focuses on ROI analysis."""

    def export_to_file(self, data: pd.DataFrame, path: str) -> str:
        """Export ROI analysis to Excel with multiple sheets."""
        import pandas as pd

        with pd.ExcelWriter(path, engine="openpyxl") as writer:
            # Main properties sheet
            main_data = self.prepare_main_data(data)
            main_data.to_excel(writer, sheet_name="Properties", index=False)

            # ROI analysis sheet
            roi_analysis = self.calculate_roi_metrics(data)
            roi_analysis.to_excel(writer, sheet_name="ROI_Analysis", index=False)

            # Investment recommendations
            recommendations = self.generate_recommendations(data)
            recommendations.to_excel(writer, sheet_name="Recommendations", index=False)

            # Market summary
            market_summary = self.calculate_market_summary(data)
            market_summary.to_excel(writer, sheet_name="Market_Summary", index=True)

        return path

    def export_to_memory(self, data: pd.DataFrame) -> Dict:
        """Export ROI analysis to dictionary."""
        return {
            "properties": self.prepare_main_data(data).to_dict("records"),
            "roi_analysis": self.calculate_roi_metrics(data).to_dict("records"),
            "recommendations": self.generate_recommendations(data).to_dict("records"),
            "market_summary": self.calculate_market_summary(data).to_dict(),
        }

    def prepare_main_data(self, data: pd.DataFrame) -> pd.DataFrame:
        """Prepare main property data with ROI calculations."""
        if data.empty:
            return data

        result = data.copy()

        # Calculate ROI metrics
        if "airbnb_avg_price_entire_home" in result.columns and "price_usd" in result.columns:
            # Estimated monthly income (20 nights/month)
            result["estimated_monthly_income"] = result["airbnb_avg_price_entire_home"] * 20

            # Annual rental yield
            result["estimated_annual_yield"] = (
                (result["estimated_monthly_income"] * 12) / result["price_usd"] * 100
            ).round(2)

            # Payback period in years
            result["payback_period_years"] = (
                result["price_usd"] / (result["estimated_monthly_income"] * 12)
            ).round(1)

        # Price per m² analysis
        if "price_usd" in result.columns and "surface_m2" in result.columns:
            result["price_per_m2"] = (result["price_usd"] / result["surface_m2"]).round(0)

        # Investment score (if available from custom matching)
        if "investment_score" not in result.columns:
            result["investment_score"] = 0.5  # Default neutral score

        return result

    def calculate_roi_metrics(self, data: pd.DataFrame) -> pd.DataFrame:
        """Calculate detailed ROI metrics."""
        if data.empty:
            return pd.DataFrame()

        roi_data = []

        for _, row in data.iterrows():
            if pd.notna(row.get("price_usd")) and pd.notna(row.get("airbnb_avg_price_entire_home")):
                monthly_income = row["airbnb_avg_price_entire_home"] * 20
                annual_income = monthly_income * 12
                purchase_price = row["price_usd"]

                # Calculate various ROI metrics
                roi_metrics = {
                    "property_id": row.get("id"),
                    "title": row.get("title", ""),
                    "purchase_price_usd": purchase_price,
                    "estimated_monthly_income": monthly_income,
                    "estimated_annual_income": annual_income,
                    "gross_yield_percent": (annual_income / purchase_price * 100).round(2),
                    "monthly_roi_percent": (monthly_income / purchase_price * 100).round(3),
                    "payback_period_years": (purchase_price / annual_income).round(1),
                    "break_even_occupancy_percent": (
                        (purchase_price * 0.08) / (row["airbnb_avg_price_entire_home"] * 365) * 100
                    ).round(
                        1
                    ),  # Assuming 8% target yield
                    "investment_score": row.get("investment_score", 0.5),
                }

                roi_data.append(roi_metrics)

        return pd.DataFrame(roi_data)

    def generate_recommendations(self, data: pd.DataFrame) -> pd.DataFrame:
        """Generate investment recommendations."""
        if data.empty:
            return pd.DataFrame()

        recommendations = []

        # Sort by investment score
        sorted_data = (
            data.sort_values("investment_score", ascending=False)
            if "investment_score" in data.columns
            else data
        )

        for i, (_, row) in enumerate(sorted_data.head(10).iterrows()):
            recommendation = {
                "rank": i + 1,
                "property_id": row.get("id"),
                "title": row.get("title", ""),
                "price_usd": row.get("price_usd"),
                "investment_score": row.get("investment_score", 0.5),
                "recommendation": self.get_recommendation_text(row),
                "risk_level": self.assess_risk_level(row),
                "target_investor": self.identify_target_investor(row),
            }
            recommendations.append(recommendation)

        return pd.DataFrame(recommendations)

    def get_recommendation_text(self, row: pd.Series) -> str:
        """Generate recommendation text for a property."""
        score = row.get("investment_score", 0.5)
        price = row.get("price_usd", 0)
        yield_pct = 0

        if pd.notna(row.get("airbnb_avg_price_entire_home")) and price > 0:
            annual_income = row["airbnb_avg_price_entire_home"] * 20 * 12
            yield_pct = annual_income / price * 100

        if score >= 0.8:
            return (
                f"Strong Buy - Excellent investment potential with {yield_pct:.1f}% estimated yield"
            )
        elif score >= 0.6:
            return f"Buy - Good investment opportunity with {yield_pct:.1f}% estimated yield"
        elif score >= 0.4:
            return f"Hold - Moderate potential, consider market conditions"
        else:
            return f"Avoid - Below investment threshold"

    def assess_risk_level(self, row: pd.Series) -> str:
        """Assess investment risk level."""
        price = row.get("price_usd", 0)
        views = row.get("views_per_day", 0)

        if price < 60000 and views > 50:
            return "Low"
        elif price < 100000 and views > 30:
            return "Medium"
        else:
            return "High"

    def identify_target_investor(self, row: pd.Series) -> str:
        """Identify target investor type."""
        price = row.get("price_usd", 0)
        yield_pct = 0

        if pd.notna(row.get("airbnb_avg_price_entire_home")) and price > 0:
            annual_income = row["airbnb_avg_price_entire_home"] * 20 * 12
            yield_pct = annual_income / price * 100

        if price < 70000:
            return "First-time investor"
        elif yield_pct > 10:
            return "Yield-focused investor"
        elif price > 120000:
            return "Premium investor"
        else:
            return "Balanced investor"

    def calculate_market_summary(self, data: pd.DataFrame) -> pd.DataFrame:
        """Calculate market summary statistics."""
        if data.empty:
            return pd.DataFrame()

        summary_stats = {}

        # Price statistics
        if "price_usd" in data.columns:
            summary_stats.update(
                {
                    "Average Price (USD)": data["price_usd"].mean(),
                    "Median Price (USD)": data["price_usd"].median(),
                    "Min Price (USD)": data["price_usd"].min(),
                    "Max Price (USD)": data["price_usd"].max(),
                }
            )

        # Yield statistics
        if "airbnb_avg_price_entire_home" in data.columns and "price_usd" in data.columns:
            yields = (data["airbnb_avg_price_entire_home"] * 20 * 12) / data["price_usd"] * 100
            summary_stats.update(
                {
                    "Average Yield (%)": yields.mean(),
                    "Median Yield (%)": yields.median(),
                    "Best Yield (%)": yields.max(),
                }
            )

        # Market activity
        if "views_per_day" in data.columns:
            summary_stats.update(
                {
                    "Average Views/Day": data["views_per_day"].mean(),
                    "High Interest Properties (>50 views/day)": len(
                        data[data["views_per_day"] > 50]
                    ),
                }
            )

        # Investment scores
        if "investment_score" in data.columns:
            summary_stats.update(
                {
                    "Average Investment Score": data["investment_score"].mean(),
                    "Strong Investment Opportunities (>0.7)": len(
                        data[data["investment_score"] > 0.7]
                    ),
                }
            )

        return pd.DataFrame(list(summary_stats.items()), columns=["Metric", "Value"])


class CustomPromptManager(PromptManager):
    """Custom prompt manager with investment-focused templates."""

    def __init__(self, config):
        super().__init__(config)

        # Register custom prompts
        self.register_investment_prompts()

    def register_investment_prompts(self):
        """Register investment-focused prompt templates."""

        # ROI-focused prompt
        roi_prompt = """
Sos un analista de inversiones inmobiliarias especializado en Buenos Aires.
Analizá esta propiedad desde una perspectiva de ROI y rentabilidad:

**Datos de la Propiedad:**
- Título: {{ property.title }}
- Precio: USD {{ property.price_usd | default('No especificado') }}
- Superficie: {{ property.surface_m2 | default('No especificado') }} m²
- Precio por m²: USD {{ (property.price_usd / property.surface_m2) | round(0) | default('N/A') }}/m²

**Análisis de Rentabilidad:**
{% if property.airbnb_avg_price_entire_home %}
- Tarifa Airbnb promedio: USD {{ property.airbnb_avg_price_entire_home }}/noche
- Ingresos mensuales estimados: USD {{ (property.airbnb_avg_price_entire_home * 20) | round(0) }}
- Rendimiento anual estimado: {{ ((property.airbnb_avg_price_entire_home * 20 * 12) / property.price_usd * 100) | round(1) }}%
- Período de recuperación: {{ (property.price_usd / (property.airbnb_avg_price_entire_home * 20 * 12)) | round(1) }} años
{% endif %}

**Score de Inversión:** {{ property.investment_score | default(0.5) | round(2) }}/1.0

Proporcioná un análisis de inversión enfocado en:
1. Viabilidad del ROI y período de recuperación
2. Riesgos y oportunidades específicas
3. Recomendación de compra (Comprar/Esperar/Evitar)
4. Perfil de inversor ideal

Máximo 150 palabras, tono profesional pero accesible.
"""

        self.register_custom_prompt("roi_analysis", roi_prompt)

        # Market comparison prompt
        market_prompt = """
Compará esta propiedad con el mercado de Buenos Aires:

**Propiedad Analizada:**
- Precio: USD {{ property.price_usd }}
- Barrio: {{ property.address | regex_replace('.*,\\s*', '') }}
- Rendimiento estimado: {{ ((property.airbnb_avg_price_entire_home * 20 * 12) / property.price_usd * 100) | round(1) }}%

**Contexto de Mercado:**
- Engagement: {{ property.views_per_day | default(0) }} views/día
- Score de inversión: {{ property.investment_score | round(2) }}

Analizá:
1. Posicionamiento vs. mercado promedio
2. Ventajas competitivas de ubicación
3. Potencial de apreciación
4. Timing de compra

Máximo 120 palabras.
"""

        self.register_custom_prompt("market_comparison", market_prompt)


def main():
    """Demonstrate custom strategies."""

    logger.info("Starting custom strategies example")

    # Example search URL
    search_url = (
        "https://www.zonaprop.com.ar/inmuebles-venta-palermo-2-dormitorios-50000-130000-dolar.html"
    )

    try:
        # Initialize analyzer
        analyzer = RealEstateAnalyzer()

        # Register custom matching strategy
        custom_strategy = InvestmentFocusedMatchingStrategy(analyzer.config)
        analyzer._spatial_matcher.register_strategy("investment_focused", custom_strategy)
        analyzer._spatial_matcher.set_strategy("investment_focused")

        # Register custom exporter
        roi_exporter = ROIAnalysisExporter()
        analyzer._export_manager.register_exporter("roi_analysis", roi_exporter)

        # Register custom prompt manager
        custom_prompt_manager = CustomPromptManager(analyzer.config)
        analyzer._ai_analyzer._prompt_manager = custom_prompt_manager

        logger.info("✓ Custom strategies registered")

        # Download Airbnb data
        logger.info("Downloading Airbnb data...")
        airbnb_data = analyzer.download_airbnb_data()

        # Scrape properties
        logger.info("Scraping properties...")
        properties = analyzer.scrape_zonaprop(search_url)

        if len(properties) == 0:
            logger.warning("No properties found")
            return

        # Enrich with custom matching strategy
        logger.info("Enriching with investment-focused matching...")
        enriched_properties = analyzer.enrich_with_airbnb(properties)

        # Generate summaries with custom prompts
        logger.info("Generating ROI-focused summaries...")
        roi_summaries = analyzer.generate_summaries(
            enriched_properties.head(3), prompt_name="roi_analysis"
        )

        logger.info("Generating market comparison summaries...")
        market_summaries = analyzer.generate_summaries(
            enriched_properties.head(3), prompt_name="market_comparison"
        )

        # Export with custom ROI exporter
        logger.info("Exporting ROI analysis...")
        roi_export_path = analyzer.export(
            enriched_properties, format="roi_analysis", path="roi_analysis.xlsx"
        )

        logger.info(f"✓ ROI analysis exported: {roi_export_path}")

        # Show sample results
        if roi_summaries:
            logger.info("Sample ROI analysis:")
            logger.info(f"  {roi_summaries[0]['summary'][:100]}...")

        if market_summaries:
            logger.info("Sample market comparison:")
            logger.info(f"  {market_summaries[0]['summary'][:100]}...")

        # Show investment scores
        if "investment_score" in enriched_properties.columns:
            top_investments = enriched_properties.nlargest(3, "investment_score")
            logger.info("Top investment opportunities:")
            for _, prop in top_investments.iterrows():
                logger.info(f"  {prop['title'][:50]}... - Score: {prop['investment_score']:.2f}")

        logger.info("Custom strategies example completed successfully!")

    except Exception as e:
        logger.error(f"Custom strategies example failed: {e}")

    finally:
        if "analyzer" in locals():
            analyzer.close()


if __name__ == "__main__":
    main()
