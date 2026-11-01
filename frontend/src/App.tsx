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
}

const App: React.FC = () => {
  const [files, setFiles] = useState<File[]>([]);
  const [jobId, setJobId] = useState<string>('');
  const [snapshot, setSnapshot] = useState<JobSnapshot | null>(null);
  const [errorMessage, setErrorMessage] = useState<string>('');
  const [isUploading, setIsUploading] = useState<boolean>(false);
  const [isDragOver, setIsDragOver] = useState<boolean>(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

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

  const handleReset = () => {
    setFiles([]);
    setJobId('');
    setSnapshot(null);
    setErrorMessage('');
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  // Progress percentage calculation
  const total = snapshot?.total || files.length || 1;
  const processed = snapshot?.processed || 0;
  const percent = snapshot?.status === 'done' ? 100 : Math.min(Math.round((processed / total) * 100), 99);

  return (
    <div className="container">
      <div className="header">
        <h1>📑 LocalPDF 변환기</h1>
        <p>로컬 단일 환경에서 대용량 이미지(최대 1,000장)를 신속하게 하나의 PDF로 묶어줍니다.</p>
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
        <div className="upload-subtext">지원 형식: JPG, PNG, WEBP, BMP, TIFF (최대 1,000장 / 2GB)</div>
      </div>

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
            ? '⚙️ PDF 변환 처리 중...'
            : '🚀 PDF 생성 시작'}
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
            <span style={{ fontWeight: 600, fontSize: '0.95rem' }}>진행 상태</span>
            <span className={`badge badge-${snapshot.status}`}>
              {snapshot.status === 'queued' && '대기 중'}
              {snapshot.status === 'converting' && 'PDF 변환 중'}
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
                ? '모든 페이지가 생성되었습니다.'
                : snapshot.status === 'error'
                ? '변환 작업이 중단되었습니다.'
                : `${snapshot.processed} / ${snapshot.total} 장 처리 완료`}
            </span>
            <span style={{ fontWeight: 600 }}>{percent}%</span>
          </div>

          {/* Success Box with Download Button */}
          {snapshot.status === 'done' && (
            <div className="done-box">
              <h3>🎉 PDF 생성이 완료되었습니다!</h3>
              <p>총 {snapshot.total}장의 이미지가 성공적으로 하나의 PDF로 변환되었습니다.</p>
              <a
                href={snapshot.download_url || `/api/jobs/${snapshot.job_id}/download`}
                download={`localpdf-${snapshot.job_id}.pdf`}
                className="btn btn-success"
                style={{ width: '100%' }}
              >
                📥 생성된 PDF 다운로드
              </a>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default App;
