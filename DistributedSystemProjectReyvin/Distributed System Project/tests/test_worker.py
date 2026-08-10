from __future__ import annotations

import unittest

from minisplunk.worker import process_ingest_job


class FakeRepository:
    documents: list[dict[str, object]]

    def insert_logs(self, documents: list[dict[str, object]]) -> int:
        self.documents = documents
        return len(documents)


class WorkerTests(unittest.TestCase):
    def test_process_ingest_job_parses_and_stores_documents(self) -> None:
        repository = FakeRepository()
        job = {
            "job_id": "job-1",
            "file_name": "syslog.log",
            "payload": "Jul 16 15:20:01 web-1 sshd[123]: Failed password\n",
        }

        inserted_count = process_ingest_job(job, repository)  # type: ignore[arg-type]

        self.assertEqual(inserted_count, 1)
        self.assertEqual(repository.documents[0]["job_id"], "job-1")
        self.assertEqual(repository.documents[0]["hostname"], "web-1")
        self.assertEqual(repository.documents[0]["process"], "sshd")
        self.assertEqual(repository.documents[0]["dedupe_key"], "job-1:1")

    def test_process_ingest_job_requires_core_fields(self) -> None:
        with self.assertRaises(ValueError):
            process_ingest_job({"job_id": "job-1"}, FakeRepository())  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
