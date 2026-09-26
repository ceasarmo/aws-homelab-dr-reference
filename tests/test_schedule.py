import datetime as dt
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('schedule',Path(__file__).resolve().parents[1]/'scripts/schedule/run.py')
s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)


def local(day):
    return dt.datetime.fromisoformat(day).replace(tzinfo=s.ZONE)


class ScheduleTests(unittest.TestCase):
    def test_not_due_after_first_success(self):
        self.assertEqual(s.decision('npm',local('2026-09-23T03:10'),local('2026-09-22T20:19')),'not-due')

    def test_exact_fifteenth_calendar_day(self):
        previous=local('2026-09-22T20:17')
        self.assertEqual(s.decision('nextcloud',local('2026-10-06T03:00'),previous),'not-due')
        self.assertEqual(s.decision('nextcloud',local('2026-10-07T03:00'),previous),'biweekly')

    def test_missed_days_catch_up_once(self):
        self.assertEqual(s.decision('pihole',local('2026-10-20T12:00'),local('2026-09-22T20:21')),'biweekly')

    def test_monthly_first_of_next_local_month(self):
        old=local('2026-09-22T20:28')
        self.assertEqual(s.decision('plex',local('2026-09-23T03:30'),old,old),'not-due')
        self.assertEqual(s.decision('plex',local('2026-10-01T03:30'),old,old),'monthly')

    def test_monthly_counts_as_critical(self):
        self.assertEqual(s.decision('plex',local('2026-10-07T03:30'),local('2026-09-22T20:39'),local('2026-10-01T03:30')),'not-due')
        self.assertEqual(s.decision('plex',local('2026-10-16T03:30'),local('2026-09-22T20:39'),local('2026-10-01T03:30')),'biweekly')

    def test_no_backup_is_due(self):
        now=local('2026-10-01T03:30')
        self.assertEqual(s.decision('plex',now,None,None),'monthly')
        self.assertEqual(s.decision('npm',now,None),'biweekly')

    def test_month_boundary_uses_configured_zone(self):
        now=dt.datetime(2026,10,1,2,0,tzinfo=dt.timezone.utc)
        self.assertEqual(s.decision('plex',now,local('2026-09-22T20:39'),local('2026-09-22T20:28')),'monthly')

    def test_scan_ignores_incomplete_future_and_missing_payload(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);base=root/'plex/biweekly';base.mkdir(parents=True)
            for name,stamp,payload in [('ok','2026-09-23T02:39:28+00:00',True),('.incomplete-fail','2026-09-24T02:39:28+00:00',True),('future','2099-01-01T00:00:00+00:00',True),('missing','2026-09-24T00:00:00+00:00',False)]:
                p=base/name;p.mkdir();(p/'COMPLETE').touch();(p/'SHA256SUMS').touch()
                (p/'manifest.json').write_text(json.dumps({'service':'plex','cadence':'biweekly','validated_at_utc':stamp,'files':[{'name':'payload'}]}))
                if payload:(p/'payload').touch()
            with patch.object(s,'ROOT',root):
                self.assertEqual(s.latest_complete('plex','biweekly',local('2026-09-24T03:30')),dt.datetime(2026,9,23,2,39,28,tzinfo=dt.timezone.utc))

    def test_status_does_not_launch_backup(self):
        with patch.object(s.os,'geteuid',return_value=0),patch.object(s,'inspect',return_value='monthly'),patch.object(s.subprocess,'run') as execute,patch('sys.argv',['run.py','plex','--status']):
            self.assertEqual(s.main(),0);execute.assert_not_called()


if __name__=='__main__':unittest.main()
