"""Exercise a temporary SQLite DB on the mounted export, never the app database."""
import argparse,os,sqlite3,subprocess,sys,tempfile
from pathlib import Path

def check(directory):
    root=Path(directory)
    if not root.is_dir():raise ValueError('Storage directory must exist and be writable by the app user.')
    with tempfile.TemporaryDirectory(prefix='.acetime-storage-probe-',dir=root) as temp:
        path=Path(temp)/'probe.db';db=sqlite3.connect(path)
        try:
            if db.execute('PRAGMA journal_mode=DELETE').fetchone()[0].lower()!='delete':raise RuntimeError('Rollback journal mode unavailable.')
            db.execute('PRAGMA synchronous=FULL');db.execute('CREATE TABLE probe(value INTEGER)');db.commit()
            db.execute('BEGIN IMMEDIATE');db.execute('INSERT INTO probe VALUES(1)')
            contender='''import sqlite3,sys
con=sqlite3.connect(sys.argv[1],timeout=1)
try:
    con.execute('BEGIN IMMEDIATE')
except sqlite3.OperationalError as e:
    sys.exit(0 if 'locked' in str(e).lower() else 2)
else:
    con.rollback();sys.exit(1)
finally:
    con.close()
'''
            result=subprocess.run([sys.executable,'-c',contender,str(path)],capture_output=True,timeout=10)
            if result.returncode!=0:raise RuntimeError('Separate-process write-lock probe failed.')
            db.commit()
            if db.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise RuntimeError('SQLite integrity probe failed.')
        finally:db.close()
    return 'Temporary-file write, rollback journal, process-lock, and integrity probes passed. This does not certify crash recovery or cross-node NFS locking.'
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--directory',default=str(Path(os.getenv('DATABASE_PATH','/app/data/tracker.db')).parent));args=parser.parse_args()
    try:print(check(args.directory))
    except Exception as e:sys.exit('Storage check failed: '+str(e))
