"use client";

import { useEffect, useRef, useState } from "react";

export type Example = { q: string; company: string; kind: string; route: string };

type Source = { rcept_no: string; title: string; url: string };
type Verified = { value: string; line: string; rcept_no: string; title: string };
type Answer = {
  question: string;
  answer: string;
  unanswerable: boolean;
  sources: Source[];
  verified: Verified[];
  model: string;
  cached: boolean;
};

type Step = { label: string; ms: number };
type Turn = {
  id: number;
  q: string;
  steps: Step[];
  answer?: Answer;
  error?: string;
  loading: boolean;
  totalMs?: number;
};

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

/** SSE 스트림을 읽어 step 이벤트는 콜백으로 넘기고, result를 돌려준다. */
async function ask(question: string, onStep: (label: string) => void): Promise<Answer> {
  const res = await fetch(`${API}/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, stream: true }),
  });
  if (res.status === 429) {
    const body = await res.json();
    throw new Error(body.detail ?? "오늘 질문 한도를 넘었습니다.");
  }
  if (res.status === 422) throw new Error("질문은 2~300자로 입력해 주세요.");
  if (!res.ok || !res.body) throw new Error(`서버 응답 ${res.status}`);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let result: Answer | null = null;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() ?? "";
    for (const block of blocks) {
      const event = /^event: (.+)$/m.exec(block)?.[1];
      const data = /^data: (.+)$/m.exec(block)?.[1];
      if (!event || !data) continue;
      const payload = JSON.parse(data);
      if (event === "step") onStep(payload.label);
      if (event === "result") result = payload;
      if (event === "error") throw new Error(payload.detail);
    }
  }
  if (!result) throw new Error("답변을 받지 못했습니다.");
  return result;
}

/** 답변 문장을 '확인된 숫자'와 나머지로 나눈다. 인용 번호 [1]은 출처 목록으로 대신한다. */
function splitAnswer(text: string, verified: Verified[]) {
  const clean = text.replace(/\s?\[\d+\](\[\d+\])*/g, "");
  const values = [...new Set(verified.map((v) => v.value))].sort((a, b) => b.length - a.length);
  if (!values.length) return [{ text: clean }];
  const escaped = values.map((v) => v.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const parts = clean.split(new RegExp(`(${escaped.join("|")})`, "g"));
  return parts.filter(Boolean).map((p) => (values.includes(p) ? { text: p, num: p } : { text: p }));
}

/** 이벤트 처리 안에서만 부른다 (렌더 중 호출 아님). */
const clock = () => performance.now();

const sec = (ms: number) => `${(ms / 1000).toFixed(1)}s`;

function AnswerView({ turn }: { turn: Turn }) {
  const answer = turn.answer!;
  const [picked, setPicked] = useState<string | null>(null);
  const match = answer.verified.find((v) => v.value === picked);
  const parts = splitAnswer(answer.answer, answer.verified);
  const nums = new Set(answer.verified.map((v) => v.value)).size;

  return (
    <>
      <p className="answer">
        {parts.map((p, i) =>
          p.num ? (
            <button
              key={i}
              type="button"
              className="num"
              aria-pressed={picked === p.num}
              title="원문에서 확인한 숫자 · 눌러서 원문 보기"
              onClick={() => setPicked(picked === p.num ? null : p.num!)}
            >
              {p.text}
            </button>
          ) : (
            <span key={i}>{p.text}</span>
          ),
        )}
      </p>

      {match && (
        <div className="evidence" role="status">
          <div className="evidence-head">✓ 원문 대조 · {match.value}</div>
          <div className="evidence-line">{match.line}</div>
          <div className="evidence-src">{match.title.replace(/ \| 접수번호.*/, "")} · 접수번호 {match.rcept_no}</div>
        </div>
      )}

      <div className="answer-meta">
        {answer.unanswerable ? (
          <span className="chip warn">답변 불가</span>
        ) : nums > 0 ? (
          <span className="chip ok">
            원문 대조 숫자 <b>{nums}</b> · 숫자를 눌러 확인
          </span>
        ) : null}
        <span className="chip">
          출처 <b>{answer.sources.length}</b>
        </span>
        <span className="chip">
          {answer.cached ? "저장된 답변" : "응답"} <b>{turn.totalMs != null ? sec(turn.totalMs) : "-"}</b>
        </span>
      </div>

      {answer.sources.length > 0 && (
        <>
          <div className="sources-title" style={{ marginTop: 18 }}>
            출처 (DART 원문)
          </div>
          <ol className="sources">
            {answer.sources.map((s) => (
              <li key={s.rcept_no}>
                <a href={s.url} target="_blank" rel="noreferrer">
                  <span>
                    {s.title.replace(/ \| 접수번호 \d+.*/, "")} <span className="rcept">{s.rcept_no} ↗</span>
                  </span>
                </a>
              </li>
            ))}
          </ol>
        </>
      )}
    </>
  );
}

function TurnView({ turn }: { turn: Turn }) {
  return (
    <article className="turn" aria-live="polite">
      <h2 className="question">
        <span className="prompt">&gt;</span>
        <span>{turn.q}</span>
      </h2>
      <ol className="log" aria-label="진행 단계">
        {turn.steps.map((s, i) => (
          <li key={i} className="ok">
            <span>{s.label}</span>
            <time>{sec(s.ms)}</time>
          </li>
        ))}
        {turn.loading && (
          <li className="now">
            <span>{turn.steps.length ? "처리 중" : "질문 분석 중"}</span>
            <time>처음 묻는 질문은 15~30초</time>
          </li>
        )}
      </ol>
      {turn.answer && <AnswerView turn={turn} />}
      {turn.error && <p className="error">{turn.error}</p>}
    </article>
  );
}

export default function Chat({ examples, companyCount }: { examples: Example[]; companyCount: number }) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState("");
  const threadRef = useRef<HTMLDivElement>(null);
  const nextId = useRef(1);
  const busy = turns.some((t) => t.loading);

  const update = (id: number, fn: (t: Turn) => Turn) =>
    setTurns((ts) => ts.map((t) => (t.id === id ? fn(t) : t)));

  const run = async (q: string) => {
    const id = nextId.current++;
    const start = clock();
    let last = start;
    setTurns((ts) => [...ts, { id, q, steps: [], loading: true }]);
    try {
      const answer = await ask(q, (label) => {
        const now = clock();
        const ms = now - last;
        last = now;
        update(id, (t) => ({ ...t, steps: [...t.steps, { label, ms }] }));
      });
      update(id, (t) => ({ ...t, answer, loading: false, totalMs: clock() - start }));
    } catch (e) {
      const msg =
        e instanceof TypeError ? "데모 서버에 연결하지 못했습니다. 잠시 뒤 다시 시도해 주세요." : (e as Error).message;
      update(id, (t) => ({ ...t, error: msg, loading: false }));
    }
  };

  const count = turns.length;
  // 새 질문이 생기거나 마지막 답변이 도착하면, 마지막 질문이 화면 위쪽에 오도록 맞춘다.
  const last = turns[turns.length - 1];
  const settled = last ? Boolean(last.answer || last.error) : false;
  useEffect(() => {
    if (!count) return;
    const turnsEl = threadRef.current?.querySelectorAll(".turn");
    turnsEl?.[turnsEl.length - 1]?.scrollIntoView({ block: settled ? "start" : "end" });
  }, [count, settled]);

  const reset = () => {
    setTurns([]);
    setDraft("");
  };

  // 아직 묻지 않은 예시 질문 (답변 아래에 다음 질문으로 제안)
  const asked = new Set(turns.map((t) => t.q));
  const rest = examples.filter((ex) => !asked.has(ex.q)).slice(0, 3);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const q = draft.trim();
    if (q.length < 2 || busy) return;
    setDraft("");
    void run(q);
  };

  return (
    <>
      <div className="thread" ref={threadRef}>
        <div className="thread-inner">
          {turns.length === 0 ? (
            <section className="empty">
              <h1>DART 공시에 질문하세요</h1>
              <p className="empty-sub">공시 원문을 근거로 답하고, 답변의 숫자를 원문과 대조합니다.</p>
              <div className="empty-meta">
                <span className="chip">
                  기업 <b>{companyCount}</b> · 코스피 시총 상위
                </span>
                <span className="chip">
                  기간 <b>2024.01 – 2026.11</b>
                </span>
                <span className="chip">
                  공시 원문 <b>2,075</b>건
                </span>
              </div>

              <div className="examples">
                <div className="examples-head">
                  <span>예시 질문</span>
                  <span>경로</span>
                </div>
                {examples.map((ex) => (
                  <button key={ex.q} type="button" className="example" onClick={() => void run(ex.q)} disabled={busy}>
                    <span className="route" data-route={ex.route}>
                      {ex.route}
                    </span>
                    <span className="example-q">{ex.q}</span>
                    <span className="example-kind">{ex.kind}</span>
                  </button>
                ))}
              </div>
            </section>
          ) : (
            <>
              {turns.map((t) => (
                <TurnView key={t.id} turn={t} />
              ))}
              {!busy && (
                <nav className="next" aria-label="다음 질문">
                  {rest.length > 0 && <div className="next-title">다른 예시 질문</div>}
                  {rest.map((ex) => (
                    <button key={ex.q} type="button" className="next-q" onClick={() => void run(ex.q)}>
                      <span className="route" data-route={ex.route}>
                        {ex.route}
                      </span>
                      {ex.q}
                    </button>
                  ))}
                  <button type="button" className="next-reset" onClick={reset}>
                    ← 처음 화면으로
                  </button>
                </nav>
              )}
            </>
          )}
        </div>
      </div>

      <div className="composer">
        <form onSubmit={submit}>
          {turns.length > 0 && (
            <button type="button" className="reset" onClick={reset} title="새 대화" aria-label="새 대화">
              ＋
            </button>
          )}
          <label className="composer-box">
            <span className="prompt" aria-hidden="true">
              &gt;
            </span>
            <span className="sr-only" style={{ position: "absolute", width: 1, height: 1, overflow: "hidden" }}>
              질문
            </span>
            <input
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="예: 기아 2026년 결산배당은?"
              maxLength={300}
              autoComplete="off"
            />
          </label>
          <button className="send" type="submit" disabled={busy || draft.trim().length < 2}>
            질문
          </button>
        </form>
      </div>
    </>
  );
}
