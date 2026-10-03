import { useEffect, useMemo, useRef, useState } from 'react'
import { confirmUpload, createJob, fetchStatus, uploadFile } from './api'
import type { JobStatusResponse } from './api'
import { remainingSeconds } from './estimate'
import { overallProgress, stageProgress } from './stages'
import StatusCard from './StatusCard'
import type { Phase } from './StatusCard'

type MediaKind = 'audio' | 'video'
type Mode = 'bleep' | 'audio-only' | 'full'

const STATUS_FETCH_INTERVAL = 20_000
const MAX_FAILED_FETCHES = 3

function detectKind(file: File | null): MediaKind | null {
  if (file?.type.startsWith('audio/')) return 'audio'
  if (file?.type.startsWith('video/')) return 'video'
  return null
}

// Reads media duration in the browser. Leaves it null if the browser cannot decode the file.
function readDuration(file: File, onDuration: (seconds: number | null) => void) {
  const url = URL.createObjectURL(file)
  const media = document.createElement(file.type.startsWith('video') ? 'video' : 'audio')
  const done = (seconds: number | null) => {
    URL.revokeObjectURL(url)
    onDuration(seconds)
  }
  media.preload = 'metadata'
  media.onloadedmetadata = () => done(Number.isFinite(media.duration) ? media.duration : null)
  media.onerror = () => done(null)
  media.src = url
}

function App() {
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [mediaSeconds, setMediaSeconds] = useState<number | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  const [phase, setPhase] = useState<Phase | null>(null) // null = file picker
  const [jobId, setJobId] = useState<string | null>(null)
  const [uploadFraction, setUploadFraction] = useState(0)
  const [status, setStatus] = useState<JobStatusResponse | null>(null)
  const [remaining, setRemaining] = useState<number | null>(null)
  const [failure, setFailure] = useState('')

  const runningSince = useRef<number | null>(null)
  const runningSamples = useRef(0)

  const mediaKind = useMemo(() => detectKind(selectedFile), [selectedFile])
  const progress = status ? stageProgress(status.stage, status.percent) : stageProgress('downloading', 0)

  const reset = () => {
    setPhase(null)
    setJobId(null)
    setStatus(null)
    setRemaining(null)
    setFailure('')
    setSelectedFile(null)
    setMediaSeconds(null)
    runningSince.current = null
    runningSamples.current = 0
  }

  const startJob = async (mode: Mode) => {
    if (!selectedFile) {
      return
    }
    setErrorMessage(null)

    try {
      const created = await createJob({
        filterSubtitles: mode === 'full',
        fileSize: selectedFile.size,
        fileType: selectedFile.type,
      })
      setUploadFraction(0)
      setPhase('uploading')
      await uploadFile(created.upload_url, selectedFile, setUploadFraction)
      await confirmUpload(created.job_id)
      setPhase('queued')
      setJobId(created.job_id)
    } catch (err) {
      setPhase(null)
      setErrorMessage(err instanceof Error ? err.message : 'Unable to submit file.')
    }
  }

  // Polls job status until the job is done or failed.
  useEffect(() => {
    if (!jobId || phase === 'done' || phase === 'failed') {
      return
    }
    let failedFetches = 0

    const poll = async () => {
      try {
        const job = await fetchStatus(jobId)
        failedFetches = 0
        setStatus(job)

        if (job.status === 'done') {
          setPhase('done')
        } else if (job.status === 'failed') {
          setFailure('Processing failed.')
          setPhase('failed')
        } else if (job.status === 'running') {
          runningSince.current ??= Date.now()
          runningSamples.current += 1
          const elapsed = (Date.now() - runningSince.current) / 1000
          const overall = overallProgress(stageProgress(job.stage, job.percent))
          setRemaining(remainingSeconds(overall, runningSamples.current, elapsed, mediaSeconds))
          setPhase('running')
        }
      } catch (err) {
        failedFetches += 1
        if (failedFetches >= MAX_FAILED_FETCHES) {
          setFailure(err instanceof Error ? err.message : 'Unable to fetch job status.')
          setPhase('failed')
        }
      }
    }

    void poll()
    const timer = window.setInterval(poll, STATUS_FETCH_INTERVAL)
    return () => window.clearInterval(timer)
  }, [jobId, phase === 'done' || phase === 'failed']) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <main className="min-h-screen bg-[radial-gradient(1200px_500px_at_20%_-20%,#fecdd3,transparent),radial-gradient(1200px_500px_at_80%_120%,#bae6fd,transparent),#fff8f2] px-4 py-10 text-slate-900">
      <div className="mx-auto w-full max-w-3xl">
        <header className="mb-8">
          <p className="mb-2 inline-flex rounded-full border border-amber-300 bg-amber-100 px-3 py-1 text-xl font-semibold tracking-[0.2em] text-amber-800">
            VIDEO CONTENT FILTER
          </p>
          <h1 className="text-4xl font-black leading-tight md:text-5xl">
            Remove profanity from audio and video in one click.
          </h1>
          <p className="mt-3 max-w-2xl text-sm text-slate-700 md:text-base">
            Upload a single file, choose a filtering action, and download the cleaned result when processing completes.
          </p>
        </header>

        {errorMessage && (
          <div className="mb-6 rounded-2xl border border-rose-300 bg-rose-50 px-4 py-3 text-sm font-semibold text-rose-700">
            {errorMessage}
          </div>
        )}

        {phase ? (
          <StatusCard
            phase={phase}
            uploadFraction={uploadFraction}
            stageProgress={progress}
            remaining={remaining}
            downloadLink={status?.download_link ?? ''}
            error={failure}
            onRetry={reset}
          />
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
                setMediaSeconds(null)
                if (next) readDuration(next, setMediaSeconds)
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
