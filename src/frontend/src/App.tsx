import { useMemo, useState } from 'react'

type JobStatus = 'queued' | 'processing' | 'completed' | 'failed'
type MediaKind = 'audio' | 'video'
type Mode = 'bleep' | 'audio-only' | 'full'

type JobCreateResponse = {
  job_id: string
  status: JobStatus
  media_type: MediaKind
  mode: Mode
  message: string
}

type JobStatusResponse = {
  job_id: string
  status: JobStatus
  media_type: MediaKind
  mode: Mode
  message: string
  filename: string
  download_url: string | null
  error: string | null
}

type CompletedJob = {
  id: string
  filename: string
  mode: Mode
  downloadUrl: string
}

const API_BASE = import.meta.env.VITE_API_BASE_URL || ''

const audioExt = new Set(['wav', 'mp3', 'm4a', 'aac', 'flac', 'ogg'])
const videoExt = new Set(['mp4', 'mov', 'mkv', 'avi', 'webm'])

function detectKind(file: File | null): MediaKind | null {
  if (!file) {
    return null
  }
  const ext = file.name.split('.').pop()?.toLowerCase() || ''
  if (audioExt.has(ext)) {
    return 'audio'
  }
  if (videoExt.has(ext)) {
    return 'video'
  }
  return null
}

function modeLabel(mode: Mode): string {
  if (mode === 'bleep') {
    return 'Bleep out foul language'
  }
  if (mode === 'audio-only') {
    return 'Bleep out audio only'
  }
  return 'Bleep out subtitles and audio'
}

async function createJob(file: File, mode: Mode): Promise<JobCreateResponse> {
  const form = new FormData()
  form.append('file', file)
  form.append('mode', mode)

  const res = await fetch(`${API_BASE}/api/v1/jobs`, {
    method: 'POST',
    body: form,
  })

  if (!res.ok) {
    const detail = await res.json().catch(() => ({}))
    throw new Error(detail.detail || 'Unable to start filtering job.')
  }

  return (await res.json()) as JobCreateResponse
}

async function fetchJob(jobId: string): Promise<JobStatusResponse> {
  const res = await fetch(`${API_BASE}/api/v1/jobs/${jobId}`)
  if (!res.ok) {
    throw new Error('Unable to fetch job status.')
  }
  return (await res.json()) as JobStatusResponse
}

function App() {
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [currentJobId, setCurrentJobId] = useState<string | null>(null)
  const [isProcessing, setIsProcessing] = useState(false)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)
  const [notification, setNotification] = useState<string | null>(null)
  const [completedJobs, setCompletedJobs] = useState<CompletedJob[]>([])

  const mediaKind = useMemo(() => detectKind(selectedFile), [selectedFile])

  const startJob = async (mode: Mode) => {
    if (!selectedFile) {
      return
    }

    setNotification(null)
    setErrorMessage(null)

    try {
      const created = await createJob(selectedFile, mode)
      setCurrentJobId(created.job_id)
      setIsProcessing(true)
      setSelectedFile(null)

      const poll = window.setInterval(async () => {
        try {
          const job = await fetchJob(created.job_id)

          if (job.status === 'completed') {
            window.clearInterval(poll)
            setIsProcessing(false)
            if (job.download_url) {
              setCompletedJobs((prev) => [
                {
                  id: created.job_id,
                  filename: job.filename,
                  mode: job.mode,
                  downloadUrl: `${API_BASE}${job.download_url}`,
                },
                ...prev,
              ])
            }
            setNotification('Filtering complete. Your download is ready.')
            setCurrentJobId(null)
          }

          if (job.status === 'failed') {
            window.clearInterval(poll)
            setIsProcessing(false)
            setErrorMessage(job.error || 'Filtering failed.')
            setCurrentJobId(null)
          }
        } catch {
          window.clearInterval(poll)
          setIsProcessing(false)
          setErrorMessage('Status polling failed. Please try again.')
          setCurrentJobId(null)
        }
      }, 2000)
    } catch (err) {
      if (err instanceof Error) {
        setErrorMessage(err.message)
      } else {
        setErrorMessage('Unable to submit file.')
      }
    }
  }

  return (
    <main className="min-h-screen bg-[radial-gradient(1200px_500px_at_20%_-20%,#fecdd3,transparent),radial-gradient(1200px_500px_at_80%_120%,#bae6fd,transparent),#fff8f2] px-4 py-10 text-slate-900">
      <div className="mx-auto w-full max-w-3xl">
        <header className="mb-8">
          <p className="mb-2 inline-flex rounded-full border border-amber-300 bg-amber-100 px-3 py-1 text-xs font-semibold tracking-[0.2em] text-amber-800">
            VIDEO CONTENT FILTER
          </p>
          <h1 className="text-4xl font-black leading-tight md:text-5xl">
            Remove profanity from audio and video in one click.
          </h1>
          <p className="mt-3 max-w-2xl text-sm text-slate-700 md:text-base">
            Upload a single file, choose a filtering action, and download the cleaned result when processing completes.
          </p>
        </header>

        {notification && (
          <div className="mb-6 rounded-2xl border border-emerald-300 bg-emerald-50 px-4 py-3 text-sm font-semibold text-emerald-800">
            {notification}
          </div>
        )}

        {errorMessage && (
          <div className="mb-6 rounded-2xl border border-rose-300 bg-rose-50 px-4 py-3 text-sm font-semibold text-rose-700">
            {errorMessage}
          </div>
        )}

        {completedJobs.length > 0 && (
          <section className="mb-6 space-y-3">
            {completedJobs.map((job) => (
              <article
                key={job.id}
                className="flex flex-col gap-3 rounded-3xl border border-slate-200 bg-white/95 p-5 shadow-sm md:flex-row md:items-center md:justify-between"
              >
                <div>
                  <h2 className="text-base font-bold">{job.filename}</h2>
                  <p className="text-sm text-slate-600">{modeLabel(job.mode)}</p>
                </div>
                <a
                  className="inline-flex items-center justify-center rounded-xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white transition hover:bg-slate-700"
                  href={job.downloadUrl}
                >
                  Download filtered file
                </a>
              </article>
            ))}
          </section>
        )}

        {isProcessing ? (
          <section className="rounded-3xl border border-slate-200 bg-white p-10 text-center shadow-sm">
            <p className="text-xs font-semibold tracking-[0.3em] text-slate-500">JOB {currentJobId}</p>
            <h2 className="mt-4 text-2xl font-black text-slate-900">filtering profanity</h2>
            <p className="mt-2 text-sm text-slate-600">This can take a little while for longer videos.</p>
          </section>
        ) : (
          <section className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm md:p-8">
            <label
              htmlFor="media-upload"
              className="mb-4 block rounded-2xl border-2 border-dashed border-slate-300 bg-slate-50 p-8 text-center transition hover:border-slate-400"
            >
              <span className="block text-sm font-semibold text-slate-600">Upload one audio or video file</span>
              <span className="mt-2 block text-lg font-bold text-slate-900">
                {selectedFile ? selectedFile.name : 'Click to choose a file'}
              </span>
              <span className="mt-1 block text-xs text-slate-500">Single file only. Multi-upload is disabled.</span>
            </label>

            <input
              id="media-upload"
              type="file"
              accept="audio/*,video/*"
              className="hidden"
              onChange={(event) => {
                const next = event.target.files?.[0] || null
                setSelectedFile(next)
                setErrorMessage(null)
                setNotification(null)
              }}
            />

            {!selectedFile && <p className="text-sm text-slate-600">Choose a file to see available actions.</p>}

            {selectedFile && mediaKind === null && (
              <p className="text-sm font-semibold text-rose-700">Unsupported file type. Please choose audio or video.</p>
            )}

            {selectedFile && mediaKind === 'audio' && (
              <button
                type="button"
                className="mt-4 inline-flex w-full items-center justify-center rounded-xl bg-amber-500 px-4 py-3 text-sm font-bold text-amber-950 transition hover:bg-amber-400"
                onClick={() => {
                  void startJob('bleep')
                }}
              >
                Bleep out foul language
              </button>
            )}

            {selectedFile && mediaKind === 'video' && (
              <div className="mt-4 grid gap-3 md:grid-cols-2">
                <button
                  type="button"
                  className="inline-flex items-center justify-center rounded-xl bg-sky-500 px-4 py-3 text-sm font-bold text-sky-950 transition hover:bg-sky-400"
                  onClick={() => {
                    void startJob('audio-only')
                  }}
                >
                  Bleep out audio only
                </button>
                <button
                  type="button"
                  className="inline-flex items-center justify-center rounded-xl bg-fuchsia-500 px-4 py-3 text-sm font-bold text-fuchsia-950 transition hover:bg-fuchsia-400"
                  onClick={() => {
                    void startJob('full')
                  }}
                >
                  Bleep out subtitles and audio
                </button>
              </div>
            )}
          </section>
        )}
      </div>
    </main>
  )
}

export default App
