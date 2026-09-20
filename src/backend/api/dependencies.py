from __future__ import annotations

from functools import lru_cache
from typing import Iterator

import boto3
import pika
from pika.adapters.blocking_connection import BlockingChannel
import psycopg
import redis

from backend.api.settings import Settings, load_settings


@lru_cache
def get_settings() -> Settings:
    return load_settings()


@lru_cache
def get_r2_client():
    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=settings.r2_endpoint_url,
        aws_access_key_id=settings.r2_access_key_id,
        aws_secret_access_key=settings.r2_secret_access_key,
        region_name="auto",
    )


@lru_cache
def get_redis_client() -> redis.Redis:
    settings = get_settings()
    return redis.Redis.from_url(settings.upstash_redis_job_store_url)


@lru_cache
def get_rabbitmq_channel() -> BlockingChannel:
    settings = get_settings()
    connection = pika.BlockingConnection(pika.URLParameters(settings.rabbitmq_url))
    channel = connection.channel()
    channel.queue_declare(queue=settings.job_queue_name, durable=True)
    return channel


def get_db_connection() -> Iterator[psycopg.Connection]:
    settings = get_settings()
    with psycopg.connect(settings.database_url) as conn:
        yield conn
