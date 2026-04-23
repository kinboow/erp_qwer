from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class AppException(Exception):
    def __init__(self, message: str, status_code: int = 500, error_code: str = "APP_ERROR"):
        self.status_code = status_code
        self.error_code = error_code
        self.message = message
        super().__init__(message)


class ERPUpstreamError(AppException):
    def __init__(self, message: str = "ERP upstream HTTP error"):
        super().__init__(message=message, status_code=502, error_code="ERP_UPSTREAM_ERROR")


class ERPBusinessError(AppException):
    def __init__(self, message: str = "ERP returned a business error"):
        super().__init__(message=message, status_code=502, error_code="ERP_BUSINESS_ERROR")


class ERPAuthError(AppException):
    def __init__(self, message: str = "ERP session expired or authentication failed"):
        super().__init__(message=message, status_code=502, error_code="ERP_AUTH_ERROR")


class NotFoundError(AppException):
    def __init__(self, error_code: str = "NOT_FOUND", message: str = "Resource not found"):
        super().__init__(message=message, status_code=404, error_code=error_code)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.error_code, "message": exc.message},
        )
