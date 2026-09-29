"""Regression tests requiring no model weights and using only temporary data."""
import asyncio
import os
import socket
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services import store_service as store
from tasks.text_generation import ChatTemplateVariant, ReasoningVariant
from api.server import APIServer
from runtime import _AsyncLockView, run_blocking


class ConcurrencyTests(unittest.IsolatedAsyncioTestCase):
    async def test_cancelled_waiter_does_not_steal_inference_lock(self):
        lock = threading.Lock()
        lock.acquire()
        waiter = asyncio.create_task(_AsyncLockView(lock).__aenter__())
        await asyncio.sleep(0.03)
        waiter.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await waiter
        lock.release()
        await asyncio.sleep(0.03)
        self.assertTrue(lock.acquire(blocking=False))
        lock.release()

    async def test_cancelled_inference_keeps_lock_until_worker_finishes(self):
        lock, started, finish = threading.Lock(), threading.Event(), threading.Event()
        def work():
            started.set()
            finish.wait(2)
        async def request():
            async with _AsyncLockView(lock):
                await run_blocking(work)
        request_task = asyncio.create_task(request())
        while not started.is_set():
            await asyncio.sleep(0.01)
        try:
            request_task.cancel()
            await asyncio.sleep(0.03)
            self.assertTrue(lock.locked())
        finally:
            finish.set()
        with self.assertRaises(asyncio.CancelledError):
            await request_task
        self.assertFalse(lock.locked())


class McpTests(unittest.IsolatedAsyncioTestCase):
    async def test_real_stdio_handshake_and_status_tool(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            port = probe.getsockname()[1]
        server = APIServer()
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {'ZEROINFER_DATA_DIR': directory}):
                try:
                    self.assertTrue((await asyncio.to_thread(server.start, port))['running'])
                    params = StdioServerParameters(command=sys.executable,
                        args=['-B', '-m', 'mcp_server.server', '--url', f'http://127.0.0.1:{port}', '--output-dir', directory],
                        cwd=str(Path(__file__).resolve().parents[1]),
                        env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
                    async with stdio_client(params) as (read, write):
                        async with ClientSession(read, write) as session:
                            initialized = await session.initialize()
                            self.assertEqual(initialized.serverInfo.name, 'zeroinfer')
                            tools = await session.list_tools()
                            self.assertIn('generate_text', [tool.name for tool in tools.tools])
                            result = await session.call_tool('zeroinfer_status', {})
                            self.assertFalse(result.isError, str(result.content))
                            self.assertIn(str(port), str(result.content))
                finally:
                    await asyncio.to_thread(server.stop)


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {'ZEROINFER_DATA_DIR': self.temp.name})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def test_concurrent_settings_merge_keeps_every_change(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda n: store.save_settings({f'key{n}': n}), range(30)))
        self.assertEqual(len(store.get_settings()), 30)

    def test_validate_settings_before_writing(self):
        store.save_settings({'theme': 'light', 'apiPort': 11600, 'temperature': 0})
        for value in ({'apiPort': 80}, {'apiPort': 11500.5}, {'maxNewTokens': -1},
                      {'personalizationEnabled': 'yes'}, {'customInstructions': 'x' * 4001}):
            with self.assertRaises(ValueError):
                store.save_settings(value)
        self.assertEqual(store.get_settings(), {'theme': 'light', 'apiPort': 11600, 'temperature': 0})

    def test_export_contains_sessions_and_no_settings_or_credentials(self):
        store.save_settings({'customInstructions': 'Not part of export'})
        store.save_chat({'id': 'c-one', 'messages': [{'role': 'user', 'text': 'hello'}]})
        result = store.export_chats()
        self.assertEqual(result['format'], 'zeroinfer-sessions')
        self.assertEqual(result['sessions'][0]['id'], 'c-one')
        self.assertNotIn('customInstructions', str(result))


class ChatTests(unittest.TestCase):
    def fake_pipeline(self):
        class Pipe:
            def __init__(self):
                self.messages = None
                self.tokenizer = SimpleNamespace(apply_chat_template=self.template)
            def template(self, messages, **kwargs):
                self.messages = messages
                return 'PROMPT'
            def __call__(self, prompt, **kwargs):
                return [{'generated_text': prompt + '<think>private scratch</think>Blue'}]
        return Pipe()

    def test_template_receives_system_and_history(self):
        pipe = self.fake_pipeline()
        inputs = {'text': 'Which color?', 'messages': [{'role': 'system', 'content': 'Be concise'},
            {'role': 'user', 'content': 'Blue'}, {'role': 'assistant', 'content': 'OK'},
            {'role': 'user', 'content': 'Which color?'}]}
        variant = ChatTemplateVariant()
        self.assertTrue(variant.can_handle({'model_id': 'Qwen/Qwen3-0.6B'}, inputs))
        result = variant.run(SimpleNamespace(pipe=pipe), inputs, {'max_new_tokens': 64})
        self.assertEqual(pipe.messages, inputs['messages'])
        self.assertNotIn('PROMPT', result['text'])

    def test_reasoning_strips_prompt_and_thoughts(self):
        result = ReasoningVariant().run(SimpleNamespace(pipe=self.fake_pipeline()), {'text': 'Which color?'}, {})
        self.assertEqual(result['text'], 'Blue')


class ApiTests(unittest.TestCase):
    def test_invalid_port_has_actionable_error(self):
        server = APIServer()
        self.assertIn('1024', server.start(80)['error'])

    def test_busy_port_reports_failure_and_server_can_recover(self):
        with socket.socket() as occupied:
            occupied.bind(('127.0.0.1', 0))
            occupied.listen(1)
            port = occupied.getsockname()[1]
            server = APIServer()
            result = server.start(port)
            self.assertFalse(result['running'])
            self.assertIsNotNone(result['error'])
        try:
            result = server.start(port)
            self.assertTrue(result['running'], result)
            self.assertEqual(result['port'], port)
        finally:
            self.assertFalse(server.stop()['running'])


if __name__ == '__main__':
    unittest.main()
