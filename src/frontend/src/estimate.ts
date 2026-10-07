// Guess of processing time per second of media, used until there is enough data to measure.
export const PROCESSING_RATIO = 1.0

const MIN_SAMPLES = 2
const MIN_FIRST_SAMPLE_PROGRESS = 0.25

/**
 * Estimated seconds left, or null when no estimate should be shown.
 * @param progress overall weighted progress, 0-1
 * @param samples number of 'running' status updates received so far
 * @param elapsedSeconds time since the first 'running' update
 * @param mediaSeconds media duration, or null if the browser could not read it
 */
export function remainingSeconds(
  progress: number,
  samples: number,
  elapsedSeconds: number,
  mediaSeconds: number | null,
): number | null {
  const enough = samples >= MIN_SAMPLES || progress > MIN_FIRST_SAMPLE_PROGRESS
  if (enough && progress > 0) {
    return (elapsedSeconds / progress) * (1 - progress)
  }
  if (mediaSeconds === null) {
    return null
  }
  return mediaSeconds * PROCESSING_RATIO * (1 - progress)
}
