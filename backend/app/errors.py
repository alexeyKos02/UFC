class AppError(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def bad_request(detail: str) -> AppError:
    return AppError(400, detail)


def unauthorized(detail: str = "Требуется вход в систему") -> AppError:
    return AppError(401, detail)


def forbidden(detail: str = "Недостаточно прав") -> AppError:
    return AppError(403, detail)


def not_found(detail: str = "Не найдено") -> AppError:
    return AppError(404, detail)


def conflict(detail: str) -> AppError:
    return AppError(409, detail)
