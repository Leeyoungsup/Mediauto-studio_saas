import { api } from './api.js?v=20261012-pdl1-01';
import { esc } from './common-utils.js?v=20260604-01';

export function formatStopwatch(ms) {
    const seconds = Math.floor(Math.max(0, ms) / 1000);
    return [Math.floor(seconds / 3600), Math.floor(seconds / 60) % 60, seconds % 60]
        .map(value => String(value).padStart(2, '0')).join(':');
}

export class AssessmentClock {
    constructor(now = () => performance.now()) { this.now = now; this.reset(); }
    reset() { this.started = null; this.fixed = null; }
    start() { this.started = this.now(); this.fixed = null; }
    elapsed() { return this.fixed ?? (this.started === null ? 0 : Math.max(0, this.now() - this.started)); }
    stop() {
        if (this.started === null) throw new Error('슬라이드를 먼저 열어주세요.');
        this.fixed ??= Math.max(1, this.elapsed());
        return this.fixed;
    }
}

export function createPdl1Comparison() {
    const root = document.getElementById('pdl1-comparison-panel');
    const watch = document.getElementById('pdl1-stopwatch');
    if (!root || !watch) return null;
    root.hidden = false; watch.hidden = false;
    const clock = new AssessmentClock();
    const form = root.querySelector('form');
    const percent = root.querySelector('[name="percentage"]');
    const grade = root.querySelector('[name="grade"]');
    const tissue = root.querySelector('[name="tissue_type"]');
    const submit = root.querySelector('[type="submit"]');
    const message = root.querySelector('[data-message]');
    const history = root.querySelector('[data-history]');
    const aiTime = root.querySelector('[data-ai-time]');
    const doctorTime = root.querySelector('[data-doctor-time]');
    const summary = root.querySelector('[data-summary]');
    let slide = null, project = '', role = '', run = null, ai = null, readPromise = null;
    let controller = null, saving = false, saved = false, generation = 0, frozenInput = null;
    let historyGeneration = 0;
    const canWrite = () => ['admin', 'doctor'].includes(role);
    const setMessage = (text, error = false) => {
        message.textContent = text; message.classList.toggle('error', error);
    };
    const duration = ms => ms == null ? '—' : ms < 1000 ? `${ms.toFixed(3)} ms` : `${(ms / 1000).toFixed(3)}초`;
    function render() {
        watch.querySelector('output').textContent = formatStopwatch(clock.elapsed());
        watch.classList.toggle('running', !!slide && clock.fixed === null);
        doctorTime.textContent = slide ? duration(clock.elapsed()) : '—';
        aiTime.textContent = duration(ai?.ai_json_elapsed_ms);
        submit.disabled = !slide || !canWrite() || saving || saved;
        percent.disabled = grade.disabled = !slide || !canWrite() || saving || saved || !!frozenInput;
        tissue.disabled = saving || saved || !!frozenInput;
    }
    const interval = setInterval(render, 250);
    window.addEventListener('pagehide', () => { clearInterval(interval); controller?.abort(); }, { once: true });

    async function refreshHistory() {
        if (!project) { history.textContent = '프로젝트를 선택하면 기록이 표시됩니다.'; return; }
        const requested = project, version = ++historyGeneration;
        history.textContent = '기록을 불러오는 중…';
        try {
            const data = await api.listPdl1Comparisons(requested);
            if (version !== historyGeneration || requested !== project) return;
            if (!data.records.length) { history.textContent = '저장된 비교 기록이 없습니다.'; return; }
            history.innerHTML = data.records.map(record => `<article class="pdl1-history-record">
                <strong>${esc(record.filename)}</strong>
                <span>${esc(record.score_type)} · 전문의 ${esc(record.percentage)}% · Grade ${esc(record.grade)}</span>
                <span>전문의 ${esc(duration(record.specialist_elapsed_ms))} / AI JSON ${esc(duration(record.ai_json_elapsed_ms))}</span>
                <small>${esc(new Date(record.dt_created_at).toLocaleString())}</small>
            </article>`).join('');
        } catch (error) {
            if (version === historyGeneration) history.textContent = `기록 조회 실패: ${error.message}`;
        }
    }
    root.querySelector('[data-refresh]').addEventListener('click', refreshHistory);
    root.querySelector('[data-restart]').addEventListener('click', () => {
        if (!slide || saving || !canWrite()) return;
        if (clock.fixed === null && !window.confirm('현재 측정을 버리고 시간을 다시 시작할까요?')) return;
        openSlide(slide);
    });

    function loadJson() {
        controller?.abort(); ai = null;
        const version = generation;
        controller = new AbortController();
        const activeController = controller;
        const timeout = setTimeout(() => activeController.abort(), 30000);
        readPromise = api.readPdl1Json(slide.slideId, tissue.value, { signal: activeController.signal })
            .then(result => {
                if (version !== generation) return;
                ai = result; render();
            }).catch(error => {
                if (version !== generation) return;
                ai = null;
                aiTime.textContent = 'JSON 없음 / 읽기 실패';
                if (!saving && !saved) setMessage(`AI JSON을 불러오지 못했습니다. 전문의 결과는 기록할 수 있습니다. ${error.message}`);
            }).finally(() => clearTimeout(timeout));
    }

    function openSlide(context) {
        generation++;
        slide = { ...context }; project = context.project;
        run = crypto.randomUUID(); saved = false; saving = false; frozenInput = null; ai = null;
        percent.value = ''; grade.value = ''; summary.hidden = true;
        clock.start(); render();
        root.querySelector('[data-slide]').textContent = context.filename;
        setMessage(canWrite() ? '퍼센트와 Grade 입력 후 확인을 누르면 시간이 확정됩니다.' : '기록을 조회할 수 있습니다. 측정 저장은 전문의·관리자 계정에서 가능합니다.');
        loadJson();
        refreshHistory();
    }

    tissue.addEventListener('change', () => {
        if (!slide || saving || saved || frozenInput) return;
        generation++; percent.value = ''; grade.value = '';
        loadJson(); render(); // Changing score type is part of the specialist interval.
    });

    form.addEventListener('submit', async event => {
        event.preventDefault();
        if (!slide || saving || saved || !canWrite() || !form.reportValidity()) return;
        const percentage = Number(percent.value), trimmedGrade = grade.value.trim();
        if (!Number.isFinite(percentage) || percentage < 0 || percentage > 100 || !trimmedGrade) {
            setMessage('0~100 사이 퍼센트와 Grade를 입력해주세요.', true); return;
        }
        const version = generation;
        frozenInput ??= { percentage, grade: trimmedGrade, specialist_elapsed_ms: clock.stop() };
        saving = true; render(); setMessage('전문의 시간을 확정했습니다. 서버에 저장하는 중…');
        try {
            await readPromise; // Waiting for JSON or saving never extends the specialist interval.
            if (version !== generation) return;
            const record = await api.savePdl1Comparison({
                run_id: run, slide_id: slide.slideId, tissue_type: tissue.value,
                ai_read_id: ai?.ai_read_id ?? null, ...frozenInput,
            });
            if (version !== generation) return;
            saved = true; summary.hidden = false;
            const ratio = record.ai_json_elapsed_ms > 0 ? record.specialist_elapsed_ms / record.ai_json_elapsed_ms : null;
            summary.textContent = `전문의 ${duration(record.specialist_elapsed_ms)} · AI JSON ${duration(record.ai_json_elapsed_ms)}`
                + (ratio == null ? '' : ` · 시간 비율 ${ratio.toFixed(1)}배`)
                + (record.ai_percentage == null ? '' : ` · AI ${record.ai_percentage}%`)
                + (record.ai_grade == null ? '' : ` · AI Grade ${record.ai_grade}`);
            setMessage('저장했습니다. 프로젝트 기록에서 다시 확인할 수 있습니다.');
            refreshHistory();
        } catch (error) {
            if (version === generation) setMessage(`저장 실패: ${error.message} 같은 확정 시간으로 다시 확인할 수 있습니다.`, true);
        } finally {
            if (version === generation) { saving = false; render(); }
        }
    });
    render();
    return {
        openSlide,
        setUser(user) { role = user.str_role; render(); },
        setProject(path) {
            const next = String(path || '').split('/')[0];
            if (project === next) return;
            project = next; controller?.abort(); generation++; historyGeneration++;
            slide = null; clock.reset(); ai = null; frozenInput = null; saving = saved = false;
            summary.hidden = true; percent.value = ''; grade.value = '';
            root.querySelector('[data-slide]').textContent = '왼쪽 목록에서 슬라이드를 열어주세요.';
            setMessage('슬라이드를 열면 시간이 자동으로 시작됩니다.'); render(); refreshHistory();
        },
    };
}
