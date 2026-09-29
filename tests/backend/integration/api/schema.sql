CREATE TYPE "job_status" AS ENUM('queued', 'running', 'done', 'failed');

CREATE TABLE "job" (
	"id" uuid PRIMARY KEY,
	"filter_subtitles" boolean NOT NULL,
	"file_type" text NOT NULL,
	"percent" integer DEFAULT 0 NOT NULL,
	"stage" text NOT NULL,
	"status" job_status NOT NULL,
	"download_link" text,
	"created_at" timestamp NOT NULL,
	"started_at" timestamp,
	"ended_at" timestamp,
	"file_size" bigint NOT NULL
);