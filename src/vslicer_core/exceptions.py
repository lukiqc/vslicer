"""Custom exception hierarchy for VSlicer.

Provides structured exception types for better error handling and debugging.
"""


class VSlicerError(Exception):
    """Base exception for all VSlicer errors.

    All custom exceptions in VSlicer inherit from this class,
    allowing callers to catch all VSlicer-specific errors with a single except clause.
    """

    pass


class MPVError(VSlicerError):
    """Errors related to mpv playback and IPC communication.

    Raised when:
    - mpv process fails to start
    - IPC connection fails
    - mpv commands fail
    """

    pass


class ExportError(VSlicerError):
    """Errors related to video export operations.

    Raised when:
    - ffmpeg command fails
    - Output file cannot be created
    - Encoding errors occur
    """

    pass


class ValidationError(VSlicerError):
    """Errors related to input validation.

    Raised when:
    - URL is invalid or malformed
    - Clip specification is invalid
    - Export options are invalid
    """

    pass


class ConfigurationError(VSlicerError):
    """Errors related to configuration.

    Raised when:
    - Required configuration is missing
    - Configuration values are invalid
    """

    pass
