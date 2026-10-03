export type Stage = { key: string; label: string; weight: number }

// key = backend `stage` string, weight = share of total processing time.
// To add a stage, add a row here in backend order (weights must sum to 1).
// Stages with weight 0 are tracked but not shown as a bar.
export const STAGES: Stage[] = [
  { key: 'downloading', label: 'Downloading', weight: 0 },
  { key: 'transcribe', label: 'Transcribing', weight: 0.6 },
  { key: 'censoring video', label: 'Censoring video', weight: 0.2 },
  { key: 'uploading', label: 'Worker uploading video', weight: 0.2 },
  { key: 'completed', label: 'Completed', weight: 0 },
]

// Percent (0-100) done for each stage, given the backend's current stage and its percent.
// Stages before the current one are 100, after it 0.
export function stageProgress(stage: string, percent: number): number[] {
  const current = STAGES.findIndex((s) => s.key === stage)
  return STAGES.map((_, i) => (i < current ? 100 : i === current ? percent : 0))
}

// Weighted overall progress, 0-1.
export function overallProgress(progress: number[]): number {
  return STAGES.reduce((sum, s, i) => sum + (s.weight * progress[i]) / 100, 0)
}
