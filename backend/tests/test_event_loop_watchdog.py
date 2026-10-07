import os
from pathlib import Path
import subprocess
import sys


def test_blocked_loop_emits_stack_and_cancels_timer_on_shutdown():
    code = '''
import asyncio, time
from app.event_loop_watchdog import monitor_event_loop_delay

def blocking_work():
    time.sleep(.25)

async def main():
    task = asyncio.create_task(monitor_event_loop_delay(.02, .08, 30))
    await asyncio.sleep(.01)
    blocking_work()
    await asyncio.sleep(.03)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    time.sleep(.2)
asyncio.run(main())
'''
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]))
    result = subprocess.run([sys.executable, '-c', code], env=env,
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert 'blocking_work' in result.stderr
    assert '[event_loop] Request processing delayed' in result.stderr
    assert result.stderr.count('Timeout (') == 1
