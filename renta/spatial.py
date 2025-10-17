"""
Spatial matching and enrichment engine for RENTA library.

Provides efficient spatial matching between properties and Airbnb listings
using haversine distance calculations and BallTree indexing for performance.
"""

import logging
from typing import Dict, List, Optional, Tuple, Any
import numpy as np
import pandas as pd
from sklearn.neighbors import BallTree

from .config import ConfigManager
from .exceptions import MatchingError
from .interfaces import MatchingStrategy


logger = logging.getLogger(__name__)


class SpatialMatcher:
    """Matches properties with nearby Airbnb listings using spatial algorithms.

    Uses BallTree-based spatial indexing for efficient nearest neighbor queries
    with configurable radius and filtering criteria. Supports vectorized operations
    for handling large datasets.
    """

    def __init__(self, config: ConfigManager):
        """Initialize SpatialMatcher with configuration.

        Args:
            config: ConfigManager instance with matching configuration
        """
        self.config = config
        self._ball_tree: Optional[BallTree] = None
        self._airbnb_data: Optional[pd.DataFrame] = None

        # Cache configuration values
        self.radius_km = config.get("airbnb.matching.radius_km", 0.3)
        self.min_nights_threshold = config.get("airbnb.matching.min_nights_threshold", 7)
        self.min_review_score = config.get("airbnb.matching.min_review_score", 4.0)

        logger.info(
            "SpatialMatcher initialized",
            extra={
                "radius_km": self.radius_km,
                "min_nights_threshold": self.min_nights_threshold,
                "min_review_score": self.min_review_score,
            },
        )

    def match_properties(
        self, properties: pd.DataFrame, airbnb_listings: pd.DataFrame
    ) -> pd.DataFrame:
        """Find nearby Airbnb listings for each property.

        Args:
            properties: DataFrame with columns ['id', 'latitude', 'longitude', ...]
            airbnb_listings: DataFrame with Airbnb listing data

        Returns:
            DataFrame with matched property-Airbnb pairs including distances

        Raises:
            MatchingError: If matching fails due to data issues or configuration
        """
        try:
            logger.info(
                "Starting spatial matching",
                extra={"properties_count": len(properties), "airbnb_count": len(airbnb_listings)},
            )

            # Validate input data
            self._validate_input_data(properties, airbnb_listings)

            # Apply filters to Airbnb listings
            filtered_airbnb = self.apply_filters(airbnb_listings)

            if len(filtered_airbnb) == 0:
                logger.warning("No Airbnb listings remain after filtering")
                return pd.DataFrame()

            # Build spatial index if needed or data changed
            if (
                self._ball_tree is None
                or self._airbnb_data is None
                or not filtered_airbnb.equals(self._airbnb_data)
            ):
                self._build_spatial_index(filtered_airbnb)

            # Perform vectorized spatial matching
            matches = self._match_properties_vectorized(properties, filtered_airbnb)

            logger.info(
                "Spatial matching completed",
                extra={
                    "matches_found": len(matches),
                    "properties_with_matches": matches["property_id"].nunique()
                    if len(matches) > 0
                    else 0,
                },
            )

            return matches

        except Exception as e:
            logger.error(f"Spatial matching failed: {e}")
            raise MatchingError(f"Failed to match properties with Airbnb listings: {e}") from e

    def calculate_distances(
        self, properties: pd.DataFrame, airbnb_listings: pd.DataFrame
    ) -> np.ndarray:
        """Calculate haversine distances between properties and listings.

        Args:
            properties: DataFrame with property coordinates
            airbnb_listings: DataFrame with Airbnb coordinates

        Returns:
            2D numpy array with distances in kilometers [properties x airbnb_listings]
        """
        try:
            # Convert coordinates to radians
            prop_coords_rad = np.deg2rad(properties[["latitude", "longitude"]].values)
            airbnb_coords_rad = np.deg2rad(airbnb_listings[["latitude", "longitude"]].values)

            # Calculate distances using vectorized haversine formula
            distances = self._haversine_vectorized(
                prop_coords_rad[:, np.newaxis, :], airbnb_coords_rad[np.newaxis, :, :]
            )

            return distances

        except Exception as e:
            raise MatchingError(f"Failed to calculate distances: {e}") from e

    def apply_filters(self, airbnb_listings: pd.DataFrame) -> pd.DataFrame:
        """Apply temporal and quality filters to Airbnb matches.

        Args:
            airbnb_listings: Raw Airbnb listings DataFrame

        Returns:
            Filtered DataFrame meeting quality criteria
        """
        try:
            filtered = airbnb_listings.copy()
            initial_count = len(filtered)

            # Filter by minimum nights threshold
            if "minimum_nights" in filtered.columns:
                filtered = filtered[
                    (filtered["minimum_nights"].isna())
                    | (filtered["minimum_nights"] <= self.min_nights_threshold)
                ]
                logger.debug(f"After min nights filter: {len(filtered)}/{initial_count}")

            # Filter by review score
            if "review_scores_rating" in filtered.columns:
                filtered = filtered[
                    (filtered["review_scores_rating"].isna())
                    | (filtered["review_scores_rating"] >= self.min_review_score)
                ]
                logger.debug(f"After review score filter: {len(filtered)}/{initial_count}")

            # Filter out listings without coordinates
            filtered = filtered.dropna(subset=["latitude", "longitude"])
            logger.debug(f"After coordinate filter: {len(filtered)}/{initial_count}")

            # Filter out listings without price
            if "price" in filtered.columns:
                filtered = filtered[filtered["price"].notna() & (filtered["price"] > 0)]
                logger.debug(f"After price filter: {len(filtered)}/{initial_count}")

            logger.info(
                "Applied Airbnb filters",
                extra={
                    "initial_count": initial_count,
                    "filtered_count": len(filtered),
                    "filtered_out": initial_count - len(filtered),
                },
            )

            return filtered

        except Exception as e:
            raise MatchingError(f"Failed to apply filters: {e}") from e

    def _validate_input_data(self, properties: pd.DataFrame, airbnb_listings: pd.DataFrame) -> None:
        """Validate input DataFrames have required columns and data.

        Args:
            properties: Properties DataFrame to validate
            airbnb_listings: Airbnb listings DataFrame to validate

        Raises:
            MatchingError: If required columns are missing or data is invalid
        """
        # Check properties DataFrame
        required_prop_cols = ["id", "latitude", "longitude"]
        missing_prop_cols = [col for col in required_prop_cols if col not in properties.columns]
        if missing_prop_cols:
            raise MatchingError(
                f"Properties DataFrame missing required columns: {missing_prop_cols}"
            )

        # Check for valid coordinates in properties
        prop_coord_mask = (
            properties["latitude"].notna()
            & properties["longitude"].notna()
            & (properties["latitude"].between(-90, 90))
            & (properties["longitude"].between(-180, 180))
        )
        if not prop_coord_mask.any():
            raise MatchingError("No properties have valid coordinates")

        # Check Airbnb DataFrame
        required_airbnb_cols = ["id", "latitude", "longitude"]
        missing_airbnb_cols = [
            col for col in required_airbnb_cols if col not in airbnb_listings.columns
        ]
        if missing_airbnb_cols:
            raise MatchingError(f"Airbnb DataFrame missing required columns: {missing_airbnb_cols}")

        # Check for valid coordinates in Airbnb listings
        airbnb_coord_mask = (
            airbnb_listings["latitude"].notna()
            & airbnb_listings["longitude"].notna()
            & (airbnb_listings["latitude"].between(-90, 90))
            & (airbnb_listings["longitude"].between(-180, 180))
        )
        if not airbnb_coord_mask.any():
            raise MatchingError("No Airbnb listings have valid coordinates")

    def _build_spatial_index(self, airbnb_listings: pd.DataFrame) -> None:
        """Build BallTree spatial index for efficient nearest neighbor queries.

        Args:
            airbnb_listings: Filtered Airbnb listings to index
        """
        try:
            # Convert coordinates to radians for haversine metric
            coords_rad = np.deg2rad(airbnb_listings[["latitude", "longitude"]].values)

            # Build BallTree with haversine metric
            self._ball_tree = BallTree(coords_rad, metric="haversine")
            self._airbnb_data = airbnb_listings.copy()

            logger.debug("Built spatial index", extra={"indexed_listings": len(airbnb_listings)})

        except Exception as e:
            raise MatchingError(f"Failed to build spatial index: {e}") from e

    def _match_properties_vectorized(
        self, properties: pd.DataFrame, airbnb_listings: pd.DataFrame
    ) -> pd.DataFrame:
        """Perform vectorized spatial matching for improved performance.

        Args:
            properties: Properties to match
            airbnb_listings: Filtered Airbnb listings

        Returns:
            DataFrame with property-Airbnb matches and distances
        """
        try:
            # Convert radius to radians (Earth radius = 6371 km)
            radius_rad = self.radius_km / 6371.0

            # Get property coordinates in radians
            property_coords_rad = np.deg2rad(properties[["latitude", "longitude"]].values)

            # Query BallTree for all properties at once
            indices_list = self._ball_tree.query_radius(property_coords_rad, r=radius_rad)

            # Build matches DataFrame
            matches = []
            for prop_idx, airbnb_indices in enumerate(indices_list):
                if len(airbnb_indices) > 0:
                    # Get property info
                    property_row = properties.iloc[prop_idx]

                    # Get matching Airbnb listings
                    matched_airbnb = airbnb_listings.iloc[airbnb_indices].copy()

                    # Calculate exact distances for matches
                    prop_coord = property_coords_rad[prop_idx : prop_idx + 1]
                    airbnb_coords = np.deg2rad(matched_airbnb[["latitude", "longitude"]].values)
                    distances_km = self._haversine_vectorized(prop_coord, airbnb_coords).flatten()

                    # Add property and distance info to matches
                    matched_airbnb["property_id"] = property_row["id"]
                    matched_airbnb["distance_km"] = distances_km

                    # Add property coordinates for reference
                    matched_airbnb["property_latitude"] = property_row["latitude"]
                    matched_airbnb["property_longitude"] = property_row["longitude"]

                    matches.append(matched_airbnb)

            # Combine all matches
            if matches:
                result = pd.concat(matches, ignore_index=True)
                # Sort by property_id and distance for consistent ordering
                result = result.sort_values(["property_id", "distance_km"])
                return result
            else:
                return pd.DataFrame()

        except Exception as e:
            raise MatchingError(f"Vectorized matching failed: {e}") from e

    @staticmethod
    def _haversine_vectorized(coords1: np.ndarray, coords2: np.ndarray) -> np.ndarray:
        """Calculate haversine distances between coordinate arrays.

        Args:
            coords1: Array of coordinates in radians [n, 2] or [n, 1, 2]
            coords2: Array of coordinates in radians [m, 2] or [1, m, 2]

        Returns:
            Distance matrix in kilometers [n, m]
        """
        # Extract lat/lon
        lat1, lon1 = coords1[..., 0], coords1[..., 1]
        lat2, lon2 = coords2[..., 0], coords2[..., 1]

        # Haversine formula
        dlat = lat2 - lat1
        dlon = lon2 - lon1

        a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
        c = 2 * np.arcsin(np.sqrt(a))

        # Earth radius in kilometers
        return 6371.0 * c


class DefaultMatchingStrategy(MatchingStrategy):
    """Default matching strategy using spatial proximity and configurable filters.

    Implements the MatchingStrategy interface with spatial matching based on
    haversine distance and quality filters.
    """

    def __init__(self, config: ConfigManager):
        """Initialize with configuration.

        Args:
            config: ConfigManager instance
        """
        self.config = config
        self.spatial_matcher = SpatialMatcher(config)

    def match_properties(
        self, properties: pd.DataFrame, airbnb_listings: pd.DataFrame, config: Dict[str, Any]
    ) -> pd.DataFrame:
        """Match properties with Airbnb listings using spatial proximity.

        Args:
            properties: DataFrame of property listings
            airbnb_listings: DataFrame of Airbnb listings
            config: Configuration dictionary (merged with instance config)

        Returns:
            DataFrame with matched property-Airbnb pairs
        """
        # Update spatial matcher config if provided
        if config:
            for key, value in config.items():
                if hasattr(self.spatial_matcher, key):
                    setattr(self.spatial_matcher, key, value)

        return self.spatial_matcher.match_properties(properties, airbnb_listings)

    def calculate_match_score(self, property_row: pd.Series, airbnb_row: pd.Series) -> float:
        """Calculate match score based on distance and quality metrics.

        Args:
            property_row: Single property record
            airbnb_row: Single Airbnb listing record

        Returns:
            Match score (higher = better match)
        """
        try:
            # Base score from inverse distance (closer = higher score)
            if "distance_km" in airbnb_row:
                distance_score = 1.0 / (1.0 + airbnb_row["distance_km"])
            else:
                # Calculate distance if not provided
                prop_coords = np.array([[property_row["latitude"], property_row["longitude"]]])
                airbnb_coords = np.array([[airbnb_row["latitude"], airbnb_row["longitude"]]])
                distance_km = SpatialMatcher._haversine_vectorized(
                    np.deg2rad(prop_coords), np.deg2rad(airbnb_coords)
                )[0, 0]
                distance_score = 1.0 / (1.0 + distance_km)

            # Quality score from reviews
            quality_score = 1.0
            if "review_scores_rating" in airbnb_row and pd.notna(
                airbnb_row["review_scores_rating"]
            ):
                quality_score = airbnb_row["review_scores_rating"] / 5.0  # Normalize to 0-1

            # Price availability score (prefer listings with price data)
            price_score = 1.0 if "price" in airbnb_row and pd.notna(airbnb_row["price"]) else 0.5

            # Combine scores with weights
            total_score = (
                0.5 * distance_score
                + 0.3 * quality_score  # Distance is most important
                + 0.2 * price_score  # Quality matters  # Price data availability
            )

            return total_score

        except Exception as e:
            logger.warning(f"Failed to calculate match score: {e}")
            return 0.0


class EnrichmentEngine:
    """Enriches properties with aggregated Airbnb metrics.

    Processes matched property-Airbnb pairs to calculate rental metrics,
    occupancy probability estimation, and match status tracking.
    """

    def __init__(self, config: ConfigManager):
        """Initialize EnrichmentEngine with configuration.

        Args:
            config: ConfigManager instance with enrichment configuration
        """
        self.config = config

        # Cache occupancy thresholds
        self.occupancy_thresholds = {
            "high": config.get("airbnb.matching.occupancy_thresholds.high", 14),
            "medium": config.get("airbnb.matching.occupancy_thresholds.medium", 7),
        }

        logger.info(
            "EnrichmentEngine initialized",
            extra={"occupancy_thresholds": self.occupancy_thresholds},
        )

    def enrich_properties(self, properties: pd.DataFrame, matches: pd.DataFrame) -> pd.DataFrame:
        """Add Airbnb metrics to properties.

        Args:
            properties: Original properties DataFrame
            matches: Matched property-Airbnb pairs from SpatialMatcher

        Returns:
            Properties DataFrame enriched with Airbnb metrics
        """
        try:
            logger.info(
                "Starting property enrichment",
                extra={"properties_count": len(properties), "matches_count": len(matches)},
            )

            # Start with copy of original properties
            enriched = properties.copy()

            # Initialize enrichment columns with null values
            enrichment_columns = [
                "airbnb_avg_price_entire_home",
                "airbnb_avg_price_private_room",
                "airbnb_occupancy_probability",
                "airbnb_avg_review_score",
                "airbnb_match_count",
                "airbnb_closest_distance_km",
                "match_status",
            ]

            for col in enrichment_columns:
                enriched[col] = None

            # Set default match status
            enriched["match_status"] = "no_matches"

            if len(matches) == 0:
                logger.warning("No matches provided for enrichment")
                return enriched

            # Group matches by property_id and calculate metrics
            for property_id, property_matches in matches.groupby("property_id"):
                try:
                    # Find property index
                    prop_mask = enriched["id"] == property_id
                    if not prop_mask.any():
                        logger.warning(f"Property {property_id} not found in properties DataFrame")
                        continue

                    prop_idx = enriched[prop_mask].index[0]

                    # Calculate rental metrics for this property
                    metrics = self.calculate_rental_metrics(property_matches)

                    # Update enriched DataFrame
                    for metric_name, value in metrics.items():
                        enriched.loc[prop_idx, metric_name] = value

                    # Set match status to indicate successful matching
                    enriched.loc[prop_idx, "match_status"] = "matched"

                except Exception as e:
                    logger.error(f"Failed to enrich property {property_id}: {e}")
                    # Keep default null values and no_matches status
                    continue

            # Log enrichment summary
            matched_count = (enriched["match_status"] == "matched").sum()
            logger.info(
                "Property enrichment completed",
                extra={
                    "properties_enriched": matched_count,
                    "properties_without_matches": len(enriched) - matched_count,
                },
            )

            return enriched

        except Exception as e:
            logger.error(f"Property enrichment failed: {e}")
            raise MatchingError(f"Failed to enrich properties: {e}") from e

    def calculate_rental_metrics(self, airbnb_group: pd.DataFrame) -> Dict[str, Any]:
        """Calculate aggregated rental metrics for a property.

        Args:
            airbnb_group: DataFrame of Airbnb listings matched to a single property

        Returns:
            Dictionary of calculated metrics
        """
        try:
            metrics = {}

            # Basic match statistics
            metrics["airbnb_match_count"] = len(airbnb_group)

            # Closest distance
            if "distance_km" in airbnb_group.columns:
                metrics["airbnb_closest_distance_km"] = airbnb_group["distance_km"].min()

            # Price metrics by room type
            if "price" in airbnb_group.columns and "room_type" in airbnb_group.columns:
                # Filter out invalid prices
                valid_price_mask = airbnb_group["price"].notna() & (airbnb_group["price"] > 0)
                price_data = airbnb_group[valid_price_mask]

                if len(price_data) > 0:
                    # Average price for entire homes/apartments
                    entire_homes = price_data[
                        price_data["room_type"].str.contains("Entire", case=False, na=False)
                    ]
                    if len(entire_homes) > 0:
                        metrics["airbnb_avg_price_entire_home"] = entire_homes["price"].mean()

                    # Average price for private rooms
                    private_rooms = price_data[
                        price_data["room_type"].str.contains("Private", case=False, na=False)
                    ]
                    if len(private_rooms) > 0:
                        metrics["airbnb_avg_price_private_room"] = private_rooms["price"].mean()

            # Review score metrics
            if "review_scores_rating" in airbnb_group.columns:
                valid_reviews = airbnb_group["review_scores_rating"].dropna()
                if len(valid_reviews) > 0:
                    metrics["airbnb_avg_review_score"] = valid_reviews.mean()

            # Occupancy probability estimation
            metrics["airbnb_occupancy_probability"] = self.estimate_occupancy(airbnb_group)

            return metrics

        except Exception as e:
            logger.error(f"Failed to calculate rental metrics: {e}")
            return {
                "airbnb_match_count": len(airbnb_group),
                "airbnb_occupancy_probability": "unknown",
            }

    def estimate_occupancy(self, airbnb_group: pd.DataFrame) -> str:
        """Estimate rental occupancy probability.

        Args:
            airbnb_group: DataFrame of Airbnb listings for a property

        Returns:
            Occupancy probability category: 'high', 'medium', 'low', or 'unknown'
        """
        try:
            # Method 1: Use availability data if present
            if "availability_30" in airbnb_group.columns:
                # Calculate average nights booked (30 - available)
                valid_availability = airbnb_group["availability_30"].dropna()
                if len(valid_availability) > 0:
                    avg_nights_booked = (30 - valid_availability).mean()
                    return self._categorize_occupancy(avg_nights_booked)

            # Method 2: Use calculated_host_listings_count and reviews as proxy
            if (
                "calculated_host_listings_count" in airbnb_group.columns
                and "number_of_reviews" in airbnb_group.columns
            ):
                # Properties with fewer host listings and more reviews tend to be more occupied
                avg_host_listings = airbnb_group["calculated_host_listings_count"].mean()
                avg_reviews = airbnb_group["number_of_reviews"].mean()

                # Heuristic: fewer host listings + more reviews = higher occupancy
                if avg_host_listings <= 2 and avg_reviews >= 10:
                    return "high"
                elif avg_host_listings <= 5 and avg_reviews >= 5:
                    return "medium"
                else:
                    return "low"

            # Method 3: Use review frequency as proxy
            if (
                "number_of_reviews" in airbnb_group.columns
                and "last_review" in airbnb_group.columns
            ):
                # More recent and frequent reviews suggest higher occupancy
                avg_reviews = airbnb_group["number_of_reviews"].mean()

                if avg_reviews >= 20:
                    return "high"
                elif avg_reviews >= 5:
                    return "medium"
                else:
                    return "low"

            # Method 4: Use minimum nights as indicator
            if "minimum_nights" in airbnb_group.columns:
                avg_min_nights = airbnb_group["minimum_nights"].mean()

                # Shorter minimum stays often indicate higher turnover/occupancy
                if avg_min_nights <= 3:
                    return "medium"
                else:
                    return "low"

            # Fallback: unknown if no suitable data
            return "unknown"

        except Exception as e:
            logger.warning(f"Failed to estimate occupancy: {e}")
            return "unknown"

    def _categorize_occupancy(self, nights_booked: float) -> str:
        """Categorize occupancy based on nights booked per month.

        Args:
            nights_booked: Average nights booked per month

        Returns:
            Occupancy category: 'high', 'medium', or 'low'
        """
        if nights_booked >= self.occupancy_thresholds["high"]:
            return "high"
        elif nights_booked >= self.occupancy_thresholds["medium"]:
            return "medium"
        else:
            return "low"


class MatchingStrategyRegistry:
    """Registry for pluggable matching strategies.

    Allows registration and retrieval of custom matching strategies
    that implement the MatchingStrategy interface.
    """

    def __init__(self):
        """Initialize registry with default strategy."""
        self._strategies: Dict[str, MatchingStrategy] = {}
        self._default_strategy_name = "default"

    def register_strategy(self, name: str, strategy: MatchingStrategy) -> None:
        """Register a matching strategy.

        Args:
            name: Strategy name/identifier
            strategy: MatchingStrategy implementation

        Raises:
            ValueError: If strategy doesn't implement MatchingStrategy interface
        """
        if not isinstance(strategy, MatchingStrategy):
            raise ValueError(f"Strategy must implement MatchingStrategy interface")

        self._strategies[name] = strategy
        logger.info(f"Registered matching strategy: {name}")

    def get_strategy(self, name: str) -> MatchingStrategy:
        """Get matching strategy by name.

        Args:
            name: Strategy name

        Returns:
            MatchingStrategy implementation

        Raises:
            KeyError: If strategy not found
        """
        if name not in self._strategies:
            raise KeyError(
                f"Matching strategy '{name}' not found. Available: {list(self._strategies.keys())}"
            )

        return self._strategies[name]

    def list_strategies(self) -> List[str]:
        """List all registered strategy names.

        Returns:
            List of strategy names
        """
        return list(self._strategies.keys())

    def set_default_strategy(self, name: str) -> None:
        """Set default strategy name.

        Args:
            name: Strategy name to use as default

        Raises:
            KeyError: If strategy not found
        """
        if name not in self._strategies:
            raise KeyError(f"Strategy '{name}' not found")

        self._default_strategy_name = name
        logger.info(f"Set default matching strategy: {name}")

    def get_default_strategy(self) -> MatchingStrategy:
        """Get default matching strategy.

        Returns:
            Default MatchingStrategy implementation
        """
        return self.get_strategy(self._default_strategy_name)


# Global registry instance
_strategy_registry = MatchingStrategyRegistry()


def register_matching_strategy(name: str, strategy: MatchingStrategy) -> None:
    """Register a matching strategy globally.

    Args:
        name: Strategy name
        strategy: MatchingStrategy implementation
    """
    _strategy_registry.register_strategy(name, strategy)


def get_matching_strategy(name: str) -> MatchingStrategy:
    """Get matching strategy by name.

    Args:
        name: Strategy name

    Returns:
        MatchingStrategy implementation
    """
    return _strategy_registry.get_strategy(name)


def list_matching_strategies() -> List[str]:
    """List all available matching strategies.

    Returns:
        List of strategy names
    """
    return _strategy_registry.list_strategies()


def get_default_matching_strategy() -> MatchingStrategy:
    """Get default matching strategy.

    Returns:
        Default MatchingStrategy implementation
    """
    return _strategy_registry.get_default_strategy()


def initialize_default_strategies(config: ConfigManager) -> None:
    """Initialize default matching strategies in the registry.

    Args:
        config: ConfigManager instance for strategy initialization
    """
    try:
        # Register default spatial matching strategy
        default_strategy = DefaultMatchingStrategy(config)
        _strategy_registry.register_strategy("default", default_strategy)
        _strategy_registry.register_strategy("spatial", default_strategy)
        _strategy_registry.set_default_strategy("default")

        logger.info("Initialized default matching strategies")

    except Exception as e:
        logger.error(f"Failed to initialize default strategies: {e}")
        raise MatchingError(f"Failed to initialize matching strategies: {e}") from e


# Initialize with a placeholder - will be properly initialized when config is available
try:
    from .config import ConfigManager

    # Create minimal config for initialization
    _temp_config = ConfigManager.__new__(ConfigManager)
    _temp_config._config = {
        "airbnb": {
            "matching": {
                "radius_km": 0.3,
                "min_nights_threshold": 7,
                "min_review_score": 4.0,
                "occupancy_thresholds": {"high": 14, "medium": 7},
            }
        }
    }
    _temp_config.get = lambda key, default=None: _temp_config._config.get(key, default)

    # Initialize with temporary config
    initialize_default_strategies(_temp_config)

except Exception as e:
    # If initialization fails, log but don't crash
    logger.warning(f"Could not initialize default strategies at import time: {e}")
