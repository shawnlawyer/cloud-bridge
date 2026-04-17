from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest

from bridge.steward import run_steward_adapter

REPO_ROOT = Path(__file__).resolve().parents[2]
ADAPTER = REPO_ROOT / 'examples' / 'steward-v1-workspace' / 'scripts' / 'steward-cloudbridge.mjs'
FIXED_NOW = '2026-04-17T12:00:00Z'


def _run_adapter(db_path: Path, *args: str) -> dict:
    process = subprocess.run(
        ['node', str(ADAPTER), *args, '--json', '--db', str(db_path), '--now', FIXED_NOW],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if process.returncode != 0:
        raise AssertionError(process.stderr or process.stdout)
    return json.loads(process.stdout)


class TestStewardAdapter(unittest.TestCase):
    def test_home_ingest_and_record_lanes_are_structured(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / 'steward.sqlite'

            home = _run_adapter(db_path, 'home')
            self.assertEqual(home['schemaVersion'], 'steward-cloudbridge/v1')
            self.assertEqual(home['operation'], 'home')
            self.assertEqual(home['title'], 'One Next Step')
            self.assertIn('lastWorked', home)

            _run_adapter(db_path, 'ingest', '--text', 'add bill mortgage due 1st')
            _run_adapter(db_path, 'ingest', '--text', 'add routine let dogs out every 180m')
            _run_adapter(db_path, 'ingest', '--text', 'add date taxes on 2026-04-18')
            _run_adapter(db_path, 'ingest', '--text', 'add task kitchen reset: clear counter | load dishwasher')
            _run_adapter(db_path, 'ingest', '--text', 'start room kitchen')
            _run_adapter(db_path, 'ingest', '--text', 'tool propane heater in shed shelf')

            bills = _run_adapter(db_path, 'records', '--kind', 'bills')
            self.assertEqual(bills['kind'], 'bills')
            self.assertTrue(any(item['title'] == 'Mortgage' for item in bills['summaries']))
            self.assertTrue(any(row['state'] == 'overdue' for row in bills['records']))
            self.assertTrue(any(action['action'] == 'mark_paid' for row in bills['records'] for action in row['actions']))

            routines = _run_adapter(db_path, 'records', '--kind', 'routines')
            self.assertEqual(routines['kind'], 'routines')
            self.assertTrue(any(item['title'] == 'Let Dogs Out' for item in routines['summaries']))
            self.assertTrue(any(row['state'] == 'due' for row in routines['records']))
            self.assertTrue(any(action['action'] == 'mark_done' for row in routines['records'] for action in row['actions']))

            important_dates = _run_adapter(db_path, 'records', '--kind', 'important_dates')
            self.assertEqual(important_dates['kind'], 'important_dates')
            self.assertTrue(any(item['title'] == 'Taxes' for item in important_dates['summaries']))
            self.assertTrue(any(row['state'] == 'soon' for row in important_dates['records']))

            tasks = _run_adapter(db_path, 'records', '--kind', 'tasks')
            self.assertEqual(tasks['kind'], 'tasks')
            self.assertTrue(any(item['title'] == 'kitchen reset' for item in tasks['summaries']))
            self.assertTrue(any(row['continuity'].startswith('Continue with: clear counter') for row in tasks['records']))

            rooms = _run_adapter(db_path, 'records', '--kind', 'rooms')
            self.assertEqual(rooms['kind'], 'rooms')
            self.assertTrue(any(item['title'] == 'Kitchen' for item in rooms['summaries']))
            self.assertTrue(any('Continue with Kitchen: trash.' in row['recoveryPrompt'] for row in rooms['records']))

            tools = _run_adapter(db_path, 'records', '--kind', 'tools')
            self.assertEqual(tools['kind'], 'tools')
            self.assertTrue(any(item['title'] == 'Propane Heater' for item in tools['summaries']))
            self.assertTrue(any('shed shelf' in row['detail'] for row in tools['records']))

            notifications = _run_adapter(db_path, 'records', '--kind', 'notification_events')
            self.assertEqual(notifications['kind'], 'notification_events')
            self.assertGreaterEqual(len(notifications['summaries']), 1)
            self.assertGreaterEqual(len(notifications['records']), 1)

            next_step = _run_adapter(db_path, 'ingest', '--text', "what's next")
            self.assertEqual(next_step['operation'], 'ingest')
            self.assertIn('Mortgage is overdue', next_step['frontDoor']['oneNextStep']['text'])
            self.assertEqual(next_step['frontDoor']['lastWorked']['task']['label'], 'kitchen reset')
            self.assertEqual(next_step['frontDoor']['lastWorked']['room']['label'], 'Kitchen')
            self.assertIsNotNone(next_step['frontDoor']['lastWorked']['notification'])
            self.assertEqual(next_step['frontDoor']['todaySnapshot']['dueRoutineCount'], 1)
            self.assertEqual(next_step['frontDoor']['todaySnapshot']['upcomingDateCount'], 1)

    def test_direct_actions_update_lane_state_without_prose_parsing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / 'steward.sqlite'

            _run_adapter(db_path, 'ingest', '--text', 'add bill mortgage due 1st')
            _run_adapter(db_path, 'ingest', '--text', 'add routine let dogs out every 180m')
            _run_adapter(db_path, 'ingest', '--text', 'add task kitchen reset: clear counter | load dishwasher')
            _run_adapter(db_path, 'ingest', '--text', 'start room kitchen')

            bills = _run_adapter(db_path, 'records', '--kind', 'bills')
            mortgage_ref = next(row['ref'] for row in bills['records'] if row['slug'] == 'mortgage')
            bill_action = _run_adapter(db_path, 'action', '--kind', 'bills', '--ref', mortgage_ref, '--action', 'mark_paid')
            self.assertEqual(bill_action['operation'], 'action')
            self.assertEqual(bill_action['result']['status'], 'paid')
            self.assertTrue(any(row['paidThisMonth'] for row in bill_action['records']))

            routines = _run_adapter(db_path, 'records', '--kind', 'routines')
            routine_ref = routines['records'][0]['ref']
            routine_action = _run_adapter(db_path, 'action', '--kind', 'routines', '--ref', routine_ref, '--action', 'mark_done')
            completed_routine = next(row for row in routine_action['records'] if row['ref'] == routine_ref)
            self.assertIsNotNone(completed_routine['lastDoneAt'])
            self.assertEqual(completed_routine['state'], 'waiting')

            tasks = _run_adapter(db_path, 'records', '--kind', 'tasks')
            task_ref = tasks['records'][0]['ref']
            task_action = _run_adapter(db_path, 'action', '--kind', 'tasks', '--ref', task_ref, '--action', 'advance')
            stepped_task = next(row for row in task_action['records'] if row['ref'] == task_ref)
            self.assertEqual(stepped_task['steps'][0]['status'], 'done')
            self.assertEqual(stepped_task['nextStep']['summary'], 'load dishwasher')

            task_complete = _run_adapter(db_path, 'action', '--kind', 'tasks', '--ref', task_ref, '--action', 'complete')
            finished_task = next(row for row in task_complete['records'] if row['ref'] == task_ref)
            self.assertEqual(finished_task['status'], 'done')

            rooms = _run_adapter(db_path, 'records', '--kind', 'rooms')
            room_ref = rooms['records'][0]['ref']
            room_action = _run_adapter(db_path, 'action', '--kind', 'rooms', '--ref', room_ref, '--action', 'continue')
            continued_room = next(row for row in room_action['records'] if row['ref'] == room_ref)
            self.assertEqual(continued_room['currentIndex'], 1)

            room_done = _run_adapter(db_path, 'action', '--kind', 'rooms', '--ref', room_ref, '--action', 'done')
            closed_room = next(row for row in room_done['records'] if row['ref'] == room_ref)
            self.assertEqual(closed_room['status'], 'done')

            notifications = _run_adapter(db_path, 'records', '--kind', 'notification_events')
            notification_ref = notifications['records'][0]['ref']
            dismissed = _run_adapter(
                db_path,
                'action',
                '--kind',
                'notification_events',
                '--ref',
                notification_ref,
                '--action',
                'dismiss',
            )
            self.assertEqual(dismissed['result']['status'], 'dismissed')
            self.assertFalse(any(row['ref'] == notification_ref for row in dismissed['records']))

    def test_approval_resolution_refreshes_front_door(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / 'steward.sqlite'
            _run_adapter(db_path, 'home')
            with sqlite3.connect(db_path) as connection:
                connection.execute(
                    '''
                    INSERT INTO approvals (approval_ref, title, detail, status, requested_by, created_at)
                    VALUES (?, ?, ?, 'pending', 'steward', ?)
                    ''',
                    ('approval:demo', 'Review budget hold', 'Budget hold needs a decision.', FIXED_NOW),
                )
                connection.commit()

            approvals = _run_adapter(db_path, 'records', '--kind', 'approvals')
            self.assertEqual(approvals['summaries'][0]['ref'], 'approval:demo')

            home = _run_adapter(db_path, 'home')
            self.assertEqual(home['todaySnapshot']['pendingApprovalCount'], 1)
            self.assertEqual(home['oneNextStep']['kind'], 'approval')

            decision = _run_adapter(db_path, 'approval', '--ref', 'approval:demo', '--decision', 'approve')
            self.assertEqual(decision['decision'], 'approve')
            self.assertEqual(decision['result']['status'], 'approved')

            refreshed = _run_adapter(db_path, 'home')
            self.assertEqual(refreshed['todaySnapshot']['pendingApprovalCount'], 0)
            self.assertNotEqual(refreshed['oneNextStep']['kind'], 'approval')

    def test_python_wrapper_reads_json_without_prose_parsing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / 'steward.sqlite'
            previous = None
            try:
                import os

                previous = os.environ.get('CLOUD_BRIDGE_STEWARD_DB_PATH')
                os.environ['CLOUD_BRIDGE_STEWARD_DB_PATH'] = str(db_path)
                payload = run_steward_adapter('home')
                self.assertEqual(payload['schemaVersion'], 'steward-cloudbridge/v1')
                self.assertIn('oneNextStep', payload)
            finally:
                import os

                if previous is None:
                    os.environ.pop('CLOUD_BRIDGE_STEWARD_DB_PATH', None)
                else:
                    os.environ['CLOUD_BRIDGE_STEWARD_DB_PATH'] = previous


if __name__ == '__main__':
    unittest.main()
