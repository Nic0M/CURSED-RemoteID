class HealthcheckError(Exception):
    """General error for all healthcheck errors."""


class JWTError(HealthcheckError):
    """General error for JSON Web Token (JWT) processing."""


class JSONValueError(JWTError):
    """Invalid JSON used to generate JSON Web Token (JWT)"""
