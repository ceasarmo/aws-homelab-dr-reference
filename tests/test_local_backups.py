"""Development checks with synthetic data; never connects to a homelab or AWS."""
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts/lib"))
import unittest
from unittest.mock import patch
import zipfile

spec = importlib.util.spec_from_file_location('backup', Path(__file__).resolve().parents[1]/'scripts/lib/backup.py')
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)


class BackupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def test_sqlite_snapshot_captures_committed_wal(self):
        source = self.root/'live.sqlite'
        with sqlite3.connect(source) as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('CREATE TABLE demo(value TEXT)')
            db.execute("INSERT INTO demo VALUES ('synthetic')")
            db.commit()
            b.snapshot(source, self.root/'copy.sqlite')
        with sqlite3.connect(self.root/'copy.sqlite') as copy:
            self.assertEqual(copy.execute('SELECT * FROM demo').fetchall(), [('synthetic',)])

    def test_missing_source_is_not_created(self):
        source = self.root/'missing.sqlite'
        with self.assertRaises(RuntimeError): b.snapshot(source, self.root/'out.sqlite')
        self.assertFalse(source.exists())

    def test_pihole_preserves_group_associations(self):
        source = self.root/'gravity.db'
        with sqlite3.connect(source) as db:
            for table in b.PI_TABLES:
                db.execute('CREATE TABLE "'+table+'" (id INTEGER, value TEXT)')
                db.execute('INSERT INTO "'+table+'" VALUES (1, "synthetic")')
        b.export_pihole(source, self.root/'rules.json')
        result = json.loads((self.root/'rules.json').read_text())
        self.assertEqual(set(result['tables']),set(b.PI_TABLES))
        self.assertEqual(result['tables']['client_by_group']['rows'],[[1,'synthetic']])

    def test_pihole_unknown_schema_fails(self):
        source=self.root/'gravity.db'
        with sqlite3.connect(source) as db: db.execute('CREATE TABLE other(id INTEGER)')
        with self.assertRaises(sqlite3.OperationalError): b.export_pihole(source,self.root/'rules.json')

    def test_archive_rejects_links(self):
        target=self.root/'secret';target.write_text('synthetic')
        link=self.root/'config';link.symlink_to(target)
        with self.assertRaises(RuntimeError): b.archive(self.root/'out.tar.gz',[link])

    def test_archive_skips_socket(self):
        import os, stat, tarfile
        config=self.root/'config';config.mkdir();(config/'settings').write_text('synthetic')
        ipc=config/'ipc';ipc.touch()
        original=Path.lstat
        def simulated_socket(path):
            info=original(path)
            if path == ipc:
                values=list(info);values[0]=stat.S_IFSOCK | 0o600
                return os.stat_result(values)
            return info
        out=self.root/'out.tar.gz'
        with patch.object(Path,'lstat',simulated_socket): b.archive(out,[config])
        with tarfile.open(out) as tar:
            self.assertTrue(any(n.endswith('/settings') for n in tar.getnames()))
            self.assertFalse(any(n.endswith('/ipc') for n in tar.getnames()))

    def test_stale_zip_rejected(self):
        import os,time
        path=self.root/'native.zip'
        with zipfile.ZipFile(path,'w') as z: z.writestr('config','synthetic')
        with patch.object(b,'ZIP_DIRS',{'sonarr':self.root}):
            self.assertEqual(b.latest_zips()['sonarr'],path)
            old=time.time()-7200;os.utime(path,(old,old))
            with self.assertRaises(RuntimeError): b.latest_zips()

    def test_manual_and_scheduled_selected_but_update_excluded(self):
        import os,time
        now=time.time()
        for directory,age in [('manual',30),('scheduled',60),('update',0)]:
            folder=self.root/directory;folder.mkdir()
            path=folder/'backup.zip'
            with zipfile.ZipFile(path,'w') as z:z.writestr('config','synthetic')
            os.utime(path,(now-age,now-age))
        with patch.object(b,'ZIP_DIRS',{'radarr':self.root}):
            self.assertEqual(b.latest_zips()['radarr'],self.root/'manual/backup.zip')
            path=self.root/'scheduled/backup.zip'
            os.utime(path,(now-10,now-10))
            self.assertEqual(b.latest_zips()['radarr'],path)

    def test_corrupt_zip_rejected(self):
        (self.root/'bad.zip').write_text('not a zip')
        with patch.object(b,'ZIP_DIRS',{'sonarr':self.root}):
            with self.assertRaises(zipfile.BadZipFile): b.latest_zips()

    def test_npm_restart_after_capture_failure(self):
        calls=[]
        def command(*args,**kwargs):
            calls.append(args)
            if args[1]=='inspect': return 'false' if any(c[1]=='stop' for c in calls) and not any(c[1]=='start' for c in calls) else 'true'
            return ''
        with patch.object(b,'command',side_effect=command):
            with self.assertRaisesRegex(RuntimeError,'synthetic failure'):
                with b.paused('npm',self.root/'log'): raise RuntimeError('synthetic failure')
        self.assertIn(('docker','start',b.NPM_CONTAINER),calls)

    def test_plex_only_restarts_previously_active_services(self):
        states={'plexmediaserver':'active','qbittorrent-nox':'inactive'};calls=[]
        def command(*args,**kwargs):
            calls.append(args)
            states[args[2]]='inactive' if args[1]=='stop' else 'active'
            return ''
        with patch.object(b,'service_state',side_effect=lambda s:states[s]),patch.object(b,'command',side_effect=command):
            with self.assertRaises(RuntimeError):
                with b.paused('plex',self.root/'log'): raise RuntimeError('capture failed')
        self.assertIn(('systemctl','start','plexmediaserver'),calls)
        self.assertNotIn(('systemctl','start','qbittorrent-nox'),calls)

    def test_restart_failure_is_not_success(self):
        def command(*args,**kwargs):
            if args[1]=='inspect': return 'false' if seen else 'true'
            if args[1]=='stop': seen.append(True)
            if args[1]=='start': raise RuntimeError('start failed')
            return ''
        seen=[]
        with patch.object(b,'command',side_effect=command):
            with self.assertRaisesRegex(RuntimeError,'Manual service recovery'):
                with b.paused('npm',self.root/'log'): pass

    def test_monthly_captures_metadata_with_paired_state(self):
        import tarfile
        plex=self.root/'plex';dbdir=plex/'Plug-in Support/Databases';dbdir.mkdir(parents=True)
        for name in ('com.plexapp.plugins.library.db','com.plexapp.plugins.library.blobs.db'):
            with sqlite3.connect(dbdir/name) as db: db.execute('CREATE TABLE demo(id INTEGER)')
        for name in ('Metadata','Media'):
            (plex/name).mkdir();(plex/name/'item').write_text('synthetic artwork')
        config=self.root/'config';config.write_text('synthetic config')
        zipdir=self.root/'native';zipdir.mkdir()
        with zipfile.ZipFile(zipdir/'backup.zip','w') as z: z.writestr('config','synthetic')
        work=self.root/'work';work.mkdir()
        states={'plexmediaserver':'active','qbittorrent-nox':'active'}
        def command(*args,**kwargs):
            if args[0]=='systemctl':
                states[args[2]]='inactive' if args[1]=='stop' else 'active'
                return ''
            if args[0]=='dpkg-query': return 'synthetic-package 1.0'
            if args[0]==b.PLEX_SQLITE:
                if args[-1].startswith('.backup'):
                    target=Path(args[-1].split("'",2)[1]);b.snapshot(Path(args[2]),target)
                    return ''
                return 'ok'
            raise AssertionError(args)
        with patch.object(b,'PLEX',plex),patch.object(b,'paths_for',return_value=[config]),patch.object(b,'native_backups') as native,patch.object(b,'command',side_effect=command),patch.object(b,'service_state',side_effect=lambda s:states[s]):
            native.generate.return_value={'sonarr':zipdir/'backup.zip'}
            b.capture('plex',True,work)
        for name in ('plex-library.sqlite','plex-blobs.sqlite','metadata.tar.gz','config.tar.gz','sonarr.zip','packages.txt','native-backups.json'):
            self.assertTrue((work/name).is_file(),name)
        self.assertTrue(all(s=='active' for s in states.values()))
        with tarfile.open(work/'metadata.tar.gz') as tar:
            self.assertTrue(any(n.endswith('/Metadata/item') for n in tar.getnames()))
            self.assertTrue(any(n.endswith('/Media/item') for n in tar.getnames()))

    def test_finish_hashes_and_atomically_publishes(self):
        work=self.root/'.incomplete-test';work.mkdir()
        (work/'payload').write_bytes(b'synthetic')
        (work/'backup.log').write_text('private diagnostic')
        final=b.finish(work,'npm',False,'synthetic-start')
        self.assertFalse(work.exists());self.assertTrue((final/'COMPLETE').exists())
        manifest=json.loads((final/'manifest.json').read_text())
        self.assertEqual([f['name'] for f in manifest['files']],['payload'])
        self.assertEqual(manifest['files'][0]['sha256'],b.digest(final/'payload'))
        self.assertIn('manifest.json',(final/'SHA256SUMS').read_text())

    def test_finish_failure_does_not_mark_complete(self):
        work=self.root/'.incomplete-test';work.mkdir();(work/'payload').write_text('synthetic')
        with patch.object(b,'digest',side_effect=['first','manifest','changed']):
            with self.assertRaises(RuntimeError): b.finish(work,'npm',False,'start')
        self.assertFalse((work/'COMPLETE').exists())


if __name__=='__main__': unittest.main()
