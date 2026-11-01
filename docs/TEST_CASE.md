# TEST_CASE.md — 테스트 케이스 명세

- 기준 문서: `docs/REQUIREMENT.md`, `docs/TRD.md`, `docs/API_SPEC.md`
- 범위: v1 전체 + v2 LLM 다중 키 failover(제안)
- 상태: **v1 실행 대기**, **v2는 명세 반영 대기(제안)**
- 원칙: 실패 테스트(Red) → 최소 구현(Green) → 리팩터. 각 테스트는 요구사항 ID에 추적 가능해야 한다.

---

## 1. 테스트 환경과 도구

| 구분 | 도구 | 용도 |
|---|---|---|
| 백엔드 단위/통합 | pytest, FastAPI TestClient | 서비스/API 검증 |
| 이미지 fixture | Pillow | JPEG/PNG/EXIF/알파 생성 |
| PDF fixture | PyMuPDF | 텍스트/이미지 전용 PDF 생성 |
| 시간 제어 | pytest `monkeypatch` 또는 주입 가능한 clock | TTL/쿨다운 검증 |
| LLM mock | HTTP transport mock | 실제 키/네트워크 없이 failover 검증 |
| 프론트 | `tsc --noEmit`, `npm run build`, (선택) Vitest | 타입/빌드/헬퍼 |
| 린트 | ruff | 백엔드 정적 검사 |

- 모든 자동 테스트는 **외부 네트워크 없이** 실행되어야 한다.
- 실제 LLM 키 스모크 테스트는 수동(`manual`)로 분리하고 CI에서 제외한다.
- 테스트 함수명: `test_<test_id 소문자, 하이픈→언더스코어>_<설명>` (예: `test_tc_fr_003_a_portrait_a4`).

## 2. 테스트 데이터(Fixture)

| 이름 | 생성 방법 | 사용 테스트 |
|---|---|---|
| `img_portrait` | 100×200 JPEG, 단색 | FR-003 |
| `img_landscape` | 200×100 JPEG, 단색 | FR-003 |
| `img_square` | 150×150 PNG | FR-003 |
| `img_colors` | 서로 다른 단색 이미지 3장 (a,b,c) | FR-002, FR-007 |
| `img_exif6` | 100×200 JPEG, Orientation=6 | FR-004 |
| `img_exif3` | 200×100 JPEG, Orientation=3 | FR-004 |
| `img_alpha` | 투명 배경 + 불투명 사각형 PNG | FR-005 |
| `img_palette_alpha` | 팔레트 + transparency PNG | FR-005 |
| `img_small` | 10×10 PNG | FR-003 |
| `img_corrupt` | 확장자만 `.jpg`인 텍스트 바이트 | FR-011 |
| `img_oversize` | 51 MiB 더미 파일 | FR-001 |
| `pdf_text2` | 텍스트 2페이지 PDF | FR-008 |
| `pdf_image_only` | 이미지 2페이지 PDF | FR-009 |
| `pdf_mixed` | 텍스트 1페이지 + 이미지 1페이지 | FR-009 |
| `pdf_encrypted` | 암호 설정 PDF | FR-011 |
| `pdf_corrupt` | 확장자만 `.pdf`인 텍스트 바이트 | FR-011 |
| `pdf_many_pages` | 2,001페이지 PDF (또는 페이지 수 제한 단위 테스트) | FR-011 |
| `llm_mock` | 키별 응답 시퀀스를 반환하는 mock transport | LLM-* |

## 3. 테스트 ID 규칙

| 접두사 | 의미 | 예 |
|---|---|---|
| `TC-FR-xxx-y` | 기능 요구사항 | `TC-FR-003-a` |
| `TC-NFR-xxx` | 비기능 요구사항 | `TC-NFR-001` |
| `TC-API-xxx` | API 계약 | `TC-API-004` |
| `TC-LLM-xxx` | v2 다중 키 failover (제안) | `TC-LLM-003` |

---

## 4. v1 기능 테스트

### FR-001 이미지 일괄 업로드

| ID | 레벨 | 사전 조건 / 절차 | 기대 결과 | 자동화 |
|---|---|---|---|---|
| TC-FR-001-a | API | 유효 이미지 3장을 `files`로 업로드 → 상태 폴링 → 다운로드 | 202, `total=3`, `status=queued`; 최종 `done`; PDF 3페이지 | 예 |
| TC-FR-001-b | API | `files` 파트 없이 요청 | 400 `EMPTY_UPLOAD` | 예 |
| TC-FR-001-c | API | 이미지 1,001장 업로드 | 400 `TOO_MANY_FILES`, Job 미생성 | 예 |
| TC-FR-001-d | API | 51 MiB 이미지 1장 업로드 | 413 `FILE_TOO_LARGE`, 임시 디렉터리 삭제 | 예 |
| TC-FR-001-e | 단위 | 전체 누적 2 GiB 초과를 제한 로직에 주입 | 413 `TOTAL_SIZE_EXCEEDED` | 예 |
| TC-FR-001-f | API | `.heic` 파일 업로드 | 415 `UNSUPPORTED_IMAGE` | 예 |
| TC-FR-001-g | API | 손상 JPEG 업로드 | 422 `INVALID_IMAGE` | 예 |
| TC-FR-001-h | API | 정확히 1,000장 업로드(경계값) | 202, `total=1000` | 예(slow) |
| TC-FR-001-i | API | 0바이트 파일 업로드 | 422 `INVALID_IMAGE` | 예 |

### FR-002 페이지 순서 보존

| ID | 레벨 | 사전 조건 / 절차 | 기대 결과 | 자동화 |
|---|---|---|---|---|
| TC-FR-002-a | 단위 | `["img10","img2","img1"]` 자연 정렬 | `["img1","img2","img10"]` | 예 |
| TC-FR-002-b | API | `b,a,c` 순서로 multipart 전송 후 PDF 렌더링 | 1~3페이지 색상이 b,a,c 순서 | 예 |
| TC-FR-002-c | API | 동일 파일명 2개를 순서대로 업로드 | 두 파일 모두 페이지로 포함, 순서 유지 | 예 |
| TC-FR-002-d | 프론트 | 목록에서 순서 변경/삭제 후 업로드 | `FormData`의 `files` 순서가 화면 순서와 일치 | 수동/컴포넌트 |

### FR-003 페이지 크기와 배치

| ID | 레벨 | 사전 조건 / 절차 | 기대 결과 | 자동화 |
|---|---|---|---|---|
| TC-FR-003-a | 단위 | 세로 이미지 변환 | 페이지 595.276×841.89 pt | 예 |
| TC-FR-003-b | 단위 | 가로 이미지 변환 | 페이지 841.89×595.276 pt | 예 |
| TC-FR-003-c | 단위 | 정방형 이미지 변환 | 세로 A4 | 예 |
| TC-FR-003-d | 단위 | 이미지 N장 변환 | 페이지 수 == N | 예 |
| TC-FR-003-e | 단위 | 임의 비율 이미지 | rect가 페이지 내부, 중앙 정렬, 비율 유지(±0.5 pt) | 예 |
| TC-FR-003-f | 단위 | 10×10 소형 이미지 | 업스케일되어 페이지에 맞춤(비율 유지) | 예 |

### FR-004 EXIF 방향 보정

| ID | 레벨 | 사전 조건 / 절차 | 기대 결과 | 자동화 |
|---|---|---|---|---|
| TC-FR-004-a | 단위 | Orientation=6 JPEG 변환 | 회전 후 방향/픽셀이 `exif_transpose` 결과와 일치 | 예 |
| TC-FR-004-b | 단위 | Orientation=3 JPEG 변환 | 180° 회전 반영 | 예 |

### FR-005 투명도 처리

| ID | 레벨 | 사전 조건 / 절차 | 기대 결과 | 자동화 |
|---|---|---|---|---|
| TC-FR-005-a | 단위 | 투명 PNG 변환 후 픽셀 샘플 | 투명 영역이 흰색(255,255,255) | 예 |
| TC-FR-005-b | 단위 | 팔레트+transparency PNG 변환 | 투명 영역이 흰색 | 예 |
| TC-FR-005-c | 단위 | 반투명 빨강 PNG 변환 | 흰 배경 합성 결과(예: 분홍) | 예 |

### FR-006 변환 진행률

| ID | 레벨 | 사전 조건 / 절차 | 기대 결과 | 자동화 |
|---|---|---|---|---|
| TC-FR-006-a | 단위 | Job 상태 전이 시퀀스 실행 | `queued→converting→done`만 허용, 종료 후 재전이 없음 | 예 |
| TC-FR-006-b | API | 변환 중 50 ms 간격 폴링 | `processed` 단조 증가, 최종 `processed==total` | 예 |
| TC-FR-006-c | 단위 | PDF 빌더가 예외를 던지도록 주입 | `status=error`, `processed<total`, `error.code=CONVERSION_FAILED` | 예 |
| TC-FR-006-d | API | 완료 전/후 상태 조회 | 완료 전 `download_url=null`, 완료 후 URL 존재 | 예 |

### FR-007 PDF 다운로드

| ID | 레벨 | 사전 조건 / 절차 | 기대 결과 | 자동화 |
|---|---|---|---|---|
| TC-FR-007-a | API | `done` Job 다운로드 | 200, `application/pdf`, `Content-Disposition`, 페이지 수 일치 | 예 |
| TC-FR-007-b | API | `queued`/`converting` Job 다운로드 | 409 `JOB_NOT_READY` | 예 |
| TC-FR-007-c | API | 존재하지 않는 job_id 다운로드 | 404 `JOB_NOT_FOUND` | 예 |
| TC-FR-007-d | API | `error` Job 다운로드 | 409 `JOB_NOT_READY` | 예 |
| TC-FR-007-e | API | TTL 만료 Job 다운로드 | 404 `JOB_NOT_FOUND` | 예 |

### FR-008 PDF 텍스트 추출

| ID | 레벨 | 사전 조건 / 절차 | 기대 결과 | 자동화 |
|---|---|---|---|---|
| TC-FR-008-a | 단위 | 텍스트 2페이지 PDF 추출 | 페이지별 텍스트가 `strip()` 결과와 일치 | 예 |
| TC-FR-008-b | 단위 | 3페이지 중 1페이지가 빈 경우 | `text`는 비어 있지 않은 페이지를 `\n\n`로 연결 | 예 |
| TC-FR-008-c | 단위 | 텍스트 PDF 추출 | `page_count == len(pages)` | 예 |
| TC-FR-008-d | 단위 | 공백만 있는 페이지 | 해당 페이지 `text=""` | 예 |
| TC-FR-008-e | API | 텍스트 PDF 업로드 | `pages[].page`가 1부터 순서대로 | 예 |
| TC-FR-008-f | 단위 | 텍스트+이미지 혼합 PDF | 텍스트 페이지만 값 포함, `has_text=true` | 예 |

### FR-009 텍스트 없는 PDF 처리

| ID | 레벨 | 사전 조건 / 절차 | 기대 결과 | 자동화 |
|---|---|---|---|---|
| TC-FR-009-a | API | 이미지 전용 2페이지 PDF 추출 | 200, `has_text=false`, `text=""`, 모든 페이지 `""` | 예 |
| TC-FR-009-b | 단위 | 텍스트 1페이지 + 이미지 1페이지 | `has_text=true`, 이미지 페이지 `""` | 예 |

### FR-010 추출 텍스트 활용

| ID | 레벨 | 사전 조건 / 절차 | 기대 결과 | 자동화 |
|---|---|---|---|---|
| TC-FR-010-a | 프론트 | 복사 버튼 클릭(`navigator.clipboard` mock) | 전체 텍스트가 클립보드에 기록 | 컴포넌트 |
| TC-FR-010-b | 프론트 | `.txt` 다운로드 클릭 | UTF-8 Blob, 파일명/내용 일치 | 컴포넌트 |
| TC-FR-010-c | 프론트 | `text=""` 상태 | 복사/다운로드 비활성화 또는 안내 표시 | 컴포넌트 |

### FR-011 입력 검증

| ID | 레벨 | 사전 조건 / 절차 | 기대 결과 | 자동화 |
|---|---|---|---|---|
| TC-FR-011-a | API | 텍스트 바이트를 `.jpg`로 업로드 | 422 `INVALID_IMAGE` | 예 |
| TC-FR-011-b | API | 텍스트 파일을 텍스트 추출에 업로드 | 415 `UNSUPPORTED_PDF` | 예 |
| TC-FR-011-c | API | 손상 PDF 업로드 | 422 `INVALID_PDF` | 예 |
| TC-FR-011-d | API | 암호화 PDF 업로드 | 422 `INVALID_PDF` | 예 |
| TC-FR-011-e | API | 0페이지 PDF 업로드 | 422 `INVALID_PDF` | 예 |
| TC-FR-011-f | 단위 | 2,001페이지 PDF 제한 로직 | 422 `PDF_TOO_MANY_PAGES` | 예 |
| TC-FR-011-g | 단위 | 100 MiB 초과 PDF 제한 로직 | 413 `PDF_TOO_LARGE` | 예 |
| TC-FR-011-h | API | 대문자 확장자 `.JPG` 업로드 | 202, 정상 변환 | 예 |
| TC-FR-011-i | API | 선두 1024바이트 내 `%PDF-`가 없는 파일 | 415 `UNSUPPORTED_PDF` | 예 |

### FR-012 임시 파일 정리

| ID | 레벨 | 사전 조건 / 절차 | 기대 결과 | 자동화 |
|---|---|---|---|---|
| TC-FR-012-a | 통합 | `done` Job의 TTL 경과 후 정리 태스크 실행 | Job 디렉터리 삭제, 상태/다운로드 404 | 예 |
| TC-FR-012-b | 통합 | 변환 실패 Job | 부분 `output.pdf` 삭제, `status=error`, Job 디렉터리는 TTL까지 유지 | 예 |
| TC-FR-012-c | 통합 | 서버 종료(lifespan shutdown) | 모든 Job 디렉터리 삭제 | 예 |
| TC-FR-012-d | 통합 | `queued`/`converting` Job에 TTL 경과 | 정리 대상에서 제외 | 예 |
| TC-FR-012-e | API | 업로드 검증 실패 | 생성된 임시 디렉터리 즉시 삭제 | 예 |

### FR-013 헬스체크

| ID | 레벨 | 사전 조건 / 절차 | 기대 결과 | 자동화 |
|---|---|---|---|---|
| TC-FR-013-a | API | `GET /api/health` | 200, `status=ok`, `version` 비어 있지 않음 | 예 |
| TC-FR-013-b | API | 버전 형식 확인 | `major.minor.patch` 형태 | 예 |

### FR-014 로컬 전용 바인딩

| ID | 레벨 | 사전 조건 / 절차 | 기대 결과 | 자동화 |
|---|---|---|---|---|
| TC-FR-014-a | 스모크 | 기본 설정으로 서버 실행 | `127.0.0.1`에서만 수신 | 수동 |
| TC-FR-014-b | 단위 | `LOCALPDF_HOST` 오버라이드 | 설정 객체에 반영 | 예 |

### FR-015 오류 메시지

| ID | 레벨 | 사전 조건 / 절차 | 기대 결과 | 자동화 |
|---|---|---|---|---|
| TC-FR-015-a | API | 각 오류 코드 유발 | `{detail:{code,message}}` 형식, 한국어 메시지 | 예 |
| TC-FR-015-b | API | 내부 예외 주입 | 500 `INTERNAL_ERROR`, 스택/경로 미노출 | 예 |
| TC-FR-015-c | 단위 | API_SPEC의 모든 오류 코드 매핑 확인 | 코드→HTTP 상태 매핑 일치 | 예 |
| TC-FR-015-d | API | 응답/로그에 sentinel 비밀키 주입 | 응답/로그에 키 값 미포함 | 예 |

---

## 5. v1 비기능 테스트

| ID | 요구사항 | 절차 | 기대 결과 | 자동화 |
|---|---|---|---|---|
| TC-NFR-001 | NFR-001 | 100×100 이미지 500장 변환 | 500페이지, 순서 유지, 60초 이내 | 예(slow) |
| TC-NFR-002 | NFR-002 | 변환 워커 내 `Image.open` 동시 호출 수 계측 | 워커 내 동시에 열린 이미지 ≤ 1, 전체 이미지 동시 로드 없음 | 예 |
| TC-NFR-003 | NFR-003 | Job 3개 동시 제출 | 동시 `converting` Job ≤ 1 | 예 |
| TC-NFR-004 | NFR-004 | 파일명 `../../etc/passwd.jpg` 업로드 | Job 디렉터리 밖 파일 생성/접근 없음 | 예 |
| TC-NFR-005 | NFR-005 | 개수/크기/페이지 제한 | FR-001, FR-011 테스트로 검증 | 예 |
| TC-NFR-006 | NFR-006 | 허용/비허용 Origin으로 CORS 요청 | 허용 Origin만 `Access-Control-Allow-Origin` 반환 | 예 |
| TC-NFR-007 | NFR-007 | sentinel 키를 env에 주입 후 오류 유발 | 로그/응답에 sentinel 미포함 | 예 |
| TC-NFR-008 | NFR-008 | 최신 Chromium/Firefox/Safari에서 수동 실행 | 업로드/진행률/다운로드/텍스트 동작 | 수동 |
| TC-NFR-009 | NFR-009 | 500장 목록에서 순서 변경/삭제/진행률 확인 | UI 조작과 진행률 표시 정상 | 수동/컴포넌트 |
| TC-NFR-010 | NFR-010 | 네트워크 차단 상태로 `pytest backend` | 전체 통과 | CI |
| TC-NFR-011 | NFR-011 | `ruff check backend`, `tsc --noEmit`, `npm run build` | 모두 통과 | CI |

---

## 6. API 계약 테스트

| ID | 엔드포인트 | 절차 | 기대 결과 | 자동화 |
|---|---|---|---|---|
| TC-API-001 | `GET /api/health` | 호출 | 200, `{status,version}` | 예 |
| TC-API-002 | `POST /api/jobs` | 유효 파일 업로드 | 202, Job 스키마/필드 타입 일치 | 예 |
| TC-API-003 | `GET /api/jobs/{job_id}` | 각 상태 조회 | Job 스키마, `status` enum, `processed` 범위 | 예 |
| TC-API-004 | `GET /api/jobs/{job_id}/download` | 완료 Job 다운로드 | `Content-Type`, `Content-Disposition`, PDF 바이너리 | 예 |
| TC-API-005 | `POST /api/pdf/text` | 텍스트 PDF 업로드 | 200, `page_count/has_text/text/pages` 스키마 | 예 |
| TC-API-006 | 전체 | 오류 응답 형식 | `detail.code`, `detail.message` | 예 |
| TC-API-007 | `GET /api/jobs/{job_id}` | 없는 ID | 404 `JOB_NOT_FOUND` | 예 |
| TC-API-008 | `GET /api/jobs/{job_id}/download` | 미완료 ID | 409 `JOB_NOT_READY` | 예 |
| TC-API-009 | 전체 | `created_at` 확인 | ISO 8601 UTC(`...Z`) | 예 |
| TC-API-010 | `POST /api/jobs` | multipart 필드명 확인 | `files`만 사용, 순서 보존 | 예 |

---

## 7. v2 LLM 다중 키 failover 테스트 (제안)

> **상태: 제안.** `docs/REQUIREMENT.md`에 `FR-017`(다중 키 failover)과 관련 API 오류 코드가 반영된 뒤 v1 CI에 포함한다. 그 전까지는 mock 기반 단위 테스트로만 작성한다.

### 7.0 FR-016 요약 (v2, 명세 기존 항목)

| ID | 레벨 | 사전 조건 / 절차 | 기대 결과 | 자동화 |
|---|---|---|---|---|
| TC-FR-016-a | 단위 | provider mock이 정상 요약 반환 | 요약문/사용 provider/model 반환, 키 미노출 | 예 |
| TC-FR-016-b | API | API 키 미설정 상태로 요약 요청 | 400 `LLM_NOT_CONFIGURED` | 예 |
| TC-FR-016-c | 단위 | 텍스트 없음 | 요약 요청 거부 또는 빈 결과 안내 | 예 |

### 7.1 제안 요구사항

- **FR-017 (제안)**: provider별 키 풀을 구성하고, 통신 오류/키 무효/한도 초과/5xx/타임아웃 시 다음 키로 전환해 작업을 계속한다. 모델 설정 오류(404/410)와 요청 오류(일반 400)는 키 전환 대상이 아니다.
- **NFR-012 (제안)**: failover 포함 최대 지연은 `키 수 × 요청 타임아웃 + 백오프`를 넘지 않는다. 로그에 키 값을 남기지 않는다.

### 7.2 테스트 케이스

| ID | 레벨 | 사전 조건 / 절차 | 기대 결과 | 자동화 |
|---|---|---|---|---|
| TC-LLM-001 | 단위 | `GEMINI_API_KEY`, `GEMINI_API_KEY_1..N` 설정 | 순서 보존, 중복 제거, 빈 값 제외 | 예 |
| TC-LLM-002 | 단위 | `NVIDIA_API_KEY_1..N` 설정 | 순서 보존, 중복 제거 | 예 |
| TC-LLM-003 | 단위 | key1 401, key2 200 (mock) | key2로 재시도, 논리 호출 1회 성공, key1 비활성 | 예 |
| TC-LLM-004 | 단위 | key1 403, key2 200 | key2로 전환 | 예 |
| TC-LLM-005 | 단위 | key1 429 + `Retry-After: 30`(또는 RetryInfo), key2 200 | key2 성공, key1 쿨다운 30초 | 예 |
| TC-LLM-006 | 단위 | key1 500, key2 200 | key2로 전환 | 예 |
| TC-LLM-007 | 단위 | key1 타임아웃, key2 200 | key2로 전환 | 예 |
| TC-LLM-008 | 단위 | key1 일반 400(요청 오류) | 키 전환 없이 즉시 실패 | 예 |
| TC-LLM-009 | 단위 | Gemini 400 `API key not valid` | 키 실패로 분류해 다음 키 전환 | 예 |
| TC-LLM-010 | 단위 | key1 404/410(모델 EOL/미지원) | 키 전환 없이 모델 설정 오류 반환 | 예 |
| TC-LLM-011 | 단위 | 모든 키 401 | `LLM_ALL_KEYS_FAILED`, 시도 횟수/마지막 오류 포함 | 예 |
| TC-LLM-012 | 단위 | 실패 후 키가 성공 | 쿨다운/실패 카운트 초기화 | 예 |
| TC-LLM-013 | 단위 | 키 없음 | `LLM_NOT_CONFIGURED` | 예 |
| TC-LLM-014 | 단위 | 3청크 요약, 청크2에서 key1 실패 | key2로 청크2 완료, 청크1 결과 유지, 성공 호출 중복 없음 | 예 |
| TC-LLM-015 | 단위 | 429 + `Retry-After`/RetryInfo | 지정 시간 이후에만 해당 키 재사용 | 예 |
| TC-LLM-016 | 단위 | 동시 요청 2개, key1 쿨다운 | 두 요청 모두 쿨다운 키를 사용하지 않음 | 예 |
| TC-LLM-017 | 단위 | 실패 로그 캡처 | provider/key_index/attempt/오류 분류 기록, 키 값 미기록 | 예 |
| TC-LLM-018 | 단위 | 키 3개, 모두 성공 가능 | 시도 순서가 설정 순서와 일치 | 예 |
| TC-LLM-019 | 단위 | `LLM_PROVIDER=gemini`/`nvidia` | 해당 provider 풀만 사용 | 예 |
| TC-LLM-020 | 단위 | 모든 키 실패 후 부분 결과 존재 | 완료 청크 수와 마지막 오류를 보존한 오류 반환 | 예 |
| TC-LLM-021 | API | `POST /api/summarize`에서 모든 키 실패 | 502 `LLM_ALL_KEYS_FAILED`(제안) | 예 |
| TC-LLM-022 | API | 키 미설정 상태로 요약 요청 | 400 `LLM_NOT_CONFIGURED` | 예 |
| TC-LLM-023 | 수동 | 실제 key1 정상 + key2 무효 | key1로 작업 완료, key2는 건너뜀 | 수동 |
| TC-LLM-024 | 수동 | 실제 key1 무효 + key2 정상 | key2로 작업 완료 | 수동 |
| TC-LLM-025 | API | 모든 키가 429 반환 | 429 `LLM_RATE_LIMITED`(Retry-After 포함) | 예 |
| TC-LLM-026 | API | 모든 키가 5xx 반환 | 502 `LLM_UPSTREAM_ERROR` | 예 |
| TC-LLM-027 | 단위 | 모든 키 타임아웃 | 총 지연 ≤ `키 수 × 타임아웃 + 백오프` | 예 |

---

## 8. TDD 실행 순서

| 순서 | 대상 | 선행 테스트 | 완료 기준 |
|---|---|---|---|
| 1 | 변환 코어 | FR-003, FR-004, FR-005, FR-002 | 단위 테스트 통과 |
| 2 | 업로드/Job | FR-001, FR-006, FR-007, FR-012 | API 통합 통과 |
| 3 | 텍스트 추출 | FR-008, FR-009, FR-011 | 단위/API 통과 |
| 4 | 오류/보안 | FR-013, FR-014, FR-015, NFR-004~007 | 통합/스모크 통과 |
| 5 | 프론트 | FR-002-d, FR-006, FR-010, NFR-009 | 타입/빌드/수동 통과 |
| 6 | 성능 | NFR-001~003 | slow 테스트 통과 |
| 7 | v2 failover | TC-FR-016-a~c, TC-LLM-001~027 | 명세 반영 후 구현 |

## 9. 검증 체크리스트

```bash
# 구현 후
pytest backend
pytest backend -m "not slow"
ruff check backend
cd frontend && npx tsc --noEmit && npm run build
```

검증 항목(작성 시 자동 대조 완료: **PASS**):
- [x] `docs/REQUIREMENT.md`의 모든 v1 FR/NFR에 테스트가 1개 이상 있다.
- [x] `docs/API_SPEC.md`의 모든 엔드포인트에 테스트가 있다.
- [x] `docs/API_SPEC.md`의 모든 오류 코드에 테스트가 있다.
- [x] 테스트 ID가 중복되지 않는다.
- [x] v2 LLM 테스트는 "제안"으로 표시되어 v1 CI와 분리된다.
- [x] 테스트가 외부 네트워크/실제 키에 의존하지 않는다.

## 10. 추적표

| 요구사항 | 테스트 ID |
|---|---|
| FR-001 | TC-FR-001-a~i |
| FR-002 | TC-FR-002-a~d |
| FR-003 | TC-FR-003-a~f |
| FR-004 | TC-FR-004-a~b |
| FR-005 | TC-FR-005-a~c |
| FR-006 | TC-FR-006-a~d |
| FR-007 | TC-FR-007-a~e |
| FR-008 | TC-FR-008-a~f |
| FR-009 | TC-FR-009-a~b |
| FR-010 | TC-FR-010-a~c |
| FR-011 | TC-FR-011-a~i |
| FR-012 | TC-FR-012-a~e |
| FR-013 | TC-FR-013-a~b |
| FR-014 | TC-FR-014-a~b |
| FR-015 | TC-FR-015-a~d |
| NFR-001 | TC-NFR-001 |
| NFR-002 | TC-NFR-002 |
| NFR-003 | TC-NFR-003 |
| NFR-004 | TC-NFR-004 |
| NFR-005 | TC-NFR-005, TC-FR-001-*, TC-FR-011-* |
| NFR-006 | TC-NFR-006 |
| NFR-007 | TC-NFR-007 |
| NFR-008 | TC-NFR-008 |
| NFR-009 | TC-NFR-009 |
| NFR-010 | TC-NFR-010 |
| NFR-011 | TC-NFR-011 |
| FR-016 | TC-FR-016-a~c |
| FR-017 (제안) | TC-LLM-001~027 |
| NFR-012 (제안) | TC-LLM-027 |

## 11. 미해결/가정

- `FR-017`(다중 키 failover)과 `LLM_ALL_KEYS_FAILED` 오류 코드는 아직 `docs/REQUIREMENT.md`/`docs/API_SPEC.md`에 없다. v2 구현 전에 명세를 먼저 갱신한다.
- 실제 키 테스트 결과: Gemini 키는 정상, NVIDIA key 1은 정상, key 2는 형식/인증 오류. `GEMINI_MODEL`과 `NVIDIA_MODEL`은 현재 EOL/미지원 값이므로 교체가 필요하다.
- 확인된 동작 모델: Gemini `gemini-3.1-flash-lite`/`gemini-3.5-flash`, NVIDIA `deepseek-ai/deepseek-v4.1-flash`. `gemini-3.7/3.8-flash`는 이 환경에서 타임아웃되었다.
- OCR, HEIC/AVIF, 다중 프레임 확장은 범위 외다.
