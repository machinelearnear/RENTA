# Spatial Analysis

The spatial analysis module handles geospatial matching between properties and Airbnb listings.

## SpatialMatcher

::: renta.spatial.SpatialMatcher
    options:
      show_root_heading: true
      show_source: true
      heading_level: 3

### Usage Examples

```python
from renta.spatial import SpatialMatcher
from renta.config import ConfigManager
import pandas as pd

config = ConfigManager()
matcher = SpatialMatcher(config)

# Load data
properties = pd.read_csv("properties.csv")
airbnb_listings = pd.read_csv("airbnb_listings.csv")

# Perform spatial matching
matches = matcher.match_properties(properties, airbnb_listings)
print(f"Found {len(matches)} property-Airbnb matches")

# Calculate distances manually
distances = matcher.calculate_distances(properties, airbnb_listings)
print(f"Distance matrix shape: {distances.shape}")
```

## EnrichmentEngine

::: renta.spatial.EnrichmentEngine
    options:
      show_root_heading: true
      show_source: true
      heading_level: 3

### Usage Examples

```python
from renta.spatial import EnrichmentEngine
from renta.config import ConfigManager

config = ConfigManager()
engine = EnrichmentEngine(config)

# Enrich properties with Airbnb metrics
enriched_properties = engine.enrich_properties(properties, matches)

# Calculate metrics for a specific property
property_matches = matches[matches['property_id'] == 'prop_123']
metrics = engine.calculate_rental_metrics(property_matches)
print(f"Average nightly rate: ${metrics['avg_price_usd']:.2f}")

# Estimate occupancy
occupancy = engine.estimate_occupancy(property_matches)
print(f"Occupancy probability: {occupancy}")
```

## Matching Strategies

RENTA supports pluggable matching strategies for custom spatial logic.

### Built-in Strategies

```python
from renta.spatial import SpatialMatchingStrategy

# Default spatial strategy (haversine distance)
strategy = SpatialMatchingStrategy(config)
matches = strategy.match_properties(properties, airbnb_listings)
```

### Custom Matching Strategy

```python
from renta.spatial import SpatialMatchingStrategy
import numpy as np

class CustomMatchingStrategy(SpatialMatchingStrategy):
    """Custom matching strategy with additional filters."""
    
    def match_properties(self, properties, airbnb_listings):
        # Call parent method for basic spatial matching
        matches = super().match_properties(properties, airbnb_listings)
        
        # Apply custom filters
        # Example: Only match properties with similar room counts
        filtered_matches = []
        
        for _, match in matches.iterrows():
            prop_rooms = match.get('property_rooms', 0)
            airbnb_beds = match.get('airbnb_beds', 0)
            
            # Allow ±1 room difference
            if abs(prop_rooms - airbnb_beds) <= 1:
                filtered_matches.append(match)
        
        return pd.DataFrame(filtered_matches)
    
    def calculate_similarity_score(self, property_row, airbnb_row):
        """Calculate custom similarity score."""
        # Distance component (0-1, lower is better)
        distance_km = self.haversine_distance(
            property_row['latitude'], property_row['longitude'],
            airbnb_row['latitude'], airbnb_row['longitude']
        )
        distance_score = min(distance_km / self.config.get('airbnb.matching.radius_km', 0.3), 1.0)
        
        # Room similarity component (0-1, higher is better)
        prop_rooms = property_row.get('rooms', 0)
        airbnb_beds = airbnb_row.get('beds', 0)
        room_diff = abs(prop_rooms - airbnb_beds)
        room_score = max(0, 1 - (room_diff / 3))  # Penalize room differences
        
        # Combined score (higher is better)
        return (1 - distance_score) * 0.7 + room_score * 0.3

# Register and use custom strategy
matcher = SpatialMatcher(config)
matcher.register_strategy("custom", CustomMatchingStrategy)
matcher.set_strategy("custom")
```

## Spatial Algorithms

### Haversine Distance

The haversine formula calculates great-circle distances between points on Earth:

```python
import math

def haversine_distance(lat1, lon1, lat2, lon2):
    """Calculate haversine distance between two points in kilometers."""
    # Convert to radians
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    
    # Haversine formula
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    
    # Earth's radius in kilometers
    r = 6371
    
    return c * r

# Example usage
distance = haversine_distance(-34.6037, -58.3816, -34.6118, -58.3960)
print(f"Distance: {distance:.3f} km")
```

### Spatial Indexing

For performance with large datasets, RENTA uses BallTree spatial indexing:

```python
from sklearn.neighbors import BallTree
import numpy as np

# Build spatial index for Airbnb listings
airbnb_coords = np.deg2rad(airbnb_listings[['latitude', 'longitude']].values)
tree = BallTree(airbnb_coords, metric='haversine')

# Query for properties within radius
property_coords = np.deg2rad(properties[['latitude', 'longitude']].values)
radius_km = 0.3
radius_rad = radius_km / 6371  # Earth's radius

# Find all Airbnb listings within radius of each property
indices_list = tree.query_radius(property_coords, r=radius_rad)

for i, indices in enumerate(indices_list):
    property_id = properties.iloc[i]['id']
    nearby_airbnbs = airbnb_listings.iloc[indices]
    print(f"Property {property_id}: {len(nearby_airbnbs)} nearby Airbnbs")
```

## Enrichment Metrics

### Rental Metrics

The enrichment engine calculates various rental metrics:

```python
# Example enriched property data
enriched_property = {
    'id': 'prop_123',
    'title': '2 ambientes en Palermo',
    'price_usd': 95000,
    
    # Airbnb enrichment metrics
    'airbnb_avg_price_entire_home': 85.50,      # Average nightly rate for entire homes
    'airbnb_avg_price_private_room': 45.20,     # Average nightly rate for private rooms
    'airbnb_occupancy_probability': 'high',      # Estimated occupancy level
    'airbnb_avg_review_score': 4.7,             # Average review score
    'airbnb_match_count': 12,                   # Number of nearby Airbnb listings
    'airbnb_avg_distance_km': 0.15,             # Average distance to matches
    'match_status': 'matched'                   # Match status
}
```

### Occupancy Estimation

Occupancy probability is estimated based on review frequency and availability:

```python
def estimate_occupancy_probability(airbnb_group):
    """Estimate occupancy probability from Airbnb data."""
    # Calculate average nights booked per month based on reviews
    avg_reviews_per_month = airbnb_group['reviews_per_month'].mean()
    
    # Assume 1 review per 3 bookings (industry estimate)
    estimated_bookings_per_month = avg_reviews_per_month * 3
    
    # Classify occupancy
    if estimated_bookings_per_month >= 14:
        return 'high'
    elif estimated_bookings_per_month >= 7:
        return 'medium'
    else:
        return 'low'
```

## Configuration Options

### Spatial Matching Configuration

```yaml
airbnb:
  matching:
    radius_km: 0.3                    # Search radius in kilometers
    min_nights_threshold: 7           # Minimum nights filter
    min_review_score: 4.0            # Minimum review score filter
    occupancy_thresholds:
      high: 14                       # Nights per month for high occupancy
      medium: 7                      # Nights per month for medium occupancy
    max_matches_per_property: 50     # Limit matches per property
    
spatial:
  indexing:
    algorithm: "ball_tree"           # Spatial indexing algorithm
    leaf_size: 30                    # BallTree leaf size
    metric: "haversine"              # Distance metric
    
performance:
  batch_size: 1000                   # Batch size for processing
  parallel_processing: true          # Enable parallel processing
  max_workers: 4                     # Number of worker threads
```

## Performance Optimization

### Vectorized Operations

```python
import numpy as np
import pandas as pd

def vectorized_haversine(lat1, lon1, lat2, lon2):
    """Vectorized haversine distance calculation."""
    # Convert to radians
    lat1, lon1, lat2, lon2 = np.radians([lat1, lon1, lat2, lon2])
    
    # Vectorized haversine formula
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat/2)**2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon/2)**2
    c = 2 * np.arcsin(np.sqrt(a))
    
    return c * 6371  # Earth's radius in km

# Example: Calculate distances between all properties and all Airbnb listings
prop_lats = properties['latitude'].values[:, np.newaxis]
prop_lons = properties['longitude'].values[:, np.newaxis]
airbnb_lats = airbnb_listings['latitude'].values
airbnb_lons = airbnb_listings['longitude'].values

distances = vectorized_haversine(prop_lats, prop_lons, airbnb_lats, airbnb_lons)
print(f"Distance matrix shape: {distances.shape}")
```

### Memory-Efficient Processing

```python
def process_properties_in_batches(properties, airbnb_listings, batch_size=100):
    """Process properties in batches to manage memory usage."""
    all_matches = []
    
    for i in range(0, len(properties), batch_size):
        batch = properties.iloc[i:i+batch_size]
        
        # Process batch
        batch_matches = matcher.match_properties(batch, airbnb_listings)
        all_matches.append(batch_matches)
        
        print(f"Processed batch {i//batch_size + 1}/{len(properties)//batch_size + 1}")
    
    return pd.concat(all_matches, ignore_index=True)

# Use for large datasets
matches = process_properties_in_batches(properties, airbnb_listings)
```

## Error Handling

```python
from renta.exceptions import MatchingError

try:
    matches = matcher.match_properties(properties, airbnb_listings)
except MatchingError as e:
    print(f"Spatial matching failed: {e}")
    
    # Fallback: use larger radius
    config.set('airbnb.matching.radius_km', 0.5)
    matches = matcher.match_properties(properties, airbnb_listings)
```

## Validation

```python
def validate_spatial_data(df, coord_columns=['latitude', 'longitude']):
    """Validate spatial data quality."""
    issues = []
    
    for col in coord_columns:
        if col not in df.columns:
            issues.append(f"Missing column: {col}")
            continue
            
        # Check for missing values
        missing = df[col].isna().sum()
        if missing > 0:
            issues.append(f"{col}: {missing} missing values")
        
        # Check coordinate ranges
        if col == 'latitude':
            invalid = df[(df[col] < -90) | (df[col] > 90)].shape[0]
            if invalid > 0:
                issues.append(f"{col}: {invalid} invalid values (outside ±90)")
        
        elif col == 'longitude':
            invalid = df[(df[col] < -180) | (df[col] > 180)].shape[0]
            if invalid > 0:
                issues.append(f"{col}: {invalid} invalid values (outside ±180)")
    
    return issues

# Validate data before matching
prop_issues = validate_spatial_data(properties)
airbnb_issues = validate_spatial_data(airbnb_listings)

if prop_issues or airbnb_issues:
    print("Data validation issues found:")
    for issue in prop_issues + airbnb_issues:
        print(f"  - {issue}")
```