CREATE TYPE job_status AS ENUM ('queued', 'running', 'done', 'failed');

CREATE TABLE Job (
    id UUID PRIMARY KEY,
    filter_subtitles BOOLEAN NOT NULL,
    file_name TEXT NOT NULL,
    file_type TEXT NOT NULL,
    percent INT NOT NULL DEFAULT 0,
    stage TEXT NOT NULL,
    status job_status NOT NULL,
    download_link TEXT,
    started_at TIMESTAMP NOT NULL,
    ended_at TIMESTAMP
);