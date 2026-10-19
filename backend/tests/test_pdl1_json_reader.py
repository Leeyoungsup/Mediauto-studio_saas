"""Large comparison JSON parsing leaves the API event loop responsive."""
import asyncio
import json
from app.pdl1_json_reader import prepare
from app.routers import pd_l1_comparison as routes


def test_reader_requires_complete_json(tmp_path):
    path=tmp_path/'result.json'
    path.write_text('{"pd_score":{"score_type":"TPS","score":20},"cells":[[1,2,1,.9]')
    payload, error=prepare(path, {'score_type':'TPS'}, 'receipt')
    assert payload is None and error['status']==422


def test_large_json_parse_and_encode_do_not_block_server_loop(tmp_path):
    path=tmp_path/'large.json'
    with path.open('w') as output:
        output.write('{"pd_score":{"score_type":"TPS","score":20},"cells":[')
        output.write(','.join(['[1,2,1,0.9,0,0,2,3]']*250000))
        output.write(']}')
    async def run():
        task=asyncio.create_task(routes.read_json(path,'Lung','receipt'))
        ticks=0
        while not task.done():
            await asyncio.sleep(.005);ticks+=1
        payload, metadata=await task
        assert ticks>=2
        assert metadata['ai_percentage']==20
        parsed=json.loads(payload)
        assert len(parsed['result']['cells'])==250000
        assert parsed['ai_read_id']=='receipt'
    asyncio.run(run())
