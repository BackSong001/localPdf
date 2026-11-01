from __future__ import annotations

ERROR_STATUS: dict[str, int] = {
    "EMPTY_UPLOAD": 400,
    "TOO_MANY_FILES": 400,
    "FILE_TOO_LARGE": 413,
    "TOTAL_SIZE_EXCEEDED": 413,
    "UNSUPPORTED_IMAGE": 415,
    "INVALID_IMAGE": 422,
    "UNSUPPORTED_PDF": 415,
    "INVALID_PDF": 422,
    "PDF_TOO_LARGE": 413,
    "PDF_TOO_MANY_PAGES": 422,
    "JOB_NOT_FOUND": 404,
    "JOB_NOT_READY": 409,
    "CONVERSION_FAILED": 500,
    "EMPTY_TEXT": 400,
    "LLM_NOT_CONFIGURED": 400,
    "LLM_RATE_LIMITED": 429,
    "LLM_UPSTREAM_ERROR": 502,
    "LLM_ALL_KEYS_FAILED": 502,
    "INVALID_REQUEST": 400,
    "INTERNAL_ERROR": 500,
}

ERROR_MESSAGES: dict[str, str] = {
    "EMPTY_UPLOAD": "업로드된 파일이 없습니다.",
    "TOO_MANY_FILES": "업로드할 수 있는 파일 수를 초과했습니다.",
    "FILE_TOO_LARGE": "파일 한 개의 크기 제한을 초과했습니다.",
    "TOTAL_SIZE_EXCEEDED": "전체 업로드 크기 제한을 초과했습니다.",
    "UNSUPPORTED_IMAGE": "지원하지 않는 이미지 형식입니다.",
    "INVALID_IMAGE": "이미지 파일이 손상되었거나 읽을 수 없습니다.",
    "UNSUPPORTED_PDF": "PDF 파일이 아닙니다.",
    "INVALID_PDF": "PDF 파일이 손상되었거나 열 수 없습니다.",
    "PDF_TOO_LARGE": "PDF 파일 크기 제한을 초과했습니다.",
    "PDF_TOO_MANY_PAGES": "PDF 페이지 수 제한을 초과했습니다.",
    "JOB_NOT_FOUND": "작업을 찾을 수 없습니다.",
    "JOB_NOT_READY": "아직 다운로드할 수 없는 작업입니다.",
    "CONVERSION_FAILED": "이미지 변환 중 오류가 발생했습니다.",
    "EMPTY_TEXT": "요약할 텍스트가 없습니다.",
    "LLM_NOT_CONFIGURED": "LLM API 키가 설정되지 않았습니다.",
    "LLM_RATE_LIMITED": "LLM API 사용 한도를 초과했습니다.",
    "LLM_UPSTREAM_ERROR": "LLM API 호출 중 오류가 발생했습니다.",
    "LLM_ALL_KEYS_FAILED": "모든 LLM API 키로 요청에 실패했습니다.",
    "INVALID_REQUEST": "요청 형식이 올바르지 않습니다.",
    "INTERNAL_ERROR": "서버 내부 오류가 발생했습니다.",
}


class AppError(Exception):
    def __init__(
        self,
        code: str,
        message: str | None = None,
        http_status: int | None = None,
    ) -> None:
        self.code = code
        self.message = message or ERROR_MESSAGES.get(code, "요청을 처리할 수 없습니다.")
        self.http_status = http_status or ERROR_STATUS.get(code, 500)
        super().__init__(self.message)

    def detail(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}
