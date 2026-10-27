"""Verified, rotating SQLite snapshots. Run one application process per database."""
import json
import os
import re
import sqlite3
import threading
import time
import uuid
from datetime import datetime,timezone
from pathlib import Path

LOCK=threading.Lock()
NAME=re.compile(r'acetime-\d{8}T\d{12}Z-[a-f0-9]{8}\.sqlite3')

def options(database):
    folder=Path(os.getenv('BACKUP_DIRECTORY',str(Path(database).parent/'backups'))).resolve()
    hours=float(os.getenv('BACKUP_INTERVAL_HOURS','6'))
    keep=int(os.getenv('BACKUP_KEEP','28'))
    if not 0.01<=hours<=8760 or not 1<=keep<=1000:raise ValueError('Invalid backup interval or retention.')
    return folder,hours*3600,keep

def files(folder):
    if not folder.exists():return []
    return sorted([p for p in folder.iterdir() if NAME.fullmatch(p.name) and p.is_file() and not p.is_symlink()],key=lambda p:p.name,reverse=True)

def status(database):
    folder,interval,keep=options(database)
    metadata={}
    try:metadata=json.loads((folder/'status.json').read_text(encoding='utf-8'))
    except (OSError,ValueError):pass
    if not isinstance(metadata,dict):metadata={}
    copies=files(folder)
    last=metadata.get('lastSuccess') or (copies[0].stat().st_mtime if copies else None)
    return {'lastSuccess':last,'lastAttempt':metadata.get('lastAttempt'),'error':metadata.get('error'),
            'nextAttempt':metadata.get('nextAttempt') or ((last+interval) if last else time.time()),
            'intervalHours':interval/3600,'keep':keep,
            'files':[{'name':p.name,'bytes':p.stat().st_size,'created':p.stat().st_mtime} for p in copies]}

def write_status(folder,payload):
    temp=folder/('status-'+uuid.uuid4().hex+'.partial')
    try:
        with temp.open('x',encoding='utf-8') as f:
            os.chmod(temp,0o600);json.dump(payload,f);f.flush();os.fsync(f.fileno())
        os.replace(temp,folder/'status.json')
    finally:
        if temp.exists():temp.unlink()

def snapshot(database,db_lock):
    folder,interval,keep=options(database)
    with LOCK:
        folder.mkdir(parents=True,exist_ok=True)
        previous=status(database);now=time.time()
        name='acetime-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')+'-'+uuid.uuid4().hex[:8]+'.sqlite3'
        target=folder/name;temp=folder/(name+'.partial')
        try:
            # Never use a connection with an active write transaction as a backup source.
            with db_lock:
                source=sqlite3.connect(Path(database).resolve().as_uri()+'?mode=ro',uri=True,timeout=30)
                destination=sqlite3.connect(temp)
                try:
                    os.chmod(temp,0o600)
                    source.backup(destination,pages=256,sleep=0.05)
                    if destination.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise RuntimeError('Snapshot verification failed.')
                finally:destination.close();source.close()
            with temp.open('rb+') as f:os.fsync(f.fileno())
            os.replace(temp,target)
            # Delete only our own recognized snapshot files, after verifying a replacement.
            for old in files(folder)[keep:]:old.unlink()
            write_status(folder,{'lastAttempt':now,'lastSuccess':time.time(),'error':None,'nextAttempt':time.time()+interval})
            return target.name
        except Exception:
            try:write_status(folder,{'lastAttempt':now,'lastSuccess':previous['lastSuccess'],
                    'error':'Backup failed. Check backup storage and available space.','nextAttempt':time.time()+300})
            except OSError:pass
            raise
        finally:
            if temp.exists():temp.unlink()

def download_path(database,name):
    folder,_,_=options(database)
    if not isinstance(name,str) or not NAME.fullmatch(name):raise ValueError('Choose a saved backup.')
    path=folder/name
    if path.is_symlink() or not path.is_file() or path.resolve().parent!=folder:raise ValueError('Backup not found.')
    return path

def run_due(database,db_lock):
    current=status(database)
    if time.time()>=current['nextAttempt']:snapshot(database,db_lock)

def loop(database,db_lock,stop=None):
    stop=stop or threading.Event()
    while not stop.is_set():
        try:run_due(database,db_lock)
        except Exception:pass # The instructor can inspect persisted status; retry in five minutes.
        stop.wait(60)

def restore_copy(source,output):
    """Restore to a NEW file for offline inspection; never overwrite a running database."""
    output=Path(output)
    with output.open('xb'):pass
    try:
        src=sqlite3.connect(Path(source).resolve().as_uri()+'?mode=ro',uri=True)
        dest=sqlite3.connect(output)
        try:
            os.chmod(output,0o600);src.backup(dest)
            if dest.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise ValueError('Backup is not healthy.')
        finally:dest.close();src.close()
    except Exception:
        output.unlink(missing_ok=True);raise

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description='Restore a backup into a new database file. Stop the app before replacing its live database.')
    parser.add_argument('--restore',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();restore_copy(args.restore,args.output)
