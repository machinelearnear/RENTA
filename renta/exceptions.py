"""
Core exception hierarchy for RENTA library.

All RENTA exceptions inherit from RentaError to provide a consistent
error handling interface.
"""


class RentaError(Exception):
    """Base exception for RENTA library.

    All RENTA-specific exceptions inherit from this class to provide
    a consistent error handling interface for library consumers.
    """

    def __init__(self, message: str, details: dict = None):
        """Initialize RentaError with message and optional details.

        Args:
            message: Human-readable error message
            details: Optional dictionary with additional error context
        """
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def __str__(self) -> str:
        """Return string representation of the error."""
        if self.details:
            return f"{self.message} (Details: {self.details})"
        return self.message


class ConfigurationError(RentaError):
    """Configuration-related errors.

    Raised when there are issues with configuration loading, validation,
    or when required configuration values are missing or invalid.
    """

    pass


class AirbnbDataError(RentaError):
    """Airbnb data ingestion errors.

    Raised when there are issues downloading, processing, or validating
    Airbnb data from InsideAirbnb or during data processing operations.
    """

    pass


class ScrapingError(RentaError):
    """Web scraping errors.

    Base class for all web scraping related errors, including network
    issues, parsing failures, and rate limiting problems.
    """

    pass


class ZonapropAntiBotError(ScrapingError):
    """Zonaprop anti-bot protection detected.

    Raised when Zonaprop's anti-bot protection (like Cloudflare) is
    encountered during scraping operations. Suggests using manual
    HTML file fallback.
    """

    def __init__(self, message: str = None, details: dict = None):
        """Initialize with default message suggesting HTML fallback."""
        if message is None:
            message = (
                "Zonaprop anti-bot protection detected. "
                "Consider using manual HTML file fallback with html_path parameter."
            )
        super().__init__(message, details)


class MatchingError(RentaError):
    """Spatial matching errors.

    Raised when there are issues during spatial matching operations,
    such as invalid coordinates, missing data, or algorithm failures.
    """

    pass


class AIServiceConfigurationError(RentaError):
    """AWS Bedrock configuration errors.

    Raised when there are issues with AWS Bedrock configuration,
    authentication, or service availability.
    """

    pass


class ExportFormatError(RentaError):
    """Data export format errors.

    Raised when an unsupported export format is requested or when
    there are issues during the export process.
    """

    def __init__(self, format_name: str, supported_formats: list = None):
        """Initialize with format information.

        Args:
            format_name: The unsupported format that was requested
            supported_formats: List of supported formats
        """
        if supported_formats:
            message = (
                f"Unsupported export format '{format_name}'. "
                f"Supported formats: {', '.join(supported_formats)}"
            )
        else:
            message = f"Unsupported export format '{format_name}'"

        super().__init__(message, {"format": format_name, "supported": supported_formats})
