from __future__ import annotations

import os

from minisplunk.config import mongo_uri, rabbitmq_config
from minisplunk.parser import parse_syslog_lines
from minisplunk.rabbitmq import consume_ingest_jobs
from minisplunk.storage import MongoLogRepository


def process_ingest_job(job: dict[str, str], repository: MongoLogRepository) -> int:
    for field in ("job_id", "file_name", "payload"):
        if field not in job:
            raise ValueError(f"Missing ingest job field: {field}")

    parsed = parse_syslog_lines(job["payload"].splitlines())
    documents = [
        log.to_document(job_id=job["job_id"], line_number=index, file_name=job["file_name"])
        for index, log in enumerate(parsed, start=1)
    ]
    return repository.insert_logs(documents)


def main() -> None:
    repository = MongoLogRepository(mongo_uri())
    worker_name = os.getenv("WORKER_NAME", os.uname().nodename)

    def callback(job: dict[str, str]) -> None:
        inserted_count = process_ingest_job(job, repository)
        repository.mark_worker_active(worker_name, inserted_count)
        print(f"Processed job {job['job_id']} with {inserted_count} log lines")

    print("Worker waiting for ingest jobs...")
    consume_ingest_jobs(rabbitmq_config(), callback)


if __name__ == "__main__":
    main()
