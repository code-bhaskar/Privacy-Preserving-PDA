from fastapi import HTTPException, status


class NotFoundError(HTTPException):
    def __init__(self, detail: str = "Resource not found"):
        super().__init__(status.HTTP_404_NOT_FOUND, detail)


class ConsentDeniedError(HTTPException):
    """FR-3: block any processing path without granted consent."""
    def __init__(self, category: str):
        super().__init__(
            status.HTTP_403_FORBIDDEN,
            f"Consent not granted for category '{category}'. "
            f"Grant it via POST /consent before this operation.",
        )


class ValidationError(HTTPException):
    def __init__(self, detail: str):
        super().__init__(status.HTTP_400_BAD_REQUEST, detail)


class InvalidCredentialsError(HTTPException):
    def __init__(self, detail: str = "Incorrect email or password"):
        super().__init__(
            status.HTTP_401_UNAUTHORIZED,
            detail=detail,
            headers={"WWW-Authenticate": "Bearer"},
        )
