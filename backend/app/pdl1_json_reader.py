"""Isolate full JSON parsing/encoding from the API server's Python interpreter."""
import json
import math
import sys
import time
from pathlib import Path


def prepare(path, config, receipt):
    started = time.perf_counter()
    try:
        with Path(path).open(encoding="utf-8") as stream:
            result = json.load(stream)
    except FileNotFoundError:
        return None, {"status":404,"detail":"No saved PD-L1 JSON for this slide and tissue"}
    except (OSError, ValueError):
        return None, {"status":422,"detail":"Saved PD-L1 JSON could not be read"}
    elapsed = (time.perf_counter()-started)*1000
    score = result.get('pd_score') if isinstance(result,dict) else None
    if not isinstance(score,dict) or score.get('score_type') != config['score_type']:
        return None, {"status":422,"detail":"Saved JSON does not contain the selected PD-L1 score"}
    value=score.get('score')
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not 0<=value<=100:
        return None, {"status":422,"detail":"Saved JSON contains an invalid PD-L1 score"}
    if config['score_type']=='CPS' and (score.get('class_schema')!=config['class_schema'] or result.get('model_runtime')!=config['runtime']):
        return None, {"status":409,"detail":"Saved PD-L1 result belongs to an older model. Run AI analysis with the current model first."}
    grade=score.get('grade')
    metadata={'ai_json_elapsed_ms':elapsed,'ai_percentage':value,
              'ai_grade':str(grade)[:80] if grade is not None else None,
              'score_type':config['score_type'],'ai_class_schema':score.get('class_schema')}
    payload={'ai_read_id':receipt,**metadata,'result':result}
    return payload, metadata


if __name__=='__main__':
    payload, metadata=prepare(sys.argv[1],json.loads(sys.argv[2]),sys.argv[3])
    sys.stderr.write(json.dumps(metadata,allow_nan=False))
    if payload is not None:
        # Encoding and the large object graph stay in this disposable process.
        sys.stdout.write(json.dumps(payload,ensure_ascii=False,separators=(',',':'),allow_nan=False))
