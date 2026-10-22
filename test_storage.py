import sqlite3,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from storage_check import check
class StorageTests(unittest.TestCase):
    def test_temporary_probe_does_not_touch_existing_app_database(self):
        with tempfile.TemporaryDirectory() as directory:
            app=Path(directory)/'tracker.db';app.write_bytes(b'do-not-touch')
            self.assertIn('probes passed',check(directory))
            self.assertEqual(app.read_bytes(),b'do-not-touch');self.assertEqual(list(Path(directory).iterdir()),[app])
    def test_serialized_connections_use_full_sync_and_close(self):
        import server
        with tempfile.TemporaryDirectory() as directory,patch.object(server,'DB',str(Path(directory)/'db.sqlite')):
            with server.connect() as db:
                self.assertEqual(db.execute('PRAGMA synchronous').fetchone()[0],2)
                db.execute('CREATE TABLE entries(value INTEGER)')
            with self.assertRaises(sqlite3.ProgrammingError):db.execute('SELECT 1')
            from concurrent.futures import ThreadPoolExecutor
            def insert(i):
                with server.connect() as con:con.execute('INSERT INTO entries VALUES(?)',(i,))
            with ThreadPoolExecutor(max_workers=5) as pool:list(pool.map(insert,range(20)))
            with server.connect() as con:self.assertEqual(con.execute('SELECT count(*) FROM entries').fetchone()[0],20)
    def test_initialization_uses_delete_journal(self):
        import server,os
        with tempfile.TemporaryDirectory() as directory,patch.object(server,'DB',str(Path(directory)/'db.sqlite')),patch.dict(os.environ,{'ADMIN_PASSWORD':'test-storage-only-12345'}):
            server.init()
            with server.connect() as con:self.assertEqual(con.execute('PRAGMA journal_mode').fetchone()[0],'delete')
if __name__=='__main__':unittest.main()
