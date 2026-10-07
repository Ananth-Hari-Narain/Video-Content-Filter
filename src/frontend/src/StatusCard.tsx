import { STAGES } from './stages'

export type Phase = 'uploading' | 'queued' | 'running' | 'failed' | 'done'

type Props = {
  phase: Phase
  uploadFraction: number
  stageProgress: number[]
  remaining: number | null
  downloadLink: string
  error: string
  onRetry: () => void
}

function formatDuration(seconds: number): string {
  const minutes = Math.ceil(seconds / 60)
  if (minutes < 1) return 'less than a minute'
  if (minutes < 60) return `about ${minutes} min`
  return `about ${Math.floor(minutes / 60)} h ${minutes % 60} min`
}

function Bar({ label, percent }: { label: string; percent: number }) {
  const rounded = Math.round(percent)
  return (
    <div>
      <div className="mb-1 flex justify-between text-sm font-semibold text-slate-700">
        <span>{label}</span>
        <span>{rounded}%</span>
      </div>
      <div
        className="h-3 overflow-hidden rounded-full bg-slate-200"
        role="progressbar"
        aria-label={label}
        aria-valuenow={rounded}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div className="h-full rounded-full bg-amber-500 transition-all duration-700" style={{ width: `${rounded}%` }} />
      </div>
    </div>
  )
}

function StatusCard({ phase, uploadFraction, stageProgress, remaining, downloadLink, error, onRetry }: Props) {
  return (
    <section className="rounded-3xl border border-slate-200 bg-white p-8 shadow-sm md:p-10">
      {phase === 'uploading' && (
        <div className="space-y-4">
          <h2 className="text-2xl font-black">Uploading your file</h2>
          <Bar label="Upload" percent={uploadFraction * 100} />
        </div>
      )}

      {phase === 'queued' && (
        <div className="text-center">
          <h2 className="text-2xl font-black">Waiting to be processed</h2>
          <p className="mt-2 text-sm text-slate-600">Your file is uploaded. Processing starts when a worker is free.</p>
        </div>
      )}

      {phase === 'running' && (
        <div className="space-y-4">
          <h2 className="text-2xl font-black">Filtering profanity</h2>
          {STAGES.map((stage, i) =>
            stage.weight > 0 ? <Bar key={stage.key} label={stage.label} percent={stageProgress[i]} /> : null,
          )}
          {remaining !== null && (
            <p className="text-sm text-slate-600">Estimated time left: {formatDuration(remaining)}</p>
          )}
        </div>
      )}

      {phase === 'failed' && (
        <div className="space-y-4">
          <h2 className="text-2xl font-black text-rose-700">Processing failed</h2>
          <div className="min-h-16 rounded-2xl border border-rose-300 bg-rose-50 px-4 py-3 text-sm font-semibold text-rose-700">
            {error}
          </div>
          <button
            type="button"
            className="rounded-xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white transition hover:bg-slate-700"
            onClick={onRetry}
          >
            Try again
          </button>
        </div>
      )}

      {phase === 'done' && (
        <div className="space-y-4 text-center">
          <h2 className="text-2xl font-black">Your file is ready</h2>
          <a
            className="inline-flex items-center justify-center rounded-xl bg-slate-900 px-4 py-2 text-sm font-semibold text-white transition hover:bg-slate-700"
            href={downloadLink}
          >
            Download filtered file
          </a>
        </div>
      )}
    </section>
  )
}

export default StatusCard
