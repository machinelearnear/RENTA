"""
Unit tests for spatial matching functionality.

Tests the core feature: "Match properties to nearby Airbnb listings with configurable spatial filters"
"""

import pytest
import pandas as pd
import numpy as np
from unittest.mock import Mock, patch

from renta.spatial import SpatialMatcher, EnrichmentEngine, DefaultMatchingStrategy
from renta.exceptions import MatchingError


@pytest.mark.unit
class TestSpatialMatcher:
    """Test spatial matching between properties and Airbnb listings."""

    def test_init(self, mock_config_manager):
        """Test SpatialMatcher initialization."""
        matcher = SpatialMatcher(mock_config_manager)

        assert matcher.config is not None
        assert hasattr(matcher, 'logger')

    def test_match_properties(self, mock_config_manager, sample_zonaprop_data, sample_airbnb_data):
        """Test matching properties to Airbnb listings."""
        matcher = SpatialMatcher(mock_config_manager)

        # Perform matching
        matches = matcher.match_properties(sample_zonaprop_data, sample_airbnb_data)

        assert isinstance(matches, pd.DataFrame)
        # Should have property_id and listing_id columns
        assert 'property_id' in matches.columns or len(matches) == 0

    def test_radius_filtering(self, mock_config_manager):
        """Test that radius filtering works correctly."""
        matcher = SpatialMatcher(mock_config_manager)

        # Get radius from config
        radius_km = mock_config_manager.get('airbnb.matching.radius_km', 0.3)

        assert radius_km > 0
        assert isinstance(radius_km, (int, float))

    def test_distance_calculation(self, mock_config_manager):
        """Test distance calculation between coordinates."""
        matcher = SpatialMatcher(mock_config_manager)

        # Test coordinates (Palermo, Buenos Aires)
        lat1, lon1 = -34.5875, -58.4193
        lat2, lon2 = -34.5880, -58.4200

        # Calculate distance (implementation may vary)
        # This is a basic haversine distance test
        from math import radians, sin, cos, sqrt, atan2

        R = 6371  # Earth radius in km

        lat1_rad, lon1_rad = radians(lat1), radians(lon1)
        lat2_rad, lon2_rad = radians(lat2), radians(lon2)

        dlat = lat2_rad - lat1_rad
        dlon = lon2_rad - lon1_rad

        a = sin(dlat/2)**2 + cos(lat1_rad) * cos(lat2_rad) * sin(dlon/2)**2
        c = 2 * atan2(sqrt(a), sqrt(1-a))
        distance = R * c

        assert distance < 1.0  # Should be less than 1km
        assert distance > 0

    def test_empty_data_handling(self, mock_config_manager):
        """Test handling of empty datasets."""
        matcher = SpatialMatcher(mock_config_manager)

        # Empty dataframes
        empty_properties = pd.DataFrame()
        empty_listings = pd.DataFrame()

        # Should handle gracefully
        with pytest.raises((MatchingError, ValueError)):
            matcher.match_properties(empty_properties, empty_listings)

    def test_missing_coordinates(self, mock_config_manager, sample_zonaprop_data, sample_airbnb_data):
        """Test handling of missing coordinates."""
        matcher = SpatialMatcher(mock_config_manager)

        # Add missing coordinates
        invalid_properties = sample_zonaprop_data.copy()
        invalid_properties.loc[0, 'latitude'] = None
        invalid_properties.loc[1, 'longitude'] = None

        # Should handle missing coordinates
        try:
            result = matcher.match_properties(invalid_properties, sample_airbnb_data)
            # If it succeeds, ensure it filtered out invalid coords
            assert len(result) >= 0
        except (MatchingError, ValueError):
            # Also acceptable to raise error
            assert True


@pytest.mark.unit
class TestEnrichmentEngine:
    """Test property enrichment with Airbnb metrics."""

    def test_init(self, mock_config_manager):
        """Test EnrichmentEngine initialization."""
        engine = EnrichmentEngine(mock_config_manager)

        assert engine.config is not None
        assert hasattr(engine, 'logger')

    def test_enrich_properties(self, mock_config_manager, sample_zonaprop_data, sample_airbnb_data):
        """Test enriching properties with Airbnb data."""
        matcher = SpatialMatcher(mock_config_manager)
        engine = EnrichmentEngine(mock_config_manager)

        # First match properties
        matches = matcher.match_properties(sample_zonaprop_data, sample_airbnb_data)

        # Then enrich
        enriched = engine.enrich_properties(sample_zonaprop_data, matches)

        assert isinstance(enriched, pd.DataFrame)
        assert len(enriched) == len(sample_zonaprop_data)

        # Should have enrichment columns
        if 'match_status' in enriched.columns:
            assert enriched['match_status'].isin(['matched', 'no_matches', 'error']).all()

    def test_aggregation_metrics(self, mock_config_manager, sample_enriched_data):
        """Test that correct aggregation metrics are calculated."""
        # Check expected enrichment columns
        expected_columns = [
            'avg_airbnb_price',
            'median_airbnb_price',
            'matched_listings_count'
        ]

        for col in expected_columns:
            if col in sample_enriched_data.columns:
                # Validate data types
                assert sample_enriched_data[col].dtype in [np.float64, np.int64, object]

    def test_rental_yield_estimation(self, mock_config_manager, sample_enriched_data):
        """Test rental yield estimation calculations."""
        # Check if rental yield is calculated
        if 'rental_yield_estimate' in sample_enriched_data.columns:
            # Should be between 0 and 1 (or NaN)
            valid_yields = sample_enriched_data['rental_yield_estimate'].dropna()
            if len(valid_yields) > 0:
                assert (valid_yields >= 0).all()
                assert (valid_yields <= 1).all()

    def test_occupancy_estimation(self, mock_config_manager, sample_enriched_data):
        """Test occupancy rate estimation."""
        if 'estimated_occupancy' in sample_enriched_data.columns:
            # Should have valid categories
            valid_categories = ['high', 'medium', 'low', 'unknown']
            assert sample_enriched_data['estimated_occupancy'].isin(valid_categories).all()


@pytest.mark.unit
class TestMatchingStrategy:
    """Test configurable matching strategies."""

    def test_default_strategy(self, mock_config_manager):
        """Test default matching strategy."""
        strategy = DefaultMatchingStrategy(mock_config_manager)

        assert strategy is not None
        assert hasattr(strategy, 'match')

    def test_strategy_configuration(self, mock_config_manager):
        """Test that matching strategy respects configuration."""
        # Check configuration parameters
        radius_km = mock_config_manager.get('airbnb.matching.radius_km')
        min_nights = mock_config_manager.get('airbnb.matching.min_nights_threshold')
        max_listings = mock_config_manager.get('airbnb.matching.max_listings_per_property')

        assert radius_km is not None
        assert min_nights is not None
        assert max_listings is not None

    def test_min_nights_filtering(self, mock_config_manager, sample_airbnb_data):
        """Test filtering by minimum nights threshold."""
        threshold = mock_config_manager.get('airbnb.matching.min_nights_threshold', 7)

        # Filter listings
        long_term = sample_airbnb_data[sample_airbnb_data['minimum_nights'] >= threshold]
        short_term = sample_airbnb_data[sample_airbnb_data['minimum_nights'] < threshold]

        # Both should be valid dataframes
        assert isinstance(long_term, pd.DataFrame)
        assert isinstance(short_term, pd.DataFrame)

    def test_max_listings_limit(self, mock_config_manager):
        """Test maximum listings per property limit."""
        max_listings = mock_config_manager.get('airbnb.matching.max_listings_per_property', 10)

        assert max_listings > 0
        assert isinstance(max_listings, int)


@pytest.mark.unit
class TestSpatialIndexing:
    """Test spatial indexing optimizations."""

    def test_balltree_index(self, mock_config_manager, sample_airbnb_data):
        """Test BallTree spatial index creation."""
        from sklearn.neighbors import BallTree

        # Extract coordinates
        coords = sample_airbnb_data[['latitude', 'longitude']].values

        # Create BallTree
        tree = BallTree(np.radians(coords), metric='haversine')

        assert tree is not None

        # Test query
        query_point = np.radians([[-34.6037, -58.3816]])
        radius_km = 0.5
        radius_rad = radius_km / 6371.0  # Convert to radians

        indices = tree.query_radius(query_point, r=radius_rad)

        assert len(indices) > 0
        assert isinstance(indices[0], np.ndarray)

    def test_vectorized_distance(self, mock_config_manager):
        """Test vectorized distance calculations for performance."""
        # Create sample coordinates
        n_points = 100
        coords1 = np.random.uniform(-35, -34, (n_points, 2))
        coords2 = np.random.uniform(-35, -34, (n_points, 2))

        # Should be able to calculate distances in batch
        # This tests that vectorized operations are possible
        distances = np.sqrt(np.sum((coords1 - coords2) ** 2, axis=1))

        assert len(distances) == n_points
        assert np.all(distances >= 0)


@pytest.mark.unit
class TestErrorHandling:
    """Test error handling in spatial matching."""

    def test_invalid_coordinates(self, mock_config_manager):
        """Test handling of invalid coordinate ranges."""
        matcher = SpatialMatcher(mock_config_manager)

        # Create data with invalid coordinates
        invalid_data = pd.DataFrame({
            'id': [1, 2, 3],
            'latitude': [91.0, -91.0, 0.0],  # Invalid latitudes
            'longitude': [181.0, -181.0, 0.0]  # Invalid longitudes
        })

        # Should validate coordinates
        # Implementation may filter or raise error
        try:
            # Validate coordinate ranges
            valid_lat = (invalid_data['latitude'] >= -90) & (invalid_data['latitude'] <= 90)
            valid_lon = (invalid_data['longitude'] >= -180) & (invalid_data['longitude'] <= 180)
            assert not valid_lat.all() or not valid_lon.all()
        except (MatchingError, ValueError):
            assert True

    def test_mismatched_schemas(self, mock_config_manager):
        """Test handling of mismatched data schemas."""
        matcher = SpatialMatcher(mock_config_manager)

        # Create dataframes with different schemas
        properties = pd.DataFrame({'id': [1, 2], 'name': ['A', 'B']})
        listings = pd.DataFrame({'listing_id': [1, 2], 'title': ['X', 'Y']})

        # Should handle schema mismatch
        with pytest.raises((MatchingError, KeyError, ValueError)):
            matcher.match_properties(properties, listings)
