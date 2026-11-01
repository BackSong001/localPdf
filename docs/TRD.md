# TRD.md — 기술 요구사항 및 설계 문서

## 1. 개요

`localPdf`는 로컬 단일 프로세스로 동작하는 이미지 → PDF 변환기와 PDF 텍스트 추출기다. v1은 외부 네트워크를 사용하지 않으며, v2에서 무료 LLM API(Gemini, NVIDIA NIM)를 사용한 요약을 추가한다.

- 요구사항 기준: `REQUIREMENT.md`
- API 계약: `API_SPEC.md`
- 개발 방식: **TDD** (실패 테스트 → 최소 구현 → 리팩터)

## 2. 아키텍처

```
┌──────────────────────────────────────────────────────────┐
│ Browser (React + Vite + TypeScript)                      │
│  - 파일 선택/드롭, 순서 조정, 업로드 진행률(XHR)         │
│  - Job 상태 폴링(500ms), PDF 다운로드                    │
│  - 텍스트 표시/복사/.txt 다운로드                        │
└───────────────────────────┬──────────────────────────────┘
                            │ HTTP (multipart, JSON)
┌───────────────────────────▼──────────────────────────────┐
│ FastAPI (단일 Uvicorn 워커, 127.0.0.1)                    │
│                                                          │
│  api/jobs.py     POST /api/jobs, GET status, GET download │
│  api/pdf.py      POST /api/pdf/text                       │
│  api/health.py   GET /api/health                          │
│                                                          │
│  services/jobs.py       인메모리 Job 저장소 + FIFO 워커   │
│  services/images.py     검증/EXIF/색상/알파 정규화        │
│  services/pdf_builder.py 이미지 → A4 PDF                  │
│  services/text.py       PDF 텍스트 레이어 추출            │
│  settings.py            환경변수/제한값                   │
└───────────────────────────┬──────────────────────────────┘
                            │
┌───────────────────────────▼──────────────────────────────┐
│ OS 임시 디렉터리                                          │
│  <tmp>/localpdf-<job_id>/uploads/0000.jpg ...             │
│  <tmp>/localpdf-<job_id>/normalized/...                   │
│  <tmp>/localpdf-<job_id>/output.pdf                       │
└──────────────────────────────────────────────────────────┘
```

### 컴포넌트 책임

| 컴포넌트 | 책임 | 하지 않는 일 |
|---|---|---|
| `api/*` | 요청 파싱, 상태 코드/에러 매핑, 응답 직렬화 | 이미지/PDF 처리 로직 |
| `services/jobs.py` | Job 생성/상태 전이/큐/정리 | 이미지 디코딩 |
| `services/images.py` | 형식 검증, EXIF, RGB/알파 정규화 | PDF 조립 |
| `services/pdf_builder.py` | 페이지 생성, 배치 계산, PDF 저장 | 업로드/HTTP |
| `services/text.py` | PDF 열기/페이지 텍스트 추출 | 파일 저장 |
| `settings.py` | 환경변수 로딩, 기본값/제한 | 비즈니스 로직 |
| 프론트엔드 | 입력/순서/진행률/결과 표시 | 파일 형식 신뢰 |

## 3. 기술 스택과 의존성

| 구분 | 선택 | 이유 |
|---|---|---|
| 런타임 | Python 3.11+ | 타입/성능, 생태계 |
| 웹 | FastAPI + Uvicorn | 타입 기반 API, TestClient |
| 이미지 | Pillow | EXIF, 알파, 형식 검증 |
| PDF | PyMuPDF | 생성과 텍스트 추출을 한 라이브러리로 |
| 설정 | python-dotenv | `.env` 로딩 |
| 테스트 | pytest (+ httpx/TestClient) | FastAPI 통합 테스트 |
| 린트 | ruff | 빠른 단일 도구 |
| 프론트 | React 18 + TypeScript + Vite | 표준적 로컬 SPA |
| 프론트 테스트 | `tsc --noEmit`, `npm run build` (필요 시 Vitest) | 최소 검증 |

`img2pdf`는 PyMuPDF와 역할이 겹쳐 사용하지 않는다. PDF 생성/추출 모두 PyMuPDF로 통일한다.

## 4. 디렉터리 구조

```
backend/
  pyproject.toml
  app/
    __init__.py
    main.py                 # create_app, lifespan, 정적 서빙
    settings.py
    api/
      __init__.py
      health.py
      jobs.py
      pdf.py
    services/
      __init__.py
      images.py
      pdf_builder.py
      text.py
      jobs.py
    errors.py               # AppError, 에러 코드→HTTP 매핑
  tests/
    conftest.py
    test_pdf_builder.py
    test_images.py
    test_text.py
    test_jobs_api.py
    test_pdf_api.py
    test_health.py
    test_cleanup.py
    test_perf.py            # slow 마크
frontend/
  package.json
  vite.config.ts
  tsconfig.json
  index.html
  src/
    main.tsx
    App.tsx
    styles.css
    api/client.ts
    lib/naturalSort.ts
    lib/download.ts
    features/image-to-pdf/
      ImageToPdfPage.tsx
      DropZone.tsx
      FileList.tsx
      JobProgress.tsx
    features/pdf-text/
      PdfTextPage.tsx
      TextResult.tsx
.env.example
README.md
```

## 5. 데이터 모델

### 5.1 Job

```python
JobStatus = Literal["queued", "converting", "done", "error"]

@dataclass
class Job:
    id: str                 # uuid4().hex (32자)
    status: JobStatus
    total: int              # 업로드된 이미지 수
    processed: int          # PDF에 추가 완료된 수 (0..total)
    error: JobError | None
    created_at: datetime    # UTC
    completed_at: datetime | None
    dir: Path               # <tmp>/localpdf-<id>
    output_path: Path | None
```

```python
@dataclass
class JobError:
    code: str               # 예: CONVERSION_FAILED
    message: str            # 사용자용 한국어
```

### 5.2 상태 전이

```
(생성) ──▶ queued ──▶ converting ──▶ done
                         │
                         └──────────▶ error
```

- `done`/`error`는 종료 상태이며 다시 전이하지 않는다.
- `processed`는 `converting` 중에만 증가하며 절대 감소하지 않는다.
- 다운로드는 `done`에서만 허용한다.

### 5.3 저장소

- `dict[str, Job]` + `threading.Lock` (워커 스레드와 이벤트 루프 공유).
- 서버 재시작 시 소실된다. 영속화는 범위 외다.
- Job 큐는 `asyncio.Queue[str]`, 워커 1개가 FIFO로 소비한다.

### 5.4 제한값 (기본)

| 상수 | 기본값 | 환경변수 |
|---|---|---|
| 최대 이미지 수 | 1,000 | `LOCALPDF_MAX_FILES` |
| 이미지 1개 최대 | 50 MiB | `LOCALPDF_MAX_IMAGE_BYTES` |
| 전체 업로드 최대 | 2 GiB | `LOCALPDF_MAX_TOTAL_BYTES` |
| PDF 1개 최대 | 100 MiB | `LOCALPDF_MAX_PDF_BYTES` |
| PDF 최대 페이지 | 2,000 | `LOCALPDF_MAX_PDF_PAGES` |
| Job TTL(완료 후) | 3,600초 | `LOCALPDF_JOB_TTL_SECONDS` |
| 정리 주기 | 600초 | `LOCALPDF_CLEANUP_INTERVAL_SECONDS` |
| 변환 동시성 | 1 | (고정) |

지원 이미지 형식: JPEG(`.jpg`, `.jpeg`), PNG(`.png`), WEBP(`.webp`), BMP(`.bmp`), TIFF(`.tif`, `.tiff`).

## 6. 처리 흐름

### 6.1 이미지 → PDF

```
Client                       API                        Worker
  │ POST /api/jobs (files)     │                           │
  ├───────────────────────────▶│ 1) 개수/총량 사전 검사     │
  │                            │ 2) job_dir 생성            │
  │                            │ 3) 파일별 스트리밍 저장    │
  │                            │    + 개별 크기 검사        │
  │                            │ 4) 형식 검증(Pillow)       │
  │                            │ 5) Job 생성(queued)        │
  │◀── 202 {job_id,...} ───────┤ 6) 큐 enqueue              │
  │                            │                           │
  │ GET /api/jobs/{id} (poll)  │                           │
  ├───────────────────────────▶│ status 조회 ◀─────────────┤ converting
  │◀── {processed,...} ────────┤                           │
  │                            │                           ├─ 1장씩 정규화
  │                            │                           ├─ 페이지 추가
  │                            │                           └─ output.pdf
  │◀── status=done ────────────┤                           │
  │ GET .../download           │                           │
  ├───────────────────────────▶│ FileResponse(output.pdf)  │
  │◀── application/pdf ────────┤                           │
```

**업로드 단계 규칙**
- multipart 필드명은 `files`(반복)다. 파트 수신 순서가 곧 페이지 순서다.
- 동일 파일명은 허용하며 인덱스로 구분한다.
- 저장 파일명은 `uploads/{index:04d}{ext}` (예: `0000.jpg`). 원본 파일명은 경로에 쓰지 않는다.
- FastAPI/Starlette multipart의 `max_files`를 `LOCALPDF_MAX_FILES`와 동기화한다. 초과는 `TOO_MANY_FILES`로 정규화한다.
- 1 MiB 청크로 복사하며 누적 크기를 검사한다. 초과 시 즉시 중단하고 job_dir을 삭제한다.
- 파일 수/총량은 파싱 전 `Content-Length`만으로 신뢰하지 않고 실제 수신량으로 검사한다.
- 형식 검증은 확장자가 아니라 Pillow `Image.open()` + `load()`(완전 디코딩) 성공 여부로 판단한다. 검증도 이미지 1장씩 수행한다.
- 검증 실패 시 해당 요청 전체를 거부하고 job_dir을 삭제한다(부분 Job 생성 없음).

**변환 단계 규칙**
- 워커는 Job의 `uploads/`를 인덱스 오름차순으로 순회한다.
- 이미지 1장 처리 후 즉시 페이지를 추가하고 파일 핸들을 닫는다. 전체 이미지를 메모리에 유지하지 않는다.
- 진행률은 페이지 추가 성공 시 `processed += 1`.
- 예외 발생 시 `status=error`, `error={code:"CONVERSION_FAILED", message:...}`, 부분 `output.pdf` 삭제.
- 완료 시 `status=done`, `completed_at` 기록.

### 6.2 PDF 텍스트 추출

```
Client ── POST /api/pdf/text (file) ──▶ API
                                         1) 크기 검사
                                         2) %PDF- 매직 + PyMuPDF open
                                         3) needs_pass / 페이지 수 검사
                                         4) 페이지별 get_text("text")
                                         5) strip + join
       ◀── 200 {page_count,has_text,text,pages} ──
```

- 동기 처리(수 초 이내). Job 모델을 사용하지 않는다.
- OCR 없음. 텍스트 레이어가 없으면 빈 문자열을 반환한다.
- 암호화된 PDF, 페이지 수가 0인 PDF는 `INVALID_PDF`로 거부한다.

## 7. PDF 생성 규칙

### 7.1 페이지 크기와 방향

```
A4_W = 595.276 pt
A4_H = 841.89 pt

if img_w > img_h:
    page_w, page_h = A4_H, A4_W   # 가로
else:
    page_w, page_h = A4_W, A4_H   # 세로 (정방형 포함)
```

### 7.2 배치 계산

```
scale = min(page_w / img_w, page_h / img_h)   # 업스케일 허용
draw_w = img_w * scale
draw_h = img_h * scale
x0 = (page_w - draw_w) / 2
y0 = (page_h - draw_h) / 2
rect = Rect(x0, y0, x0 + draw_w, y0 + draw_h)
```

- 여백 0, 중앙 정렬, 비율 유지, 자르기 없음.
- `page.insert_image(rect, ...)` 호출 시 `keep_proportion=True`를 사용하되, rect가 이미 비율을 만족하므로 추가 보정이 없어야 한다.
- 테스트는 rect 좌표를 ±0.5 pt 허용 오차로 검증한다.

### 7.3 이미지 정규화 정책

우선순위에 따라 아래 규칙을 적용한다.

| 순서 | 입력 상태 | 처리 | 출력 형식 |
|---|---|---|---|
| 1 | JPEG + EXIF Orientation=1 + mode=RGB | 원본 바이트 직접 삽입 (무손실) | 원본 JPEG |
| 2 | 그 외 | `exif_transpose` → RGB 변환 → 알파는 흰색 합성 | 아래 규칙 |
| 2-a | 원본이 JPEG 또는 WEBP | 재인코딩 | JPEG q=90 |
| 2-b | 원본이 PNG/BMP/TIFF | 재인코딩 | PNG (무손실) |

- 재인코딩 파일은 `normalized/{index:04d}.{ext}`에 저장한다.
- EXIF 방향 보정은 페이지 방향 판정(가로/세로) **이전**에 적용한다.
- 다중 프레임 이미지(TIFF 다페이지, 애니메이션 WEBP)는 첫 프레임만 사용한다.
- 색상 프로파일은 v1에서 변환하지 않는다.

## 8. 텍스트 추출 규칙

- `page.get_text("text")` 결과를 `strip()` 한다.
- `pages[i] = {page: i+1, text: ...}` (1-based).
- `has_text = any(p.text != "" for p in pages)`.
- `text = "\n\n".join(p.text for p in pages if p.text != "")`. 모든 페이지가 비면 `""`.
- 빈 페이지도 `pages` 배열에 포함한다.

## 9. API 설계 요약

상세 계약은 `API_SPEC.md`를 따른다.

| Method | Path | 목적 | 성공 |
|---|---|---|---|
| GET | `/api/health` | 헬스체크 | 200 |
| POST | `/api/jobs` | 이미지 업로드 + Job 생성 | 202 |
| GET | `/api/jobs/{job_id}` | Job 상태 | 200 |
| GET | `/api/jobs/{job_id}/download` | PDF 다운로드 | 200 |
| POST | `/api/pdf/text` | 텍스트 추출 | 200 |

## 10. 오류 처리

### 10.1 응답 형식

```json
{
  "detail": {
    "code": "UNSUPPORTED_IMAGE",
    "message": "지원하지 않는 이미지 형식입니다: photo.heic"
  }
}
```

- `AppError(code, message, http_status)`를 정의하고 FastAPI 예외 핸들러에서 위 형식으로 변환한다.
- 예상하지 못한 예외는 `INTERNAL_ERROR`(500)로 변환하며 스택트레이스/경로/키를 응답에 포함하지 않는다.
- 서버 로그에는 job_id, 오류 코드, 처리 수, 소요 시간만 남기고 파일 내용/키는 남기지 않는다.

### 10.2 오류 코드

| 코드 | HTTP | 발생 지점 |
|---|---|---|
| `EMPTY_UPLOAD` | 400 | 파일 0개 |
| `TOO_MANY_FILES` | 400 | 최대 개수 초과 |
| `FILE_TOO_LARGE` | 413 | 이미지 1개 초과 |
| `TOTAL_SIZE_EXCEEDED` | 413 | 전체 업로드 초과 |
| `UNSUPPORTED_IMAGE` | 415 | 허용 형식 아님 |
| `INVALID_IMAGE` | 422 | 손상/디코딩 실패 |
| `UNSUPPORTED_PDF` | 415 | PDF 아님 |
| `INVALID_PDF` | 422 | 손상/암호화/열기 실패 |
| `PDF_TOO_LARGE` | 413 | PDF 크기 초과 |
| `PDF_TOO_MANY_PAGES` | 422 | 페이지 수 초과 |
| `JOB_NOT_FOUND` | 404 | 없는/TTL 만료 Job |
| `JOB_NOT_READY` | 409 | 미완료 Job 다운로드 |
| `CONVERSION_FAILED` | — | Job 내부 오류 (Job.error) |
| `INTERNAL_ERROR` | 500 | 처리되지 않은 예외 |

## 11. 보안

- 기본 바인딩 `127.0.0.1`. 외부 노출은 명시적 설정 변경 없이는 불가.
- 인증 없음(로컬 단일 사용자 전제). 외부 노출 시 인증이 필요하다는 경고를 README에 둔다.
- 업로드 파일명을 경로로 사용하지 않는다. Job ID는 `uuid4().hex`, 저장명은 인덱스 기반.
- 임시 디렉터리는 `tempfile.mkdtemp(prefix="localpdf-")`(0700) 사용.
- 형식은 확장자가 아닌 실제 내용으로 검증한다.
- 개수/크기/페이지 제한을 서버에서 강제한다.
- CORS는 `http://127.0.0.1:5173`, `http://localhost:5173`만 허용(개발). 프로덕션은 동일 오리진 정적 서빙.
- `.env`의 API 키는 응답/로그/에러 메시지에 포함하지 않는다.
- v1은 아웃바운드 네트워크를 사용하지 않는다.

## 12. 성능·메모리·동시성

- **스트리밍 저장**: 업로드 파일을 청크 단위로 디스크에 기록한다.
- **1장씩 변환**: 이미지 1장 로드 → 정규화 → 페이지 추가 → 해제.
- **동시성 1**: `asyncio.Queue` + 단일 워커. CPU/메모리 폭주와 상태 경합을 방지한다.
- **블로킹 회피**: 변환은 `asyncio.to_thread`로 실행해 이벤트 루프를 막지 않는다.
- **목표**: 500장(100×100px) 60초 이내. 대용량 원본은 디스크/메모리 사용량이 커질 수 있음을 README에 명시.
- **폴링 부하**: 상태 조회는 메모리 읽기만 수행하며 파일 I/O가 없다.

## 13. 임시 저장과 정리

```
<tmp>/localpdf-<job_id>/
  uploads/0000.jpg ...
  normalized/0000.png ...
  output.pdf
```

- Job 생성 시 디렉터리 생성, 업로드 검증 실패 시 즉시 삭제.
- 완료/실패 후 TTL(기본 1시간)이 경과한 Job은 정리 태스크가 디렉터리째 삭제하고 저장소에서 제거한다. `queued`/`converting` 상태는 삭제하지 않는다.
- 정리 태스크는 lifespan에서 시작/종료한다.
- 서버 종료 시 모든 Job 디렉터리를 삭제한다.
- TTL 이후 상태 조회/다운로드는 `JOB_NOT_FOUND`.

## 14. 설정

`settings.py`는 시작 시 `.env`가 있으면 `python-dotenv`로 로드한 뒤 환경변수를 한 번 읽어 불변 설정 객체를 만든다. 실제 환경변수가 `.env`보다 우선한다. 기본값은 `.env.example`과 일치한다.

| 환경변수 | 기본값 | 설명 |
|---|---|---|
| `LOCALPDF_HOST` | `127.0.0.1` | 바인딩 주소 |
| `LOCALPDF_PORT` | `8000` | 포트 |
| `LOCALPDF_TEMP_DIR` | (OS 임시) | Job 루트 |
| `LOCALPDF_MAX_FILES` | `1000` | 최대 이미지 수 |
| `LOCALPDF_MAX_IMAGE_BYTES` | `52428800` | 이미지 1개 |
| `LOCALPDF_MAX_TOTAL_BYTES` | `2147483648` | 전체 업로드 |
| `LOCALPDF_MAX_PDF_BYTES` | `104857600` | PDF 1개 |
| `LOCALPDF_MAX_PDF_PAGES` | `2000` | PDF 페이지 |
| `LOCALPDF_JOB_TTL_SECONDS` | `3600` | 완료 후 Job 보존 |
| `LOCALPDF_CLEANUP_INTERVAL_SECONDS` | `600` | 정리 주기 |
| `LOCALPDF_CORS_ORIGINS` | `http://127.0.0.1:5173,http://localhost:5173` | 개발 CORS |
| `VITE_API_BASE_URL` | `http://127.0.0.1:8000` | 프론트 API 주소 (개발은 프록시) |
| `GEMINI_API_KEY` | (없음) | v2 |
| `GEMINI_MODEL` | `gemini-2.0-flash` | v2 |
| `NVIDIA_API_KEY` | (없음) | v2 |
| `NVIDIA_MODEL` | `meta/llama-3.1-70b-instruct` | v2 |
| `NVIDIA_BASE_URL` | `https://integrate.api.nvidia.com/v1` | v2 |
| `LLM_PROVIDER` | `gemini` | v2 |

## 15. 프론트엔드 설계

- **라우팅**: v1은 탭 기반 단일 페이지(라우터 의존성 없음).
- **상태**: 컴포넌트 로컬 상태. 전역 스토어 없음.
- **업로드**: `XMLHttpRequest` + `FormData`로 진행률 표시. `files` 파트를 화면 순서대로 append.
- **정렬**: `Intl.Collator(undefined, {numeric: true, sensitivity: "base"})`로 자연 정렬.
- **순서 변경**: 위/아래 버튼(최소 구현). 드래그 재정렬은 v1.1.
- **썸네일**: `URL.createObjectURL`, 삭제/언마운트 시 `revokeObjectURL`.
- **폴링**: 500 ms, `done`/`error` 시 중단, 언마운트 시 정리.
- **텍스트 결과**: `<pre>` 표시, `navigator.clipboard` 복사, Blob + `a[download]`로 `.txt` 저장.
- **에러 표시**: 서버 `detail.code/message`를 그대로 노출하되, 네트워크 오류는 별도 문구.
- **개발 프록시**: Vite `/api` → `http://127.0.0.1:8000`.
- **프로덕션**: `npm run build` 결과를 FastAPI가 `/`에서 정적 서빙.

## 16. 테스트 전략 (TDD)

### 16.1 사이클

1. `REQUIREMENT.md`의 테스트 ID에 해당하는 **실패 테스트**를 작성한다.
2. 테스트를 통과하는 **최소 구현**을 한다.
3. 중복/책임을 정리하는 **리팩터** 후 전체 테스트를 재실행한다.
4. 테스트 이름은 `test_tc_fr_003_a_portrait_a4` 형식을 따른다.

### 16.2 레이어

| 레이어 | 대상 | 도구 |
|---|---|---|
| 단위 | `images`, `pdf_builder`, `text`, 정렬 | pytest |
| 통합 | API 전체 흐름 (업로드→폴링→다운로드, 텍스트) | FastAPI TestClient |
| 정리 | TTL/종료 시 디렉터리 삭제 | pytest + tmp_path |
| 성능 | 500장 변환 | pytest `-m slow` |
| 프론트 | 타입/빌드, 정렬·다운로드 헬퍼 | `tsc`, `npm run build`, (선택) Vitest |

### 16.3 Fixture

`conftest.py`에서 코드로 생성한다(외부 파일/네트워크 금지).

- `make_image(format, size, color, exif_orientation=None)` — Pillow
- `make_text_pdf(pages)` — PyMuPDF로 텍스트 페이지 생성
- `make_image_only_pdf(pages)` — 이미지 페이지 생성 (텍스트 없음)
- `client(tmp_path, monkeypatch)` — 임시 `LOCALPDF_TEMP_DIR`로 앱 생성

### 16.4 검증 명령

```bash
pytest backend
pytest backend -m "not slow"
ruff check backend
cd frontend && npx tsc --noEmit && npm run build
```

### 16.5 주요 테스트 시나리오

- FR-002: multipart 파트 순서대로 페이지 텍스트/색상이 배치되는지.
- FR-003: 페이지 크기(±0.5pt), rect 위치/크기, 가로/세로 판정.
- FR-004: EXIF 6 이미지의 페이지 방향과 픽셀 방향.
- FR-005: 알파 PNG의 투명 영역이 흰색인지.
- FR-006: 폴링 중 `processed` 단조 증가 및 종료 상태.
- FR-012: TTL 경과 후 404 및 디렉터리 부재.
- NFR-001: 500장 변환 시간/페이지 수/순서.

## 17. 실행과 운영

```bash
# 백엔드 (backend 디렉터리)
uvicorn app.main:app --host 127.0.0.1 --port 8000

# 프론트 개발
cd frontend && npm run dev

# 프로덕션 정적 서빙
cd frontend && npm run build
# FastAPI가 frontend/dist를 /에서 서빙
```

- 단일 Uvicorn 워커만 사용한다(인메모리 Job 일관성).
- `--reload`는 개발에서만 사용한다(재시작 시 Job 소실).

## 18. 기술 결정과 트레이드오프

| 결정 | 대안 | 이유 |
|---|---|---|
| PyMuPDF로 생성+추출 통일 | img2pdf + pypdf | 의존성/책임 단순화, 텍스트 추출 필수 |
| 인메모리 Job | SQLite/Redis | 영속화 요구 없음, 로컬 단일 프로세스 |
| 폴링(500ms) | SSE/WebSocket | 구현 단순, 상태 조회 비용 낮음 |
| 단일 워커 | 다중 워커 | 메모리 보호, 상태 경합 제거 |
| A4 고정 | 페이지 크기 옵션 | v1 범위 최소화, 예측 가능한 출력 |
| JPEG 원본 직접 삽입 | 전체 재인코딩 | 품질/용량 보존 |
| 업로드 단일 multipart | 배치 업로드 | 구현 단순. 500장에서 불안정 시 v1.1에서 배치화 |
| OCR 제외 | Tesseract | 설치/정확도/속도 부담, v1 범위 외 |

## 19. v2 확장 지점 (요약)

- `services/llm.py`: provider 선택(`gemini`/`nvidia`), 청크 분할, map-reduce 요약, 429 백오프.
- 새 엔드포인트 `POST /api/summarize` (텍스트 또는 PDF + provider).
- 테스트는 provider를 mock하며 실제 키/네트워크 없이 실행 가능해야 한다.
- 키 미설정 시 `LLM_NOT_CONFIGURED`(400)로 안내한다.
