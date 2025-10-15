# Export Management

The export module handles data export in multiple formats with comprehensive error handling.

## ExportManager

::: renta.export.ExportManager
    options:
      show_root_heading: true
      show_source: true
      heading_level: 3

### Usage Examples

```python
from renta.export import ExportManager
from renta.config import ConfigManager
import pandas as pd

config = ConfigManager()
export_manager = ExportManager(config)

# Export as DataFrame (in-memory)
df_result = export_manager.export(enriched_properties, format="dataframe")

# Export as CSV file
csv_path = export_manager.export(
    enriched_properties, 
    format="csv", 
    path="investment_analysis.csv"
)

# Export as JSON file
json_path = export_manager.export(
    enriched_properties,
    format="json",
    path="investment_analysis.json"
)

# Auto-generate filename
auto_path = export_manager.export(enriched_properties, format="csv")
print(f"Exported to: {auto_path}")
```

## Export Formats

### DataFrame Export

Returns the data as a pandas DataFrame (default format):

```python
# In-memory DataFrame
df = export_manager.export(data, format="dataframe")
print(f"Shape: {df.shape}")
print(f"Columns: {list(df.columns)}")

# DataFrame is a copy, safe to modify
df['custom_metric'] = df['price_usd'] / df['surface_m2']
```

### CSV Export

Exports data as comma-separated values:

```python
# Export to specific file
csv_path = export_manager.export(
    data, 
    format="csv", 
    path="analysis_results.csv"
)

# Export with auto-generated filename
csv_path = export_manager.export(data, format="csv")
# Creates file like: renta_export_20241016_143022.csv

# CSV includes all columns with proper encoding
# Handles special characters in Spanish text
```

### JSON Export

Exports data as JSON with proper formatting:

```python
# Export to file
json_path = export_manager.export(
    data,
    format="json", 
    path="analysis_results.json"
)

# Export to memory (returns dict)
json_data = export_manager.export(data, format="json")

# JSON structure
{
    "metadata": {
        "export_timestamp": "2024-10-16T14:30:22Z",
        "total_properties": 25,
        "renta_version": "0.1.0"
    },
    "properties": [
        {
            "id": "prop_123",
            "title": "2 ambientes en Palermo",
            "price_usd": 95000,
            "airbnb_avg_price_entire_home": 85.50,
            "summary": "Che, esta propiedad..."
        }
    ]
}
```

## Custom Exporters

### Creating Custom Exporters

```python
from renta.export import BaseExporter
import xml.etree.ElementTree as ET

class XMLExporter(BaseExporter):
    """Custom XML exporter."""
    
    def export_to_file(self, data: pd.DataFrame, path: str) -> str:
        """Export DataFrame to XML file."""
        root = ET.Element("properties")
        
        for _, row in data.iterrows():
            prop_elem = ET.SubElement(root, "property")
            prop_elem.set("id", str(row.get('id', '')))
            
            for column, value in row.items():
                if pd.notna(value):
                    elem = ET.SubElement(prop_elem, column.replace(' ', '_'))
                    elem.text = str(value)
        
        tree = ET.ElementTree(root)
        tree.write(path, encoding='utf-8', xml_declaration=True)
        return path
    
    def export_to_memory(self, data: pd.DataFrame) -> str:
        """Export DataFrame to XML string."""
        root = ET.Element("properties")
        
        for _, row in data.iterrows():
            prop_elem = ET.SubElement(root, "property")
            for column, value in row.items():
                if pd.notna(value):
                    elem = ET.SubElement(prop_elem, column.replace(' ', '_'))
                    elem.text = str(value)
        
        return ET.tostring(root, encoding='unicode')

# Register custom exporter
export_manager.register_exporter("xml", XMLExporter)

# Use custom exporter
xml_path = export_manager.export(data, format="xml", path="results.xml")
```

### Excel Exporter

```python
from renta.export import BaseExporter
import pandas as pd

class ExcelExporter(BaseExporter):
    """Excel exporter with multiple sheets."""
    
    def export_to_file(self, data: pd.DataFrame, path: str) -> str:
        """Export to Excel with multiple sheets."""
        with pd.ExcelWriter(path, engine='openpyxl') as writer:
            # Main data sheet
            data.to_excel(writer, sheet_name='Properties', index=False)
            
            # Summary statistics sheet
            summary_stats = self._calculate_summary_stats(data)
            summary_stats.to_excel(writer, sheet_name='Summary', index=True)
            
            # High-potential properties sheet
            high_potential = data[
                (data['airbnb_occupancy_probability'] == 'high') &
                (data['price_usd'] < data['price_usd'].median())
            ]
            high_potential.to_excel(writer, sheet_name='High_Potential', index=False)
        
        return path
    
    def _calculate_summary_stats(self, data: pd.DataFrame) -> pd.DataFrame:
        """Calculate summary statistics."""
        stats = {
            'Total Properties': len(data),
            'Average Price USD': data['price_usd'].mean(),
            'Median Price USD': data['price_usd'].median(),
            'Average Price per m²': (data['price_usd'] / data['surface_m2']).mean(),
            'Properties with Airbnb Matches': len(data[data['match_status'] == 'matched']),
            'Average Airbnb Price': data['airbnb_avg_price_entire_home'].mean(),
            'High Occupancy Properties': len(data[data['airbnb_occupancy_probability'] == 'high'])
        }
        
        return pd.DataFrame(list(stats.items()), columns=['Metric', 'Value'])

# Register and use
export_manager.register_exporter("excel", ExcelExporter)
excel_path = export_manager.export(data, format="excel", path="analysis.xlsx")
```

## File Management

### Collision-Safe Filenames

```python
# Auto-generated filenames include timestamp
filename = export_manager.generate_filename("csv")
# Returns: renta_export_20241016_143022.csv

# Custom prefix
filename = export_manager.generate_filename("json", prefix="palermo_analysis")
# Returns: palermo_analysis_20241016_143022.json

# Collision handling
export_manager.export(data, format="csv", path="results.csv")  # Creates results.csv
export_manager.export(data, format="csv", path="results.csv")  # Creates results_1.csv
export_manager.export(data, format="csv", path="results.csv")  # Creates results_2.csv
```

### Directory Management

```python
# Configure export directory
config = ConfigManager()
config.set('data.export_dir', '/path/to/exports')

# Export manager creates directories as needed
export_manager = ExportManager(config)
csv_path = export_manager.export(data, format="csv")
# Creates /path/to/exports/renta_export_20241016_143022.csv
```

### Cleanup on Failure

```python
# Partial files are cleaned up on failure
try:
    large_data = pd.DataFrame(...)  # Very large dataset
    export_manager.export(large_data, format="csv", path="huge_file.csv")
except ExportFormatError as e:
    # Partial file is automatically cleaned up
    print(f"Export failed: {e}")
```

## Data Formatting

### Column Ordering

```python
# Default column order for exports
EXPORT_COLUMN_ORDER = [
    # Property basics
    'id', 'title', 'address', 'price_usd', 'price_ars', 'surface_m2',
    'rooms', 'bathrooms', 'views_per_day',
    
    # Location
    'latitude', 'longitude',
    
    # Airbnb enrichment
    'airbnb_avg_price_entire_home', 'airbnb_avg_price_private_room',
    'airbnb_occupancy_probability', 'airbnb_avg_review_score',
    'airbnb_match_count', 'match_status',
    
    # AI analysis
    'summary', 'confidence',
    
    # URLs
    'listing_url'
]

# Custom column ordering
def reorder_columns(df, column_order):
    """Reorder DataFrame columns."""
    available_columns = [col for col in column_order if col in df.columns]
    remaining_columns = [col for col in df.columns if col not in column_order]
    return df[available_columns + remaining_columns]

# Apply custom ordering
ordered_data = reorder_columns(data, EXPORT_COLUMN_ORDER)
export_manager.export(ordered_data, format="csv")
```

### Data Cleaning for Export

```python
def clean_for_export(df):
    """Clean DataFrame for export."""
    df_clean = df.copy()
    
    # Round numeric columns
    numeric_columns = df_clean.select_dtypes(include=['float64']).columns
    df_clean[numeric_columns] = df_clean[numeric_columns].round(2)
    
    # Clean text columns
    text_columns = df_clean.select_dtypes(include=['object']).columns
    for col in text_columns:
        if col in df_clean.columns:
            # Remove extra whitespace
            df_clean[col] = df_clean[col].astype(str).str.strip()
            # Replace newlines in summaries
            if 'summary' in col:
                df_clean[col] = df_clean[col].str.replace('\n', ' ')
    
    # Format currency columns
    currency_columns = ['price_usd', 'price_ars', 'airbnb_avg_price_entire_home']
    for col in currency_columns:
        if col in df_clean.columns:
            df_clean[col] = df_clean[col].apply(
                lambda x: f"${x:,.2f}" if pd.notna(x) else ""
            )
    
    return df_clean

# Use cleaning
clean_data = clean_for_export(enriched_properties)
export_manager.export(clean_data, format="csv")
```

## Configuration Options

### Export Configuration

```yaml
data:
  export_dir: "~/.renta/exports"
  
export:
  formats:
    csv:
      encoding: "utf-8"
      separator: ","
      include_index: false
      date_format: "%Y-%m-%d"
    
    json:
      ensure_ascii: false
      indent: 2
      include_metadata: true
    
    excel:
      engine: "openpyxl"
      include_charts: false
  
  filename:
    prefix: "renta_export"
    timestamp_format: "%Y%m%d_%H%M%S"
    collision_handling: "increment"  # or "overwrite", "error"
  
  cleanup:
    remove_partial_files: true
    max_file_age_days: 30
```

## Error Handling

### Export Errors

```python
from renta.exceptions import ExportFormatError

try:
    result = export_manager.export(data, format="csv", path="results.csv")
    print(f"Export successful: {result}")
    
except ExportFormatError as e:
    print(f"Export failed: {e}")
    
    # Try alternative format
    try:
        result = export_manager.export(data, format="json")
        print(f"Fallback export successful: {result}")
    except ExportFormatError as fallback_error:
        print(f"All export attempts failed: {fallback_error}")

except PermissionError as e:
    print(f"Permission denied: {e}")
    print("Check file permissions and disk space")

except OSError as e:
    print(f"File system error: {e}")
    print("Check disk space and path validity")
```

### Validation

```python
def validate_export_data(df):
    """Validate data before export."""
    issues = []
    
    # Check for empty DataFrame
    if df.empty:
        issues.append("DataFrame is empty")
        return issues
    
    # Check for required columns
    required_columns = ['id', 'title', 'price_usd']
    missing_columns = [col for col in required_columns if col not in df.columns]
    if missing_columns:
        issues.append(f"Missing required columns: {missing_columns}")
    
    # Check for data quality issues
    if 'price_usd' in df.columns:
        invalid_prices = df[df['price_usd'] <= 0].shape[0]
        if invalid_prices > 0:
            issues.append(f"{invalid_prices} properties have invalid prices")
    
    # Check for encoding issues
    text_columns = df.select_dtypes(include=['object']).columns
    for col in text_columns:
        try:
            df[col].astype(str).str.encode('utf-8')
        except UnicodeEncodeError:
            issues.append(f"Encoding issues in column: {col}")
    
    return issues

# Validate before export
issues = validate_export_data(data)
if issues:
    print("Data validation issues:")
    for issue in issues:
        print(f"  - {issue}")
else:
    export_manager.export(data, format="csv")
```

## Performance Considerations

### Large Dataset Export

```python
def export_large_dataset(export_manager, data, chunk_size=1000):
    """Export large datasets in chunks."""
    if len(data) <= chunk_size:
        return export_manager.export(data, format="csv")
    
    # Export in chunks
    chunk_files = []
    for i in range(0, len(data), chunk_size):
        chunk = data.iloc[i:i+chunk_size]
        chunk_file = export_manager.export(
            chunk, 
            format="csv", 
            path=f"chunk_{i//chunk_size + 1}.csv"
        )
        chunk_files.append(chunk_file)
    
    # Combine chunks
    combined_file = "combined_export.csv"
    with open(combined_file, 'w', encoding='utf-8') as outfile:
        for i, chunk_file in enumerate(chunk_files):
            with open(chunk_file, 'r', encoding='utf-8') as infile:
                if i == 0:
                    # Include header from first file
                    outfile.write(infile.read())
                else:
                    # Skip header from subsequent files
                    next(infile)
                    outfile.write(infile.read())
    
    # Clean up chunk files
    for chunk_file in chunk_files:
        os.remove(chunk_file)
    
    return combined_file

# Use for large datasets
large_data = pd.DataFrame(...)  # 10,000+ rows
export_path = export_large_dataset(export_manager, large_data)
```

### Memory-Efficient Export

```python
def memory_efficient_export(data, path, chunk_size=1000):
    """Export data without loading everything into memory."""
    # Write header
    header_written = False
    
    for chunk_start in range(0, len(data), chunk_size):
        chunk = data.iloc[chunk_start:chunk_start + chunk_size]
        
        # Write chunk to file
        chunk.to_csv(
            path,
            mode='a' if header_written else 'w',
            header=not header_written,
            index=False,
            encoding='utf-8'
        )
        
        header_written = True
        
        # Free memory
        del chunk

# Use for very large datasets
memory_efficient_export(huge_dataset, "huge_export.csv")
```