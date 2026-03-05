from __future__ import annotations

import os
import shlex
import subprocess
import tempfile
import threading
import time
from datetime import datetime
from datetime import timezone
from queue import Empty
from queue import Queue
from typing import Protocol
from typing import TextIO

from agent1.adapters.codex.contracts import CodexStreamEvent
from agent1.adapters.codex.contracts import CodexStreamEventType
from agent1.adapters.codex.contracts import CodexTaskInput
from agent1.adapters.codex.contracts import StreamEventHandler
from agent1.config.settings import Settings
from agent1.config.settings import get_settings
from agent1.core.contracts import ExecutionResult
from agent1.core.contracts import ExecutionStatus

STREAM_END_EVENT: tuple[None, str] = (None, '')
PROCESS_EXIT_WAIT_SECONDS = 2


def _utc_now() -> datetime:

    '''
    Create timezone-aware UTC timestamp for Codex stream event payloads.

    Returns:
    datetime: Current UTC timestamp.
    '''

    return datetime.now(timezone.utc)


class CodexCliAdapter(Protocol):
    def execute(
        self,
        task_input: CodexTaskInput,
        event_handler: StreamEventHandler | None = None,
    ) -> ExecutionResult:
        ...

    def cancel(self, task_id: str) -> bool:
        ...


class SubprocessCodexCliAdapter:
    def __init__(
        self,
        base_command: list[str] | None = None,
        default_timeout_seconds: int | None = None,
        settings: Settings | None = None,
    ) -> None:
        runtime_settings = settings or get_settings()
        resolved_base_command = base_command or shlex.split(runtime_settings.codex_cli_command)
        self._base_command = self._normalize_base_command(resolved_base_command)
        self._default_timeout_seconds = default_timeout_seconds or runtime_settings.codex_cli_timeout_seconds
        self._active_processes: dict[str, subprocess.Popen[str]] = {}
        self._cancelled_tasks: set[str] = set()
        self._lock = threading.Lock()
        self._codex_login_verified = False
        self._codex_login_lock = threading.Lock()

    def _normalize_base_command(self, base_command: list[str]) -> list[str]:
        if len(base_command) == 0:
            return base_command
        if base_command[0] != 'codex':
            return base_command
        if len(base_command) == 1:
            return ['codex', 'exec', '--skip-git-repo-check']
        if base_command[1].startswith('-'):
            return ['codex', 'exec', '--skip-git-repo-check', *base_command[1:]]

        return base_command

    def _emit_event(
        self,
        task_id: str,
        event_type: CodexStreamEventType,
        message: str,
        event_handler: StreamEventHandler | None,
    ) -> None:
        if event_handler is None:
            return

        event_handler(
            CodexStreamEvent(
                task_id=task_id,
                event_type=event_type,
                timestamp=_utc_now(),
                message=message,
            )
        )

    def _stream_reader(
        self,
        stream: TextIO,
        event_type: CodexStreamEventType,
        stream_queue: Queue[tuple[CodexStreamEventType | None, str]],
    ) -> None:
        for raw_line in iter(stream.readline, ''):
            stream_queue.put((event_type, raw_line.rstrip('\n')))

        stream_queue.put(STREAM_END_EVENT)

    def _build_command(self, task_input: CodexTaskInput) -> list[str]:
        return [*self._base_command, *task_input.arguments]

    def _ensure_codex_authenticated(self) -> None:
        if len(self._base_command) == 0 or self._base_command[0] != 'codex':
            return
        if self._codex_login_verified:
            return

        openai_api_key = os.getenv('OPENAI_API_KEY', '').strip()
        if openai_api_key == '':
            return

        with self._codex_login_lock:
            if self._codex_login_verified:
                return

            login_process = subprocess.run(
                ['codex', 'login', '--with-api-key'],
                input=f'{openai_api_key}\n',
                text=True,
                capture_output=True,
                env=os.environ.copy(),
                check=False,
            )
            if login_process.returncode != 0:
                login_stderr = login_process.stderr.strip()
                if login_stderr == '':
                    login_stderr = 'codex login failed without stderr output'
                raise RuntimeError(login_stderr)

            self._codex_login_verified = True

    def _terminate_process(self, process: subprocess.Popen[str]) -> None:
        if process.poll() is not None:
            return

        process.terminate()
        try:
            process.wait(timeout=PROCESS_EXIT_WAIT_SECONDS)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=PROCESS_EXIT_WAIT_SECONDS)

    def _register_process(self, task_id: str, process: subprocess.Popen[str]) -> None:
        with self._lock:
            self._active_processes[task_id] = process
            self._cancelled_tasks.discard(task_id)

    def _unregister_process(self, task_id: str) -> None:
        with self._lock:
            self._active_processes.pop(task_id, None)
            self._cancelled_tasks.discard(task_id)

    def _is_cancelled(self, task_id: str) -> bool:
        with self._lock:
            return task_id in self._cancelled_tasks

    def cancel(self, task_id: str) -> bool:

        '''
        Create cancellation request for an active Codex task process.

        Args:
        task_id (str): Task identifier currently running in adapter process table.

        Returns:
        bool: True when cancellation signal is applied, otherwise False.
        '''

        with self._lock:
            process = self._active_processes.get(task_id)
            if process is None:
                return False

            self._cancelled_tasks.add(task_id)
            process.terminate()
            return True

    def execute(
        self,
        task_input: CodexTaskInput,
        event_handler: StreamEventHandler | None = None,
    ) -> ExecutionResult:

        '''
        Create Codex execution result with stream events, timeout, and cancellation handling.

        Args:
        task_input (CodexTaskInput): Task input contract for command execution.
        event_handler (StreamEventHandler | None): Optional stream event callback.

        Returns:
        ExecutionResult: Parsed execution result contract.
        '''

        self._ensure_codex_authenticated()
        timeout_seconds = task_input.timeout_seconds or self._default_timeout_seconds
        command = self._build_command(task_input)
        output_last_message_path: str | None = None
        if '--output-last-message' not in command and '-o' not in command:
            with tempfile.NamedTemporaryFile(
                prefix='agent1-codex-last-message-',
                suffix='.txt',
                delete=False,
            ) as output_file_handle:
                output_last_message_path = output_file_handle.name
            command = [*command, '--output-last-message', output_last_message_path]
        shell_command = shlex.join(command)
        deadline = time.monotonic() + timeout_seconds
        started_at = time.monotonic()
        process = subprocess.Popen(
            command,
            cwd=task_input.working_directory,
            env={**os.environ, **task_input.environment},
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self._register_process(task_input.task_id, process)
        self._emit_event(
            task_input.task_id,
            CodexStreamEventType.STARTED,
            shell_command,
            event_handler,
        )

        if process.stdin is not None:
            process.stdin.write(task_input.prompt)
            process.stdin.write('\n')
            process.stdin.flush()
            process.stdin.close()

        stream_queue: Queue[tuple[CodexStreamEventType | None, str]] = Queue()
        readers: list[threading.Thread] = []
        if process.stdout is not None:
            stdout_reader = threading.Thread(
                target=self._stream_reader,
                args=(process.stdout, CodexStreamEventType.STDOUT, stream_queue),
                daemon=True,
            )
            readers.append(stdout_reader)
            stdout_reader.start()
        if process.stderr is not None:
            stderr_reader = threading.Thread(
                target=self._stream_reader,
                args=(process.stderr, CodexStreamEventType.STDERR, stream_queue),
                daemon=True,
            )
            readers.append(stderr_reader)
            stderr_reader.start()

        output_lines: list[str] = []
        error_lines: list[str] = []
        finished_readers = 0
        timed_out = False
        cancelled = False

        while True:
            if not timed_out and process.poll() is None and time.monotonic() >= deadline:
                timed_out = True
                self._terminate_process(process)
                self._emit_event(
                    task_input.task_id,
                    CodexStreamEventType.TIMEOUT,
                    f'Timed out after {timeout_seconds} seconds.',
                    event_handler,
                )

            if not cancelled and self._is_cancelled(task_input.task_id):
                cancelled = True
                if process.poll() is None:
                    self._terminate_process(process)
                self._emit_event(
                    task_input.task_id,
                    CodexStreamEventType.CANCELLED,
                    'Cancelled by runtime request.',
                    event_handler,
                )

            try:
                stream_event_type, stream_message = stream_queue.get(timeout=0.1)
                if stream_event_type is None:
                    finished_readers += 1
                elif stream_event_type is CodexStreamEventType.STDOUT:
                    output_lines.append(stream_message)
                    self._emit_event(
                        task_input.task_id,
                        CodexStreamEventType.STDOUT,
                        stream_message,
                        event_handler,
                    )
                else:
                    error_lines.append(stream_message)
                    self._emit_event(
                        task_input.task_id,
                        CodexStreamEventType.STDERR,
                        stream_message,
                        event_handler,
                    )
            except Empty:
                pass

            if process.poll() is not None and finished_readers >= len(readers) and stream_queue.empty():
                break

        for reader in readers:
            reader.join(timeout=PROCESS_EXIT_WAIT_SECONDS)

        exit_code = process.poll()
        duration_seconds = round(time.monotonic() - started_at, 3)
        last_message = ''
        if output_last_message_path is not None:
            try:
                with open(output_last_message_path, encoding='utf-8') as output_file_handle:
                    last_message = output_file_handle.read().strip()
            finally:
                try:
                    os.remove(output_last_message_path)
                except OSError:
                    pass
        if cancelled:
            status = ExecutionStatus.BLOCKED
            summary = 'Codex command cancelled by runtime request.'
        elif timed_out:
            status = ExecutionStatus.FAILED
            summary = f'Codex command timed out after {timeout_seconds} seconds.'
        elif exit_code == 0:
            status = ExecutionStatus.SUCCEEDED
            summary = 'Codex command completed successfully.'
            self._emit_event(
                task_input.task_id,
                CodexStreamEventType.COMPLETED,
                summary,
                event_handler,
            )
        else:
            status = ExecutionStatus.FAILED
            summary = f'Codex command failed with exit code {exit_code}.'
            self._emit_event(
                task_input.task_id,
                CodexStreamEventType.FAILED,
                summary,
                event_handler,
            )

        self._unregister_process(task_input.task_id)
        return ExecutionResult(
            status=status,
            summary=summary,
            command=shell_command,
            exit_code=exit_code,
            metadata={
                'stdout': output_lines,
                'stderr': error_lines,
                'last_message': last_message,
                'duration_seconds': duration_seconds,
                'timed_out': timed_out,
                'cancelled': cancelled,
            },
        )


__all__ = ['CodexCliAdapter', 'SubprocessCodexCliAdapter']
