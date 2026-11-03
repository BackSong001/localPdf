import React, { useState, useEffect, useRef } from 'react';

interface JobError {
  code: string;
  message: string;
}

interface JobSnapshot {
  job_id: string;
  status: 'queued' | 'converting' | 'done' | 'error';
  total: number;
  processed: number;
  error: JobError | null;
  created_at: string;
  download_url: string | null;
  markdown_url: string | null;
}

interface SummaryResult {
  summary: string;
  provider: string;
  model: string;
}

interface PdfOcrSnapshot {
  job_id: string;
  status: 'queued' | 'converting' | 'done' | 'error';
  total: number;
  processed: number;
  error: { code: string; message: string } | null;
  download_url: string | null;
}

const App: React.FC = () => {
  const [files, setFiles] = useState<File[]>([]);
  const [jobId, setJobId] = useState<string>('');
  const [snapshot, setSnapshot] = useState<JobSnapshot | null>(null);
  const [errorMessage, setErrorMessage] = useState<string>('');
  const [isUploading, setIsUploading] = useState<boolean>(false);
  const [isDragOver, setIsDragOver] = useState<boolean>(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // LLM Summary state
  const [isSummarizing, setIsSummarizing] = useState<boolean>(false);
  const [summaryResult, setSummaryResult] = useState<SummaryResult | null>(null);
  const [summaryError, setSummaryError] = useState<string>('');
  const [copied, setCopied] = useState<boolean>(false);
  const [pdfFile, setPdfFile] = useState<File | null>(null);
  const [isPdfOcr, setIsPdfOcr] = useState<boolean>(false);
  const [pdfDownloadUrl, setPdfDownloadUrl] = useState<string>('');
  const [pdfError, setPdfError] = useState<string>('');
  const [pdfOcrSnapshot, setPdfOcrSnapshot] = useState<PdfOcrSnapshot | null>(null);
  const pdfInputRef = useRef<HTMLInputElement>(null);

  // Poll job status
  useEffect(() => {
    if (!jobId) return;

    let isSubscribed = true;
    const interval = setInterval(async () => {
      try {
        const res = await fetch(`/api/jobs/${jobId}`);
        if (!res.ok) {
          const errData = await res.json().catch(() => null);
          const msg =
            (errData?.detail && typeof errData.detail === 'object'
              ? errData.detail.message
              : errData?.detail) || '작업 상태를 조회하지 못했습니다.';
          throw new Error(msg);
        }

        const data: JobSnapshot = await res.json();
        if (!isSubscribed) return;
        setSnapshot(data);

        if (data.status === 'done') {
          clearInterval(interval);
        } else if (data.status === 'error') {
          clearInterval(interval);
          const reason = data.error?.message || '알 수 없는 오류가 발생했습니다.';
          setErrorMessage(`PDF 생성 실패: ${reason} (코드: ${data.error?.code || 'ERROR'})`);
        }
      } catch (err: any) {
        if (!isSubscribed) return;
        setErrorMessage(err.message || '상태 확인 중 오류가 발생했습니다.');
        clearInterval(interval);
      }
    }, 800);

    return () => {
      isSubscribed = false;
      clearInterval(interval);
    };
  }, [jobId]);

  const handleFiles = (incomingFiles: FileList | null) => {
    if (!incomingFiles || incomingFiles.length === 0) return;
    const fileArray = Array.from(incomingFiles);
    setFiles(fileArray);
    setErrorMessage('');
    setSnapshot(null);
    setJobId('');
    setSummaryResult(null);
    setSummaryError('');
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    handleFiles(e.target.files);
  };

  const handleDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragOver(false);
    handleFiles(e.dataTransfer.files);
  };

  const handleDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragOver(true);
  };

  const handleDragLeave = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragOver(false);
  };

  const formatBytes = (bytes: number) => {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
  };

  const totalSize = files.reduce((acc, f) => acc + f.size, 0);

  const startUploadAndConvert = async () => {
    if (files.length === 0) {
      setErrorMessage('변환할 이미지 파일을 1장 이상 선택해 주세요.');
      return;
    }

    setIsUploading(true);
    setErrorMessage('');
    setSnapshot(null);
    setSummaryResult(null);
    setSummaryError('');

    const formData = new FormData();
    files.forEach((file) => {
      formData.append('files', file);
    });

    try {
      const res = await fetch('/api/jobs', {
        method: 'POST',
        body: formData,
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => null);
        let errorDetail = '업로드 및 변환 요청에 실패했습니다.';
        if (errData?.detail) {
          if (typeof errData.detail === 'object') {
            errorDetail = errData.detail.message || JSON.stringify(errData.detail);
          } else {
            errorDetail = errData.detail;
          }
        }
        throw new Error(errorDetail);
      }

      const initialJob: JobSnapshot = await res.json();
      setJobId(initialJob.job_id);
      setSnapshot(initialJob);
    } catch (err: any) {
      setErrorMessage(err.message || '서버와의 통신에 실패했습니다.');
    } finally {
      setIsUploading(false);
    }
  };

  const handleSummarize = async () => {
    if (!jobId) return;
    setIsSummarizing(true);
    setSummaryError('');

    try {
      const res = await fetch(`/api/jobs/${jobId}/summarize`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => null);
        if (errData?.detail?.code === 'LLM_NOT_CONFIGURED') {
          throw new Error('💡 LLM API 키가 설정되지 않았습니다. .env 파일에 GEMINI_API_KEY 또는 NVIDIA_API_KEY를 등록해 주세요.');
        }
        const msg = errData?.detail?.message || '요약 생성에 실패했습니다.';
        throw new Error(msg);
      }

      const data: SummaryResult = await res.json();
      setSummaryResult(data);
    } catch (err: any) {
      setSummaryError(err.message || '요약 요청 중 오류가 발생했습니다.');
    } finally {
      setIsSummarizing(false);
    }
  };

  const handleCopySummary = () => {
    if (!summaryResult?.summary) return;
    navigator.clipboard.writeText(summaryResult.summary);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleReset = () => {
    setFiles([]);
    setJobId('');
    setSnapshot(null);
    setErrorMessage('');
    setSummaryResult(null);
    setSummaryError('');
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const handlePdfOcr = async () => {
    if (!pdfFile) return;
    setIsPdfOcr(true);
    setPdfError('');
    setPdfDownloadUrl('');
    setPdfOcrSnapshot(null);

    const formData = new FormData();
    formData.append('file', pdfFile);
    try {
      const res = await fetch('/api/pdf/ocr', { method: 'POST', body: formData });
      if (!res.ok) {
        const data = await res.json().catch(() => null);
        throw new Error(data?.detail?.message || 'PDF 텍스트 레이어 생성에 실패했습니다.');
      }
      const created: PdfOcrSnapshot = await res.json();
      setPdfOcrSnapshot(created);
      while (true) {
        await new Promise((resolve) => setTimeout(resolve, 500));
        const statusResponse = await fetch(`/api/pdf/ocr/${created.job_id}`);
        const status: PdfOcrSnapshot = await statusResponse.json();
        setPdfOcrSnapshot(status);
        if (status.status === 'done') {
          setPdfDownloadUrl(status.download_url || '');
          break;
        }
        if (status.status === 'error') {
          throw new Error(status.error?.message || 'PDF OCR 처리에 실패했습니다.');
        }
      }
    } catch (err: any) {
      setPdfError(err.message || 'PDF OCR 요청 중 오류가 발생했습니다.');
    } finally {
      setIsPdfOcr(false);
    }
  };

  // Progress percentage calculation
  const total = snapshot?.total || files.length || 1;
  const processed = snapshot?.processed || 0;
  const percent = snapshot?.status === 'done' ? 100 : Math.min(Math.round((processed / total) * 100), 99);

  return (
    <div className="container">
      <div className="header">
        <h1>📑 LocalPDF 변환 & 텍스트 추출기</h1>
        <p>로컬 단일 환경에서 대용량 이미지(최대 1,000장)를 검색 가능한 PDF로 변환하고, 텍스트 추출 및 요약을 지원합니다.</p>
      </div>

      {/* Upload Zone */}
      <div
        className={`upload-zone ${isDragOver ? 'dragover' : ''}`}
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onClick={() => fileInputRef.current?.click()}
      >
        <input
          ref={fileInputRef}
          type="file"
          className="file-input"
          multiple
          accept=".jpg,.jpeg,.png,.webp,.bmp,.tif,.tiff,image/*"
          onChange={handleFileChange}
          disabled={isUploading || (snapshot !== null && snapshot.status !== 'done' && snapshot.status !== 'error')}
        />
        <div className="upload-icon">📁</div>
        <div className="upload-text">이미지를 드래그하여 놓거나 클릭하여 선택하세요</div>
        <div className="upload-subtext">지원 형식: JPG, PNG, WEBP, BMP, TIFF (RapidOCR 자동 텍스트 레이어 주입)</div>
      </div>

      <section className="pdf-ocr-panel" aria-labelledby="pdf-ocr-title">
        <div>
          <h2 id="pdf-ocr-title">기존 PDF에 텍스트 레이어 추가</h2>
          <p>스캔 PDF를 OCR 처리해 검색과 복사가 가능한 새 PDF를 만듭니다.</p>
        </div>
        <input
          ref={pdfInputRef}
          type="file"
          className="pdf-file-input"
          accept="application/pdf,.pdf"
          onChange={(event) => {
            setPdfFile(event.target.files?.[0] || null);
            setPdfDownloadUrl('');
            setPdfError('');
            setPdfOcrSnapshot(null);
          }}
        />
        <div className="pdf-ocr-actions">
          <button type="button" className="btn btn-secondary" onClick={() => pdfInputRef.current?.click()}>
            {pdfFile ? pdfFile.name : 'PDF 선택'}
          </button>
          <button type="button" className="btn btn-primary" onClick={handlePdfOcr} disabled={!pdfFile || isPdfOcr}>
            {isPdfOcr ? 'OCR 처리 중...' : '텍스트 레이어 추가'}
          </button>
        </div>
        {pdfOcrSnapshot && (pdfOcrSnapshot.status === 'queued' || pdfOcrSnapshot.status === 'converting') && (
          <>
            <div className="progress-container">
              <div
                className="progress-bar animated"
                style={{ width: `${pdfOcrSnapshot.total ? Math.round((pdfOcrSnapshot.processed / pdfOcrSnapshot.total) * 100) : 0}%` }}
              />
            </div>
            <div className="progress-info">
              <span>페이지 {pdfOcrSnapshot.processed} / {pdfOcrSnapshot.total} 처리 중</span>
              <span>{pdfOcrSnapshot.total ? Math.round((pdfOcrSnapshot.processed / pdfOcrSnapshot.total) * 100) : 0}%</span>
            </div>
          </>
        )}
        {pdfError && <div className="pdf-ocr-error">{pdfError}</div>}
        {pdfDownloadUrl && (
          <a href={pdfDownloadUrl} download="searchable.pdf" className="btn btn-success pdf-download">
            검색 가능한 PDF 다운로드
          </a>
        )}
      </section>

      {/* Selected Files Summary */}
      {files.length > 0 && (
        <div className="file-summary">
          <span>
            선택된 파일: <strong>{files.length}장</strong> ({formatBytes(totalSize)})
          </span>
          <button
            type="button"
            className="btn btn-secondary"
            style={{ padding: '0.35rem 0.75rem', fontSize: '0.85rem' }}
            onClick={(e) => {
              e.stopPropagation();
              handleReset();
            }}
            disabled={isUploading || (snapshot !== null && (snapshot.status === 'queued' || snapshot.status === 'converting'))}
          >
            초기화
          </button>
        </div>
      )}

      {/* Action Buttons */}
      <div className="actions">
        <button
          className="btn btn-primary"
          onClick={startUploadAndConvert}
          disabled={
            files.length === 0 ||
            isUploading ||
            (snapshot !== null && (snapshot.status === 'queued' || snapshot.status === 'converting'))
          }
        >
          {isUploading
            ? '📤 이미지 업로드 중...'
            : snapshot?.status === 'converting' || snapshot?.status === 'queued'
            ? '⚙️ PDF 변환 & OCR 텍스트 레이어 생성 중...'
            : '🚀 Searchable PDF 변환 시작'}
        </button>
      </div>

      {/* Error Alert Box */}
      {errorMessage && (
        <div className="alert alert-danger">
          <span className="alert-icon">⚠️</span>
          <div>
            <strong>오류가 발생했습니다:</strong>
            <div>{errorMessage}</div>
          </div>
        </div>
      )}

      {/* Progress & Status Card */}
      {snapshot && (
        <div className="status-card">
          <div className="status-header">
            <span style={{ fontWeight: 600, fontSize: '0.95rem' }}>변환 진행 상태</span>
            <span className={`badge badge-${snapshot.status}`}>
              {snapshot.status === 'queued' && '대기 중'}
              {snapshot.status === 'converting' && 'OCR 및 PDF 생성 중'}
              {snapshot.status === 'done' && '변환 완료'}
              {snapshot.status === 'error' && '변환 실패'}
            </span>
          </div>

          {/* Visual Progress Bar */}
          <div className="progress-container">
            <div
              className={`progress-bar ${snapshot.status === 'converting' ? 'animated' : ''}`}
              style={{
                width: `${percent}%`,
                backgroundColor:
                  snapshot.status === 'error'
                    ? '#ef4444'
                    : snapshot.status === 'done'
                    ? '#10b981'
                    : undefined,
              }}
            />
          </div>

          <div className="progress-info">
            <span>
              {snapshot.status === 'done'
                ? '모든 페이지의 검색 가능한 텍스트 레이어 및 PDF가 생성되었습니다.'
                : snapshot.status === 'error'
                ? '변환 작업이 중단되었습니다.'
                : `${snapshot.processed} / ${snapshot.total} 장 OCR 처리 완료`}
            </span>
            <span style={{ fontWeight: 600 }}>{percent}%</span>
          </div>

          {/* Success Box with Dual Download & LLM Summary */}
          {snapshot.status === 'done' && (
            <div className="done-box">
              <h3>🎉 변환이 완료되었습니다!</h3>
              <p>텍스트 검색/복사가 가능한 Searchable PDF와 추출된 Markdown 문서가 준비되었습니다.</p>
              
              <div className="download-grid">
                <a
                  href={snapshot.download_url || `/api/jobs/${snapshot.job_id}/download`}
                  download={`localpdf-${snapshot.job_id}.pdf`}
                  className="btn btn-success"
                >
                  📥 Searchable PDF 다운로드
                </a>

                {snapshot.markdown_url && (
                  <a
                    href={snapshot.markdown_url}
                    download={`localpdf-${snapshot.job_id}.md`}
                    className="btn btn-secondary"
                  >
                    📄 Markdown(.md) 다운로드
                  </a>
                )}
              </div>

              {/* LLM Summary Trigger Button */}
              <button
                type="button"
                className="btn btn-ai"
                onClick={handleSummarize}
                disabled={isSummarizing}
                style={{ width: '100%', marginTop: '0.5rem' }}
              >
                {isSummarizing ? '🤖 AI가 문서를 분석하고 요약하는 중...' : '✨ 무료 LLM으로 핵심 내용 요약하기'}
              </button>
            </div>
          )}

          {/* Summary Error Alert */}
          {summaryError && (
            <div className="alert alert-danger" style={{ marginTop: '1rem' }}>
              <span className="alert-icon">ℹ️</span>
              <div>{summaryError}</div>
            </div>
          )}

          {/* LLM Summary Result Card */}
          {summaryResult && (
            <div className="summary-card">
              <div className="summary-header">
                <div>
                  <strong style={{ color: '#4f46e5' }}>🤖 AI 문서 요약 결과</strong>
                  <span style={{ fontSize: '0.8rem', color: '#6b7280', marginLeft: '0.5rem' }}>
                    ({summaryResult.provider.toUpperCase()} · {summaryResult.model})
                  </span>
                </div>
                <button type="button" className="btn-copy" onClick={handleCopySummary}>
                  {copied ? '✓ 복사됨!' : '📋 요약 복사'}
                </button>
              </div>
              <div className="summary-content">{summaryResult.summary}</div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default App;
