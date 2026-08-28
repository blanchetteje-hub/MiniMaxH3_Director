import os
import signal
import subprocess
import sys
import time
import unittest
from unittest import mock

import minimax


class EmergencyStopTests(unittest.TestCase):
    def test_installer_registers_python_interrupt_handlers(self):
        expected_signals = [signal.SIGINT]
        if os.name == "nt" and hasattr(signal, "SIGBREAK"):
            expected_signals.append(signal.SIGBREAK)

        with mock.patch("minimax.signal.signal") as register, mock.patch(
            "minimax._install_windows_console_handler",
        ), mock.patch("minimax._install_windows_kill_on_exit_job"):
            minimax.install_immediate_interrupt_handlers()

        self.assertEqual(
            [call.args[0] for call in register.call_args_list],
            expected_signals,
        )

    @unittest.skipUnless(os.name == "nt", "Windows console-event test")
    def test_ctrl_c_stops_blocked_process_immediately(self):
        child_code = "\n".join(
            [
                "import os",
                "import subprocess",
                "import sys",
                "import time",
                "sys.path.insert(0, os.getcwd())",
                "import minimax",
                "minimax.install_immediate_interrupt_handlers()",
                "worker = subprocess.Popen([sys.executable, '-c', "
                "'import time; time.sleep(60)'])",
                "print(f'READY {worker.pid}', flush=True)",
                "time.sleep(60)",
            ]
        )
        process = subprocess.Popen(
            [sys.executable, "-c", child_code],
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            ready, worker_pid = process.stdout.readline().strip().split()
            self.assertEqual(ready, "READY")
            worker_pid = int(worker_pid)
            started = time.monotonic()
            process.send_signal(signal.CTRL_C_EVENT)
            _, stderr = process.communicate(timeout=5)
            elapsed = time.monotonic() - started
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()

        self.assertEqual(process.returncode, 130, stderr)
        self.assertLess(elapsed, 2)
        self.assertFalse(self._windows_process_exists(worker_pid))

    @staticmethod
    def _windows_process_exists(process_id):
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel32.OpenProcess.restype = wintypes.HANDLE
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        handle = kernel32.OpenProcess(0x1000, False, process_id)
        if not handle:
            return False
        kernel32.CloseHandle(handle)
        return True


if __name__ == "__main__":
    unittest.main()
