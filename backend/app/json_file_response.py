"""Stream saved JSON inside a small metadata envelope without parsing its body.

The files are application-written JSON. Avoiding a giant Python object also
avoids FastAPI's recursive encoding and stdlib JSON's GIL-bound serialization.
"""
import json

import anyio
from starlette.responses import StreamingResponse

CHUNK_SIZE = 64 * 1024


class JsonFileEnvelopeResponse(StreamingResponse):
    def __init__(self, file, metadata):
        self.file = file
        prefix = json.dumps(metadata, ensure_ascii=True, separators=(',', ':')).encode('utf-8')
        prefix = prefix[:-1] + (b',' if metadata else b'') + b'"result":'

        async def chunks():
            yield prefix
            while True:
                data = await file.read(CHUNK_SIZE)
                if not data:
                    break
                yield data
            yield b'}'

        super().__init__(chunks(), media_type='application/json', headers={'Cache-Control': 'no-store'})

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            # Also runs on disconnect/send failure, even before body iteration.
            with anyio.CancelScope(shield=True):
                await self.file.aclose()


async def json_file_envelope(path, metadata):
    # Open before returning so missing/unreadable files become ordinary errors,
    # rather than failed streams after a 200 response has already been sent.
    file = await anyio.open_file(path, 'rb')
    try:
        return JsonFileEnvelopeResponse(file, metadata)
    except BaseException:
        with anyio.CancelScope(shield=True):
            await file.aclose()
        raise
