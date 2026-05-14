"""AI 파이프라인 모듈 — routers/ai.py 모놀리스에서 분리된 컴포넌트들.

이 패키지는 Detection / Quanti PD-L1 / Quanti IHC / Virtual-Stain 워커 함수와
공유 헬퍼(task state, cache paths, tissue mask) 를 모은다.
routers/ai.py 는 라우팅 + 인증/감사로그만 담당한다.
"""
