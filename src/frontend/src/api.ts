export const API_BASE = import.meta.env.VITE_API_BASE_URL ?? (import.meta.env.DEV ? 'http://127.0.0.1:8000' : '')

export type JobRequest = { filterSubtitles: boolean; fileSize: number; fileType: string }
export type PresignedPost = { url: string; fields: Record<string, string> }
export type JobCreateResponse = { job_id: string; upload_url: PresignedPost }
export type JobStatusResponse = { status: string; stage: string; percent: number; download_link: string }

async function request(path: string, init?: RequestInit): Promise<Response> {
  let res: Response
  try {
    res = await fetch(`${API_BASE}/api/v1${path}`, init)
  } catch {
    throw new Error('Cannot reach the backend API.')
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    const detail = typeof body.detail === 'string' ? body.detail : `Request failed (${res.status})`
    throw new Error(detail)
  }
  return res
}

export async function createJob(job: JobRequest): Promise<JobCreateResponse> {
  const res = await request('/job/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(job),
  })
  return res.json()
}

export async function confirmUpload(jobId: string): Promise<void> {
  await request(`/job/${jobId}/upload_status`, { method: 'POST' })
}

export async function fetchStatus(jobId: string): Promise<JobStatusResponse> {
  const res = await request(`/job/${jobId}`)
  return res.json()
}

// XHR instead of fetch: fetch cannot report upload progress.
export function uploadFile(
  post: PresignedPost,
  file: File,
  onProgress: (fraction: number) => void,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const form = new FormData()
    Object.entries(post.fields).forEach(([k, v]) => form.append(k, v))
    form.append('file', file) // storage requires the file to be the last field

    const xhr = new XMLHttpRequest()
    xhr.open('POST', post.url)
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total)
    xhr.onload = () =>
      xhr.status >= 200 && xhr.status < 300
        ? resolve()
        : reject(new Error(`Upload failed (${xhr.status}).`))
    xhr.onerror = () => reject(new Error('Upload failed. Check your connection.'))
    xhr.send(form)
  })
}
