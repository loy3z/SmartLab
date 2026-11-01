"""Tests for the durable background scheduler management command."""

from io import StringIO
from types import SimpleNamespace
from unittest import mock

from django.core.management import call_command as django_call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase

from booking.repository import MemoryRepository


class SchedulerCommandTests(SimpleTestCase):
    def run_command(self, *args, stderr=None):
        stdout = StringIO()
        django_call_command("run_scheduler", *args, stdout=stdout, stderr=stderr or StringIO())
        return stdout.getvalue()

    @staticmethod
    def durable_service():
        return SimpleNamespace(repo=object())

    def test_once_runs_due_processing_with_the_requested_outlook_limit(self):
        with mock.patch(
            "booking.management.commands.run_scheduler.get_service",
            return_value=self.durable_service(),
        ), mock.patch("booking.management.commands.run_scheduler.call_command") as process_due:
            self.run_command("--once", "--outlook-limit", "7")

        process_due.assert_called_once()
        self.assertEqual(process_due.call_args.args, ("process_due",))
        self.assertEqual(process_due.call_args.kwargs["outlook_limit"], 7)
        self.assertEqual(process_due.call_args.kwargs["email_limit"], 50)

    def test_refuses_process_local_memory_data(self):
        service = SimpleNamespace(repo=MemoryRepository())
        with mock.patch(
            "booking.management.commands.run_scheduler.get_service",
            return_value=service,
        ), self.assertRaises(CommandError) as failed:
            self.run_command("--once")

        self.assertIn("shared durable repository", str(failed.exception))

    def test_rejects_unsafe_interval_and_outlook_limits(self):
        for arguments in (
            ("--once", "--interval-seconds", "0"),
            ("--once", "--interval-seconds", "3601"),
            ("--once", "--outlook-limit", "101"),
            ("--once", "--email-limit", "501"),
        ):
            with self.subTest(arguments=arguments), self.assertRaises(CommandError):
                self.run_command(*arguments)

    def test_continuous_mode_retries_after_one_failed_cycle(self):
        stop_requested = mock.Mock()
        stop_requested.wait.side_effect = [False, True]
        stderr = StringIO()
        with mock.patch(
            "booking.management.commands.run_scheduler.get_service",
            return_value=self.durable_service(),
        ), mock.patch(
            "booking.management.commands.run_scheduler.Event",
            return_value=stop_requested,
        ), mock.patch(
            "booking.management.commands.run_scheduler.call_command",
            side_effect=[RuntimeError("database temporarily unavailable"), None],
        ) as process_due, mock.patch(
            "booking.management.commands.run_scheduler.signal.signal"
        ), mock.patch(
            "booking.management.commands.run_scheduler.signal.getsignal",
            return_value=signal_default_handler(),
        ), mock.patch(
            "booking.management.commands.run_scheduler.logger.exception"
        ):
            self.run_command("--interval-seconds", "1", stderr=stderr)

        self.assertEqual(process_due.call_count, 2)
        self.assertIn("The next cycle will retry", stderr.getvalue())

    def test_once_reports_processing_failure_to_the_caller(self):
        with mock.patch(
            "booking.management.commands.run_scheduler.get_service",
            return_value=self.durable_service(),
        ), mock.patch(
            "booking.management.commands.run_scheduler.call_command",
            side_effect=RuntimeError("database unavailable"),
        ), mock.patch(
            "booking.management.commands.run_scheduler.logger.exception"
        ), self.assertRaises(CommandError) as failed:
            self.run_command("--once")

        self.assertIn("database unavailable", str(failed.exception))


class EmailWorkerConnectionTests(SimpleTestCase):
    def test_worker_clears_old_database_connections_before_each_batch(self):
        # 2026-11-01: this thread has no requests, so nothing else clears a connection the server has closed.
        from booking.email_channel import EmailOutbox

        calls = mock.Mock()
        service = SimpleNamespace(email_delivery=SimpleNamespace(process_pending=calls.process_pending))
        outbox = EmailOutbox()
        outbox.BATCH_WINDOW_SECONDS = 0
        with mock.patch("booking.runtime.get_service", return_value=service), \
                mock.patch("booking.email_channel.close_old_connections", calls.close_old_connections):
            outbox.put("notification")
            self.assertTrue(outbox.wait(5))
        self.assertEqual([call[0] for call in calls.mock_calls], ["close_old_connections", "process_pending"])


def signal_default_handler():
    """Return a stable sentinel that can be restored as a signal handler in the test."""
    return mock.sentinel.default_signal_handler
