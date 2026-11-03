# API_SPEC.md — API 명세

- Base URL: `http://127.0.0.1:8000`
- 인코딩: UTF-8
- 요청/응답: `multipart/form-data` 또는 `application/json`
- 인증: 없음 (로컬 단일 사용자)
- API 문서: 개발 실행 시 `http://127.0.0.1:8000/docs`

---

## 1. 공통 규칙

### 1.1 오류 응답

모든 HTTP 오류는 아래 형식이다.

```json
{
  "detail": {
    "code": "UNSUPPORTED_IMAGE",
    "message": "지원하지 않는 이미지 형식입니다: photo.heic"
  }
}
```

| 필드 | 타입 | 설명 |
|---|---|---|
| `detail.code` | string | 안정적인 오류 코드 (클라이언트 분기용) |
| `detail.message` | string | 사용자용 한국어 메시지 |

- 내부 스택트레이스, 파일 경로, API 키는 포함하지 않는다.
- 요청 스키마 누락(예: `files` 없음)도 `EMPTY_UPLOAD`(400)로 정규화한다.

### 1.2 공통 제한

| 항목 | 기본값 | 초과 시 코드 |
|---|---|---|
| 이미지 수 | 1,000장 | `TOO_MANY_FILES` |
| 이미지 1개 | 50 MiB | `FILE_TOO_LARGE` |
| 전체 업로드 | 2 GiB | `TOTAL_SIZE_EXCEEDED` |
| PDF 1개 | 100 MiB | `PDF_TOO_LARGE` |
| PDF 페이지 | 2,000 | `PDF_TOO_MANY_PAGES` |
| Job TTL (완료 후) | 1시간 | `JOB_NOT_FOUND` |

### 1.3 지원 형식

| 종류 | 확장자 | MIME | 검증 |
|---|---|---|---|
| 이미지 | `.jpg`, `.jpeg`, `.png`, `.webp`, `.bmp`, `.tif`, `.tiff` | `image/*` | Pillow 실제 디코딩 |
| PDF | `.pdf` | `application/pdf` | `%PDF-` 매직 + PyMuPDF open |

### 1.4 Job 상태

| 값 | 의미 |
|---|---|
| `queued` | 생성됨, 변환 대기 |
| `converting` | 변환 중 |
| `done` | 완료, 다운로드 가능 |
| `error` | 실패, `error` 필드 확인 |

### 1.5 Job 객체

`POST /api/jobs`와 `GET /api/jobs/{job_id}`는 동일한 Job 객체를 반환한다.

| 필드 | 타입 | null | 설명 |
|---|---|---|---|
| `job_id` | string | 아니오 | UUID4 hex (32자) |
| `status` | string | 아니오 | `queued` / `converting` / `done` / `error` |
| `total` | integer | 아니오 | 업로드된 이미지 수 |
| `processed` | integer | 아니오 | PDF에 추가 완료된 수 (0 ≤ processed ≤ total) |
| `error` | object | 예 | 항상 포함. `status=error`이면 `{code, message}`, 아니면 `null` |
| `created_at` | string | 아니오 | ISO 8601 UTC (`...Z`) |
| `download_url` | string | 예 | 항상 포함. `status=done`이면 `/api/jobs/{job_id}/download`, 아니면 `null` |
| `markdown_url` | string | 예 | 항상 포함. `status=done`이면 `/api/jobs/{job_id}/markdown`, 아니면 `null` |

### 1.6 엔드포인트 요약

| Method | Path | 목적 | 성공 | 요청 본문 |
|---|---|---|---|---|
| GET | `/api/health` | 헬스체크 | 200 | 없음 |
| POST | `/api/jobs` | 이미지 업로드 + Job 생성 | 202 | multipart `files` |
| GET | `/api/jobs/{job_id}` | Job 상태 조회 | 200 | 없음 |
| GET | `/api/jobs/{job_id}/download` | 완성된 PDF 다운로드 | 200 | 없음 |
| POST | `/api/pdf/text` | PDF 텍스트 추출 | 200 | multipart `file` |
| POST | `/api/pdf/ocr` | 기존 PDF에 OCR 텍스트 레이어 추가 | 200 | multipart `file` |

---

## 2. GET `/api/health`

서버 생존 여부를 확인한다.

### 요청

| 항목 | 값 |
|---|---|
| Path | `/api/health` |
| Query | 없음 |
| Body | 없음 |

### 응답 `200 OK`

| 필드 | 타입 | 설명 |
|---|---|---|
| `status` | string | 항상 `ok` |
| `version` | string | 애플리케이션 버전 (예: `0.1.0`) |

```json
{
  "status": "ok",
  "version": "0.1.0"
}
```

### 오류

| HTTP | 코드 | 조건 |
|---|---|---|
| 500 | `INTERNAL_ERROR` | 처리되지 않은 예외 |

---

## 3. POST `/api/jobs`

이미지를 업로드하고 PDF 변환 Job을 생성한다. 모든 파일이 저장·검증된 뒤에 Job이 생성되며, 검증 실패 시 Job은 생성되지 않는다.

### 요청

| 항목 | 값 |
|---|---|
| Content-Type | `multipart/form-data` |
| Path | `/api/jobs` |

| Part | 타입 | 필수 | 반복 | 제약 |
|---|---|---|---|---|
| `files` | file | 예 | 예 (1~1,000) | 지원 이미지 형식, 개별 50 MiB, 전체 2 GiB |
| `ocr` | boolean | 아니오 | `true` | `false`이면 OCR 텍스트 레이어 없이 이미지 PDF만 생성 |

- 파트 **수신 순서**가 PDF 페이지 순서다.
- 프론트엔드는 화면에 표시된 순서대로 `files`를 append한다.
- 동일 파일명은 허용하며 순서로 구분한다.
- 파일명은 참고용이며 서버는 경로로 사용하지 않는다.

### 응답 `202 Accepted`

Job 객체(1.5)를 반환한다. 초기 상태는 `queued`, `processed=0`, `download_url=null`이다.

| 필드 | 타입 | 설명 |
|---|---|---|
| `job_id` | string | 생성된 Job ID |
| `status` | string | `queued` |
| `total` | integer | 업로드된 이미지 수 |
| `processed` | integer | `0` |
| `error` | null | `null` |
| `created_at` | string | 생성 시각 (UTC) |
| `download_url` | null | `null` |

```json
{
  "job_id": "9f2c1d7a4b8e4c0fa1d2e3f4567890ab",
  "status": "queued",
  "total": 500,
  "processed": 0,
  "error": null,
  "created_at": "2026-11-01T05:12:34Z",
  "download_url": null
}
```

### 오류

| HTTP | 코드 | 조건 |
|---|---|---|
| 400 | `EMPTY_UPLOAD` | `files` 파트가 없거나 0개 |
| 400 | `TOO_MANY_FILES` | 1,000장 초과 |
| 413 | `FILE_TOO_LARGE` | 이미지 1개가 50 MiB 초과 |
| 413 | `TOTAL_SIZE_EXCEEDED` | 전체 업로드가 2 GiB 초과 |
| 415 | `UNSUPPORTED_IMAGE` | 허용 확장자/형식 아님 |
| 422 | `INVALID_IMAGE` | 손상되어 디코딩 실패 |
| 500 | `INTERNAL_ERROR` | 처리되지 않은 예외 |

### 예시

```bash
curl -X POST http://127.0.0.1:8000/api/jobs \
  -F "files=@001.jpg" \
  -F "files=@002.jpg" \
  -F "files=@003.jpg"
```

```json
{
  "detail": {
    "code": "UNSUPPORTED_IMAGE",
    "message": "지원하지 않는 이미지 형식입니다: photo.heic"
  }
}
```

---

## 4. GET `/api/jobs/{job_id}`

Job 상태와 진행률을 조회한다. 프론트엔드는 500 ms 간격으로 폴링한다.

### 요청

| 항목 | 위치 | 타입 | 필수 | 설명 |
|---|---|---|---|---|
| `job_id` | path | string | 예 | UUID4 hex |

### 응답 `200 OK`

Job 객체(1.5). 상태별 예시는 아래와 같다.

**변환 중**

```json
{
  "job_id": "9f2c1d7a4b8e4c0fa1d2e3f4567890ab",
  "status": "converting",
  "total": 500,
  "processed": 237,
  "error": null,
  "created_at": "2026-11-01T05:12:34Z",
  "download_url": null
}
```

**완료**

```json
{
  "job_id": "9f2c1d7a4b8e4c0fa1d2e3f4567890ab",
  "status": "done",
  "total": 500,
  "processed": 500,
  "error": null,
  "created_at": "2026-11-01T05:12:34Z",
  "download_url": "/api/jobs/9f2c1d7a4b8e4c0fa1d2e3f4567890ab/download"
}
```

**실패**

```json
{
  "job_id": "9f2c1d7a4b8e4c0fa1d2e3f4567890ab",
  "status": "error",
  "total": 500,
  "processed": 237,
  "error": {
    "code": "CONVERSION_FAILED",
    "message": "이미지 변환 중 오류가 발생했습니다."
  },
  "created_at": "2026-11-01T05:12:34Z",
  "download_url": null
}
```

### 오류

| HTTP | 코드 | 조건 |
|---|---|---|
| 404 | `JOB_NOT_FOUND` | 존재하지 않거나 TTL 만료 |
| 500 | `INTERNAL_ERROR` | 처리되지 않은 예외 |

---

## 5. GET `/api/jobs/{job_id}/download`

완료된 Job의 PDF를 다운로드한다.

### 요청

| 항목 | 위치 | 타입 | 필수 | 설명 |
|---|---|---|---|---|
| `job_id` | path | string | 예 | UUID4 hex |

### 응답 `200 OK`

| 헤더 | 값 |
|---|---|
| `Content-Type` | `application/pdf` |
| `Content-Disposition` | `attachment; filename="localpdf-<job_id>.pdf"` |
| `Content-Length` | 파일 크기 (바이트) |

본문은 PDF 바이너리다.

### 오류

| HTTP | 코드 | 조건 |
|---|---|---|
| 404 | `JOB_NOT_FOUND` | 존재하지 않거나 TTL 만료 |
| 409 | `JOB_NOT_READY` | `status`가 `done`이 아님 (`queued`/`converting`/`error`) |
| 500 | `INTERNAL_ERROR` | 처리되지 않은 예외 |

---

## 5.1 GET `/api/jobs/{job_id}/markdown`

완료된 Job의 Markdown 텍스트 파일을 다운로드한다.

### 요청

| 항목 | 위치 | 타입 | 필수 | 설명 |
|---|---|---|---|---|
| `job_id` | path | string | 예 | UUID4 hex |

### 응답 `200 OK`

- `Content-Type`: `text/markdown; charset=utf-8`
- `Content-Disposition`: `attachment; filename="localpdf-<job_id>.md"`

본문은 추출된 Markdown 텍스트다.

### 오류

| HTTP | 코드 | 조건 |
|---|---|---|
| 404 | `JOB_NOT_FOUND` | 존재하지 않거나 TTL 만료 |
| 409 | `JOB_NOT_READY` | `status`가 `done`이 아님 |
| 500 | `INTERNAL_ERROR` | 처리되지 않은 예외 |

---

## 5.2 POST `/api/jobs/{job_id}/summarize` 및 POST `/api/summarize`

텍스트 또는 특정 Job의 Markdown 내용을 LLM(Gemini / NVIDIA NIM)으로 요약한다.

### 요청

| 항목 | 값 |
|---|---|
| Method | `POST` |
| Path | `/api/jobs/{job_id}/summarize` 또는 `/api/summarize` |
| Content-Type | `application/json` |

```json
{
  "text": "요약할 텍스트 (api/summarize 호출 시)",
  "provider": "gemini"
}
```

### 응답 `200 OK`

```json
{
  "summary": "1. 핵심 요약 내용...",
  "provider": "gemini",
  "model": "gemini-3.1-flash-lite"
}
```

### 오류

| HTTP | 코드 | 조건 |
|---|---|---|
| 400 | `LLM_NOT_CONFIGURED` | 지정된 provider의 API 키가 .env에 없음 |
| 400 | `EMPTY_TEXT` | 요약할 텍스트가 없음 |
| 429 | `LLM_RATE_LIMITED` | LLM API 사용량 초과 |
| 502 | `LLM_UPSTREAM_ERROR` | LLM 상위 서버 오류 |

---

## 6. POST `/api/pdf/text`

PDF를 업로드해 텍스트 레이어를 추출한다. OCR은 수행하지 않는다.

### 요청

| 항목 | 값 |
|---|---|
| Content-Type | `multipart/form-data` |
| Path | `/api/pdf/text` |

| Part | 타입 | 필수 | 반복 | 제약 |
|---|---|---|---|---|
| `file` | file | 예 | 아니오 | PDF, 100 MiB, 2,000페이지 |

- `file` 파트가 여러 개면 첫 번째만 사용한다.

### 응답 `200 OK`

| 필드 | 타입 | 설명 |
|---|---|---|
| `page_count` | integer | PDF 전체 페이지 수 |
| `has_text` | boolean | 텍스트가 한 페이지라도 있으면 `true` |
| `text` | string | 비어 있지 않은 페이지 텍스트를 `"\n\n"`로 연결한 전체 텍스트 (모두 비면 `""`) |
| `pages` | array | 페이지별 결과 (길이 == `page_count`) |
| `pages[].page` | integer | 1부터 시작하는 페이지 번호 |
| `pages[].text` | string | 해당 페이지 텍스트 (`strip()` 적용, 없으면 `""`) |

**텍스트 있음**

```json
{
  "page_count": 2,
  "has_text": true,
  "text": "첫 번째 페이지\n\n두 번째 페이지",
  "pages": [
    { "page": 1, "text": "첫 번째 페이지" },
    { "page": 2, "text": "두 번째 페이지" }
  ]
}
```

**텍스트 없음 (스캔 이미지 PDF)**

```json
{
  "page_count": 2,
  "has_text": false,
  "text": "",
  "pages": [
    { "page": 1, "text": "" },
    { "page": 2, "text": "" }
  ]
}
```

### 오류

| HTTP | 코드 | 조건 |
|---|---|---|
| 400 | `EMPTY_UPLOAD` | `file` 파트 없음 |
| 413 | `PDF_TOO_LARGE` | 100 MiB 초과 |
| 415 | `UNSUPPORTED_PDF` | PDF가 아님 (`%PDF-` 없음) |
| 422 | `INVALID_PDF` | 손상/암호화/0페이지/열기 실패 |
| 422 | `PDF_TOO_MANY_PAGES` | 2,000페이지 초과 |
| 500 | `INTERNAL_ERROR` | 처리되지 않은 예외 |

### 예시

```bash
curl -X POST http://127.0.0.1:8000/api/pdf/text \
  -F "file=@document.pdf"
```

---

## 7. POST `/api/pdf/ocr`

기존 PDF의 각 페이지를 `pdf2image`로 렌더링하고 `pytesseract`로 OCR한 결과를
투명 텍스트 레이어로 추가한다. 원본 PDF의 시각적 내용은 유지된다.
OCR 언어는 한국어 `kor`로 고정되어 있다. Tesseract의 `kor` 언어 데이터를
설치해야 한다.

### 요청

| 항목 | 값 |
|---|---|
| Content-Type | `multipart/form-data` |
| Path | `/api/pdf/ocr` |

| Part | 타입 | 필수 | 제약 |
|---|---|---|---|
| `file` | file | 예 | PDF, 100 MiB, 2,000페이지 |

### 응답 `202 Accepted`

```json
{
  "job_id": "...",
  "status": "queued",
  "total": 12,
  "processed": 0,
  "error": null,
  "download_url": null
}
```

페이지별 진행률은 `GET /api/pdf/ocr/{job_id}`로 조회한다.

완료되면 `download_url`의 PDF를 다운로드한다.

### 오류

`/api/pdf/text`와 동일한 PDF 업로드 오류에 더해, Python 패키지 또는 시스템
Tesseract가 설치되지 않으면 `503 OCR_NOT_CONFIGURED`를 반환한다.

### 예시

```bash
curl -X POST http://127.0.0.1:8000/api/pdf/ocr \
  -F "file=@scanned-document.pdf"
```

```bash
curl http://127.0.0.1:8000/api/pdf/ocr/<job_id>
curl http://127.0.0.1:8000/api/pdf/ocr/<job_id>/download -o searchable.pdf
```

---

## 8. 오류 코드 전체

| 코드 | HTTP | 설명 |
|---|---|---|
| `EMPTY_UPLOAD` | 400 | 필수 파일 파트 없음/0개 |
| `TOO_MANY_FILES` | 400 | 이미지 수 초과 |
| `FILE_TOO_LARGE` | 413 | 이미지 1개 크기 초과 |
| `TOTAL_SIZE_EXCEEDED` | 413 | 전체 업로드 크기 초과 |
| `UNSUPPORTED_IMAGE` | 415 | 지원하지 않는 이미지 형식 |
| `INVALID_IMAGE` | 422 | 이미지 손상/디코딩 실패 |
| `UNSUPPORTED_PDF` | 415 | PDF 형식 아님 |
| `INVALID_PDF` | 422 | PDF 손상/암호화/열기 실패 |
| `PDF_TOO_LARGE` | 413 | PDF 크기 초과 |
| `PDF_TOO_MANY_PAGES` | 422 | PDF 페이지 수 초과 |
| `OCR_NOT_CONFIGURED` | 503 | Python OCR 패키지 또는 Tesseract 미설치 |
| `JOB_NOT_FOUND` | 404 | Job 없음/TTL 만료 |
| `JOB_NOT_READY` | 409 | 미완료 Job 다운로드 시도 |
| `CONVERSION_FAILED` | — | Job 내부 변환 실패 (`Job.error.code`) |
| `INTERNAL_ERROR` | 500 | 처리되지 않은 예외 |

---

## 9. v2 예약 (미구현)

아래 엔드포인트는 v2 요약 기능용이며 v1에서는 제공하지 않는다.

| Method | Path | 목적 | 요청 | 응답 |
|---|---|---|---|---|
| POST | `/api/summarize` | 텍스트/PDF 요약 | `text` 또는 `file`, `provider`(`gemini`/`nvidia`) | `{summary, provider, model}` |

| HTTP | 코드 | 조건 |
|---|---|---|
| 400 | `LLM_NOT_CONFIGURED` | 해당 provider API 키 미설정 |
| 429 | `LLM_RATE_LIMITED` | 무료 API 한도 초과 |
| 502 | `LLM_UPSTREAM_ERROR` | provider 오류 |

> v1 구현 범위가 아니므로 테스트/구현 대상에서 제외한다.
