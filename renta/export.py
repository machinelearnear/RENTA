"""
Export and output management for RENTA library.

This module provides the ExportManager class and various data exporters
for handling output in multiple formats with comprehensive error handling.
"""

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Union

import pandas as pd

from .config import ConfigManager
from .exceptions import ExportFormatError, RentaError
from .interfaces import DataExporter


class BaseExporter(DataExporter):
    """Base implementation for data exporters."""
    
    def __init__(self, config: ConfigManager):
        """Initialize exporter with configuration.
        
        Args:
            config: Configuration manager instance
        """
        self.config = config
    
    def _ensure_export_directory(self, path: str) -> None:
        """Ensure export directory exists.
        
        Args:
            path: File path to create directory for
            
        Raises:
            ExportFormatError: If directory cannot be created
        """
        try:
            directory = os.path.dirname(path)
            if directory:
                Path(directory).mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise ExportFormatError(
                f"Failed to create export directory: {e}",
                {"path": path, "error": str(e)}
            )


class DataFrameExporter(BaseExporter):
    """Exporter that returns pandas DataFrame (in-memory)."""
    
    def export(
        self, 
        data: pd.DataFrame, 
        path: Optional[str] = None,
        **kwargs
    ) -> pd.DataFrame:
        """Export data as DataFrame.
        
        Args:
            data: DataFrame to export
            path: Ignored for DataFrame export
            **kwargs: Additional options (ignored)
            
        Returns:
            The original DataFrame
        """
        return data.copy()
    
    def get_file_extension(self) -> str:
        """Get file extension for DataFrame format.
        
        Returns:
            Empty string as DataFrames are in-memory
        """
        return ""


class CSVExporter(BaseExporter):
    """Exporter for CSV format with comprehensive error handling."""
    
    def export(
        self, 
        data: pd.DataFrame, 
        path: Optional[str] = None,
        **kwargs
    ) -> Union[str, pd.DataFrame]:
        """Export data as CSV with enhanced error handling.
        
        Args:
            data: DataFrame to export
            path: Optional file path for export
            **kwargs: Additional CSV options (index, encoding, etc.)
            
        Returns:
            File path if exported to file, or CSV string if no path
            
        Raises:
            ExportFormatError: If export fails
        """
        # Set default CSV options with validation
        csv_options = {
            'index': False,
            'encoding': 'utf-8',
            **kwargs
        }
        
        # Validate CSV-specific options
        self._validate_csv_options(csv_options)
        
        if path:
            temp_path = None
            try:
                self._ensure_export_directory(path)
                
                # Use temporary file for atomic write
                temp_path = path + ".tmp"
                data.to_csv(temp_path, **csv_options)
                
                # Atomic move to final location
                os.rename(temp_path, path)
                return path
                
            except UnicodeEncodeError as e:
                if temp_path and os.path.exists(temp_path):
                    os.remove(temp_path)
                raise ExportFormatError(
                    f"Unicode encoding error in CSV export: {e}",
                    {
                        "path": path, 
                        "encoding": csv_options.get('encoding', 'utf-8'),
                        "error": str(e),
                        "suggestion": "Try using 'utf-8-sig' or 'latin1' encoding"
                    }
                )
            except (OSError, IOError) as e:
                if temp_path and os.path.exists(temp_path):
                    os.remove(temp_path)
                raise ExportFormatError(
                    f"IO error during CSV export to {path}: {e}",
                    {"path": path, "error": str(e), "error_type": type(e).__name__}
                )
            except Exception as e:
                if temp_path and os.path.exists(temp_path):
                    os.remove(temp_path)
                raise ExportFormatError(
                    f"Failed to export CSV to {path}: {e}",
                    {"path": path, "error": str(e), "error_type": type(e).__name__}
                )
        else:
            try:
                return data.to_csv(**csv_options)
            except UnicodeEncodeError as e:
                raise ExportFormatError(
                    f"Unicode encoding error in CSV generation: {e}",
                    {
                        "encoding": csv_options.get('encoding', 'utf-8'),
                        "error": str(e),
                        "suggestion": "Try using 'utf-8-sig' or 'latin1' encoding"
                    }
                )
            except Exception as e:
                raise ExportFormatError(
                    f"Failed to generate CSV string: {e}",
                    {"error": str(e), "error_type": type(e).__name__}
                )
    
    def _validate_csv_options(self, options: dict) -> None:
        """Validate CSV export options.
        
        Args:
            options: CSV export options to validate
            
        Raises:
            ExportFormatError: If options are invalid
        """
        # Check encoding
        encoding = options.get('encoding', 'utf-8')
        try:
            'test'.encode(encoding)
        except LookupError:
            raise ExportFormatError(
                f"Invalid encoding '{encoding}' for CSV export",
                {"encoding": encoding, "suggestion": "Use 'utf-8', 'latin1', or 'utf-8-sig'"}
            )
        
        # Validate separator if provided
        sep = options.get('sep')
        if sep is not None and len(str(sep)) != 1:
            raise ExportFormatError(
                f"CSV separator must be a single character, got '{sep}'",
                {"separator": sep}
            )
    
    def get_file_extension(self) -> str:
        """Get file extension for CSV format.
        
        Returns:
            CSV file extension
        """
        return ".csv"


class JSONExporter(BaseExporter):
    """Exporter for JSON format with comprehensive error handling."""
    
    def export(
        self, 
        data: pd.DataFrame, 
        path: Optional[str] = None,
        **kwargs
    ) -> Union[str, Dict]:
        """Export data as JSON with enhanced error handling.
        
        Args:
            data: DataFrame to export
            path: Optional file path for export
            **kwargs: Additional JSON options (orient, indent, etc.)
            
        Returns:
            File path if exported to file, or dict if no path
            
        Raises:
            ExportFormatError: If export fails
        """
        # Set default JSON options with validation
        json_options = {
            'orient': 'records',
            'date_format': 'iso',
            **kwargs
        }
        
        # Validate JSON-specific options
        self._validate_json_options(json_options)
        
        if path:
            temp_path = None
            try:
                self._ensure_export_directory(path)
                
                # Use temporary file for atomic write
                temp_path = path + ".tmp"
                data.to_json(temp_path, **json_options)
                
                # Verify JSON is valid by attempting to read it
                with open(temp_path, 'r', encoding='utf-8') as f:
                    json.load(f)
                
                # Atomic move to final location
                os.rename(temp_path, path)
                return path
                
            except json.JSONDecodeError as e:
                if temp_path and os.path.exists(temp_path):
                    os.remove(temp_path)
                raise ExportFormatError(
                    f"Invalid JSON generated during export: {e}",
                    {
                        "path": path,
                        "error": str(e),
                        "context": "Generated JSON is not valid"
                    }
                )
            except (OSError, IOError) as e:
                if temp_path and os.path.exists(temp_path):
                    os.remove(temp_path)
                raise ExportFormatError(
                    f"IO error during JSON export to {path}: {e}",
                    {"path": path, "error": str(e), "error_type": type(e).__name__}
                )
            except Exception as e:
                if temp_path and os.path.exists(temp_path):
                    os.remove(temp_path)
                raise ExportFormatError(
                    f"Failed to export JSON to {path}: {e}",
                    {"path": path, "error": str(e), "error_type": type(e).__name__}
                )
        else:
            try:
                # Return as dict for in-memory usage
                json_str = data.to_json(**json_options)
                return json.loads(json_str)
            except json.JSONDecodeError as e:
                raise ExportFormatError(
                    f"Invalid JSON generated: {e}",
                    {
                        "error": str(e),
                        "context": "Generated JSON string is not valid",
                        "options": json_options
                    }
                )
            except Exception as e:
                raise ExportFormatError(
                    f"Failed to generate JSON: {e}",
                    {"error": str(e), "error_type": type(e).__name__}
                )
    
    def _validate_json_options(self, options: dict) -> None:
        """Validate JSON export options.
        
        Args:
            options: JSON export options to validate
            
        Raises:
            ExportFormatError: If options are invalid
        """
        # Validate orient option
        valid_orients = ['split', 'records', 'index', 'columns', 'values', 'table']
        orient = options.get('orient', 'records')
        if orient not in valid_orients:
            raise ExportFormatError(
                f"Invalid JSON orient '{orient}'",
                {"orient": orient, "valid_orients": valid_orients}
            )
        
        # Validate date_format option
        date_format = options.get('date_format')
        if date_format is not None and date_format not in ['epoch', 'iso']:
            raise ExportFormatError(
                f"Invalid JSON date_format '{date_format}'",
                {"date_format": date_format, "valid_formats": ['epoch', 'iso']}
            )
    
    def get_file_extension(self) -> str:
        """Get file extension for JSON format.
        
        Returns:
            JSON file extension
        """
        return ".json"


class ExportManager:
    """Manages data export in multiple formats with comprehensive error handling."""
    
    # Supported export formats
    SUPPORTED_FORMATS = ["dataframe", "csv", "json"]
    
    def __init__(self, config: ConfigManager):
        """Initialize ExportManager with configuration.
        
        Args:
            config: Configuration manager instance
        """
        self.config = config
        self._exporters = {
            "dataframe": DataFrameExporter(config),
            "csv": CSVExporter(config),
            "json": JSONExporter(config),
        }
        self._partial_files = []  # Track files for cleanup on failure
    
    def export(
        self, 
        data: pd.DataFrame, 
        format: str = "dataframe", 
        path: Optional[str] = None,
        **kwargs
    ) -> Union[pd.DataFrame, str, Dict]:
        """Export data in specified format with comprehensive error handling.
        
        Args:
            data: DataFrame to export
            format: Export format ('dataframe', 'csv', 'json')
            path: Optional file path for export
            **kwargs: Format-specific export options
            
        Returns:
            Exported data (DataFrame, file path, or dict)
            
        Raises:
            ExportFormatError: If format is unsupported or export fails
        """
        # Clear any previous partial files
        self._partial_files.clear()
        
        try:
            # Validate format with descriptive error
            self._validate_format(format)
            
            # Validate data with context
            self._validate_data(data, format)
            
            # Generate path if needed and not provided
            if path is None and format != "dataframe":
                path = self._generate_filename(format)
            
            # Track file for cleanup if export fails
            if path:
                self._partial_files.append(path)
            
            # Validate path permissions and space
            if path:
                self._validate_export_path(path)
            
            # Get appropriate exporter and export
            exporter = self._get_exporter(format)
            
            result = exporter.export(data, path, **kwargs)
            
            # Clear partial files on success
            self._partial_files.clear()
            
            return result
            
        except ExportFormatError:
            # Clean up partial files and re-raise
            self._cleanup_on_failure()
            raise
        except (OSError, IOError, PermissionError) as e:
            # Handle IO-related errors with context
            self._cleanup_on_failure()
            raise ExportFormatError(
                f"IO error during {format} export: {e}",
                {
                    "format": format, 
                    "path": path, 
                    "error_type": type(e).__name__,
                    "error": str(e),
                    "context": "File system operation failed"
                }
            )
        except MemoryError as e:
            # Handle memory errors
            self._cleanup_on_failure()
            raise ExportFormatError(
                f"Memory error during {format} export - dataset too large: {e}",
                {
                    "format": format,
                    "data_shape": str(data.shape) if data is not None else "None",
                    "error": str(e),
                    "context": "Insufficient memory for export operation"
                }
            )
        except Exception as e:
            # Wrap other unexpected exceptions with context
            self._cleanup_on_failure()
            raise ExportFormatError(
                f"Unexpected error during {format} export: {e}",
                {
                    "format": format, 
                    "path": path, 
                    "error_type": type(e).__name__,
                    "error": str(e),
                    "context": "Unexpected error during export operation"
                }
            )
    
    def _get_exporter(self, format: str) -> DataExporter:
        """Get appropriate exporter for format.
        
        Args:
            format: Export format name
            
        Returns:
            DataExporter instance for the format
            
        Raises:
            ExportFormatError: If format is not supported
        """
        if format not in self._exporters:
            raise ExportFormatError(format, self.SUPPORTED_FORMATS)
        
        return self._exporters[format]
    
    def _generate_filename(self, format: str) -> str:
        """Generate collision-safe filename.
        
        Args:
            format: Export format to determine extension
            
        Returns:
            Full path to generated filename
            
        Raises:
            ExportFormatError: If export directory cannot be created
        """
        try:
            # Get export directory from config
            export_dir = self.config.get("data.export_dir", "~/.renta/exports")
            export_dir = os.path.expanduser(export_dir)
            
            # Ensure directory exists
            Path(export_dir).mkdir(parents=True, exist_ok=True)
            
            # Generate timestamp-based filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            exporter = self._get_exporter(format)
            extension = exporter.get_file_extension()
            
            # Create base filename
            base_filename = f"renta_export_{timestamp}{extension}"
            full_path = os.path.join(export_dir, base_filename)
            
            # Handle collisions by adding counter
            counter = 1
            while os.path.exists(full_path):
                name_part = f"renta_export_{timestamp}_{counter:03d}{extension}"
                full_path = os.path.join(export_dir, name_part)
                counter += 1
                
                # Prevent infinite loop
                if counter > 999:
                    raise ExportFormatError(
                        "Too many filename collisions, cannot generate unique filename",
                        {"base_path": full_path, "counter": counter}
                    )
            
            return full_path
            
        except OSError as e:
            raise ExportFormatError(
                f"Failed to generate filename in export directory: {e}",
                {"export_dir": export_dir, "error": str(e)}
            )
    
    def register_exporter(self, format_name: str, exporter: DataExporter) -> None:
        """Register a custom exporter for a format.
        
        Args:
            format_name: Name of the format
            exporter: DataExporter instance
        """
        self._exporters[format_name] = exporter
        if format_name not in self.SUPPORTED_FORMATS:
            self.SUPPORTED_FORMATS.append(format_name)
    
    def list_supported_formats(self) -> list:
        """List all supported export formats.
        
        Returns:
            List of supported format names
        """
        return self.SUPPORTED_FORMATS.copy()
    
    def _validate_format(self, format: str) -> None:
        """Validate export format with descriptive error.
        
        Args:
            format: Export format to validate
            
        Raises:
            ExportFormatError: If format is not supported
        """
        if not isinstance(format, str):
            raise ExportFormatError(
                f"Export format must be a string, got {type(format).__name__}",
                {"provided_format": str(format), "supported_formats": self.SUPPORTED_FORMATS}
            )
        
        if format not in self.SUPPORTED_FORMATS:
            # Suggest closest match if available
            suggestions = [f for f in self.SUPPORTED_FORMATS if format.lower() in f.lower()]
            error_details = {
                "provided_format": format,
                "supported_formats": self.SUPPORTED_FORMATS
            }
            if suggestions:
                error_details["suggestions"] = suggestions
            
            raise ExportFormatError(format, self.SUPPORTED_FORMATS)
    
    def _validate_data(self, data: pd.DataFrame, format: str) -> None:
        """Validate data for export with context.
        
        Args:
            data: DataFrame to validate
            format: Export format for context
            
        Raises:
            ExportFormatError: If data is invalid for export
        """
        if data is None:
            raise ExportFormatError(
                "Cannot export None data",
                {"format": format, "data": "None"}
            )
        
        if not isinstance(data, pd.DataFrame):
            raise ExportFormatError(
                f"Data must be a pandas DataFrame, got {type(data).__name__}",
                {"format": format, "data_type": type(data).__name__}
            )
        
        if data.empty:
            raise ExportFormatError(
                "Cannot export empty DataFrame",
                {"format": format, "data_shape": str(data.shape)}
            )
        
        # Check for problematic data types that might cause export issues
        problematic_columns = []
        for col in data.columns:
            if data[col].dtype == 'object':
                # Check for mixed types that might cause issues
                sample = data[col].dropna().head(100)
                if len(sample) > 0:
                    types = set(type(x).__name__ for x in sample)
                    if len(types) > 1:
                        problematic_columns.append((col, list(types)))
        
        if problematic_columns and format in ['csv', 'json']:
            raise ExportFormatError(
                f"DataFrame contains columns with mixed data types that may cause {format} export issues",
                {
                    "format": format,
                    "problematic_columns": problematic_columns,
                    "suggestion": "Consider converting mixed-type columns to strings before export"
                }
            )
    
    def _validate_export_path(self, path: str) -> None:
        """Validate export path permissions and available space.
        
        Args:
            path: File path to validate
            
        Raises:
            ExportFormatError: If path is invalid or inaccessible
        """
        try:
            # Check if directory exists and is writable
            directory = os.path.dirname(path)
            if directory and not os.path.exists(directory):
                # Try to create directory
                Path(directory).mkdir(parents=True, exist_ok=True)
            
            # Check write permissions by creating a temporary file
            temp_path = path + ".tmp"
            try:
                with open(temp_path, 'w') as f:
                    f.write("test")
                os.remove(temp_path)
            except PermissionError as e:
                raise ExportFormatError(
                    f"No write permission for export path: {path}",
                    {"path": path, "error": str(e), "context": "Permission denied"}
                )
            
            # Check if file already exists and warn
            if os.path.exists(path):
                # This is just a warning - we'll overwrite
                pass
                
        except OSError as e:
            raise ExportFormatError(
                f"Invalid export path: {path}",
                {"path": path, "error": str(e), "context": "Path validation failed"}
            )
    
    def _cleanup_on_failure(self) -> None:
        """Clean up partial files on export failure.
        
        This method is called automatically when export operations fail
        and the debug.keep_partial configuration is False.
        """
        if self.config.get("debug.keep_partial", False):
            # Keep partial files for debugging
            return
        
        cleanup_errors = []
        for path in self._partial_files:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except OSError as e:
                cleanup_errors.append({"path": path, "error": str(e)})
        
        # Clear the list after cleanup attempt
        self._partial_files.clear()
        
        # Note: We don't raise cleanup errors as they're secondary to the main export error
        # But we could log them if logging is available
    
    def cleanup_partial_files(self, paths: list) -> None:
        """Clean up partial files on failure (public method for external use).
        
        Args:
            paths: List of file paths to clean up
        """
        cleanup_errors = []
        for path in paths:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except OSError as e:
                cleanup_errors.append({"path": path, "error": str(e)})
        
        if cleanup_errors:
            raise ExportFormatError(
                "Failed to clean up some partial files",
                {"cleanup_errors": cleanup_errors}
            )