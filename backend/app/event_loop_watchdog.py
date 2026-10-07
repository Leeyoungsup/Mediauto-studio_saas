"""Capture native-thread stacks during stalls, not just after recovery."""
import asyncio
import faulthandler
import logging
import sys


async def monitor_event_loop_delay(interval=1.0, threshold=1.0, cooldown=30.0):
    """The native timer can dump stacks even when Python's GIL is held.

    Output contains code locations only, never frame locals/request payloads.
    Limit dumps to one per cooldown; cancel the process-wide timer on shutdown.
    """
    loop = asyncio.get_running_loop()
    next_dump = 0.0
    armed = False
    try:
        while True:
            expected = loop.time() + interval
            if loop.time() >= next_dump:
                try:
                    faulthandler.dump_traceback_later(
                        interval + threshold, repeat=False, file=sys.stderr
                    )
                    armed = True
                except (OSError, ValueError, RuntimeError):
                    # Some GUI launchers have no usable stderr file descriptor.
                    armed = False
            await asyncio.sleep(interval)
            delay = loop.time() - expected
            if armed:
                faulthandler.cancel_dump_traceback_later()
                if delay >= threshold:
                    next_dump = loop.time() + cooldown
                armed = False
            if delay >= threshold:
                logging.getLogger('uvicorn.error').warning(
                    '[event_loop] Request processing delayed by %.2fs; '
                    'look for the preceding Timeout thread stacks', delay
                )
    finally:
        if armed:
            faulthandler.cancel_dump_traceback_later()
