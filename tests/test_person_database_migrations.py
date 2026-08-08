import sqlite3
import tempfile
import unittest
from pathlib import Path

from src.core.person_database import PersonDatabaseMigrationError, PersonRepository


class PersonDatabaseMigrationTests(unittest.TestCase):
    def test_new_database_and_schema_version_one(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "people.db"
            repository = PersonRepository(path)
            self.assertEqual(repository.initialize(), 1)
            with sqlite3.connect(path) as connection:
                self.assertEqual(connection.execute(
                    "SELECT MAX(version) FROM schema_version"
                ).fetchone()[0], 1)
                columns = {row[1] for row in connection.execute("PRAGMA table_info(people)")}
            self.assertEqual(columns, {
                "person_id", "cedula", "first_name", "last_name", "address", "phone",
                "email", "birth_date", "sex", "notes", "status", "created_at", "updated_at",
            })

    def test_future_schema_version_is_rejected_without_change(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "future.db"
            with sqlite3.connect(path) as connection:
                connection.execute(
                    "CREATE TABLE schema_version(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)"
                )
                connection.execute("CREATE TABLE people(person_id TEXT PRIMARY KEY)")
                connection.execute(
                    "INSERT INTO schema_version(version, applied_at) VALUES (?, ?)", (99, "future")
                )
                connection.commit()
            with self.assertRaises(PersonDatabaseMigrationError):
                PersonRepository(path).initialize()
            with sqlite3.connect(path) as connection:
                self.assertEqual(connection.execute(
                    "SELECT version FROM schema_version"
                ).fetchone()[0], 99)


if __name__ == "__main__": unittest.main()
