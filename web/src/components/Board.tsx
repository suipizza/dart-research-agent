"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export type Example = { q: string; company: string; kind: string; route: string };

type Source = { rcept_no: string; title: string; url: string };
type Verified = { value: string; line: string; rcept_no: string; title: string };
type Answer = {
  question: string;
  answer: string;
  unanswerable: boolean;
  sources: Source[];
  verified: Verified[];
  cached: boolean;
};

type RowState = {
  steps: string[];
  answer?: Answer;
  error?: string;
  loading: boolean;
};

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

/** SSE 스트림을 읽어 step / result / error 이벤트를 콜백으로 넘긴다. */
async function ask(
  question: string,
  onStep: (label: string) => void,
): Promise<Answer> {
  const res = await fetch(`${API}/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, stream: true }),
  });
  if (res.status === 429) {
    const body = await res.json();
    throw new Error(body.detail ?? "오늘 질문 한도를 넘었습니다.");
  }
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

/** 답변 문장에서 확인된 숫자를 눌러볼 수 있는 조각으로 나눈다. 인용 번호 [1]은 출처 목록으로 대신한다. */
function splitAnswer(text: string, verified: Verified[]) {
  const clean = text.replace(/\s?\[\d+\](\[\d+\])*/g, "");
  const values = [...new Set(verified.map((v) => v.value))].sort((a, b) => b.length - a.length);
  if (!values.length) return [{ text: clean }];
  const escaped = values.map((v) => v.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const parts = clean.split(new RegExp(`(${escaped.join("|")})`, "g"));
  return parts.filter(Boolean).map((p) => (values.includes(p) ? { text: p, num: p } : { text: p }));
}

function AnswerBody({ answer }: { answer: Answer }) {
  const [picked, setPicked] = useState<string | null>(null);
  const match = answer.verified.find((v) => v.value === picked);
  const parts = splitAnswer(answer.answer, answer.verified);
  return (
    <>
      <div className="answer">
        <p>
          {parts.map((p, i) =>
            p.num ? (
              <button
                key={i}
                type="button"
                className="num"
                aria-pressed={picked === p.num}
                onClick={() => setPicked(picked === p.num ? null : p.num!)}
              >
                {p.text}
              </button>
            ) : (
              <span key={i}>{p.text}</span>
            ),
          )}
        </p>
      </div>
      {match && (
        <div className="evidence" role="status">
          원문 · {match.title}
          <strong>{match.line}</strong>
        </div>
      )}
      {answer.sources.length > 0 && (
        <ul className="sources">
          {answer.sources.map((s) => (
            <li key={s.rcept_no}>
              <a className="link" href={s.url} target="_blank" rel="noreferrer">
                {s.title.replace(/ \| 접수번호 \d+.*/, "")} · 접수번호 {s.rcept_no} ↗
              </a>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

export default function Board({
  examples,
  initialOpen,
  sample,
}: {
  examples: Example[];
  initialOpen: number;
  sample: Answer;
}) {
  const [rows, setRows] = useState<Example[]>(examples);
  const [open, setOpen] = useState(initialOpen);
  const [state, setState] = useState<Record<string, RowState>>({
    [examples[initialOpen].q]: { steps: [], answer: sample, loading: false },
  });
  const [draft, setDraft] = useState("");
  const openRef = useRef<HTMLDivElement>(null);

  const run = useCallback(async (question: string) => {
    setState((s) => ({ ...s, [question]: { steps: [], loading: true } }));
    try {
      const answer = await ask(question, (label) =>
        setState((s) => ({
          ...s,
          [question]: { ...s[question], steps: [...(s[question]?.steps ?? []), label] },
        })),
      );
      setState((s) => ({ ...s, [question]: { ...s[question], answer, loading: false } }));
    } catch (e) {
      const msg =
        e instanceof TypeError
          ? "데모 서버에 연결하지 못했습니다. 잠시 뒤 다시 시도해 주세요."
          : (e as Error).message;
      setState((s) => ({ ...s, [question]: { ...s[question], error: msg, loading: false } }));
    }
  }, []);

  const choose = (i: number) => {
    setOpen(i);
    const q = rows[i].q;
    if (!state[q]) void run(q);
  };

  const lastOpen = useRef(open);
  useEffect(() => {
    // 열린 행이 실제로 바뀌었을 때만 따라간다(첫 화면을 가리지 않게).
    if (lastOpen.current === open) return;
    lastOpen.current = open;
    openRef.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [open]);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const q = draft.trim();
    if (q.length < 2) return;
    const next = [...rows, { q, company: "직접 질문", kind: "—", route: "질문" }];
    setRows(next);
    setOpen(next.length - 1);
    setDraft("");
    void run(q);
  };

  const current = rows[open];
  const cur = state[current.q];

  return (
    <section className="board" id="ask" aria-label="질문 보드">
      <div className="board-rows">
        <div className="row edge" aria-hidden="true">
          <span className="q">한화오션 2026년 3분기 영업이익은?</span>
          <span className="company">한화오션</span>
          <span className="kind">잠정실적</span>
          <span className="status" data-route="재무">재무</span>
        </div>
        {rows.map((r, i) =>
          i === open ? (
            <div className="open" key={r.q} ref={openRef} aria-live="polite">
              <p className="q">{r.q}</p>
              <ol className="steps" aria-label="진행 단계">
                {(cur?.answer && !cur.steps.length ? ["저장된 답변"] : cur?.steps ?? []).map(
                  (s, k) => (
                    <li key={s + k} className="done">
                      {s}
                    </li>
                  ),
                )}
                {cur?.loading && <li className="now">{cur.steps.length ? "다음 단계 진행 중…" : "질문 분석 중…"}</li>}
              </ol>
              {cur?.answer ? (
                <AnswerBody answer={cur.answer} />
              ) : cur?.error ? (
                <p className="answer">{cur.error}</p>
              ) : (
                <p className="answer">공시를 찾고 숫자를 대조하는 중입니다. 처음 묻는 질문은 10~20초 걸립니다.</p>
              )}
              {cur?.answer && cur.answer.verified.length > 0 && (
                <p className="hint">흰 바탕의 숫자를 누르면 그 숫자가 나온 공시 원문의 줄이 보입니다.</p>
              )}
            </div>
          ) : (
            <button className="row" key={r.q} type="button" onClick={() => choose(i)}>
              <span className="q">{r.q}</span>
              <span className="company">{r.company}</span>
              <span className="kind">{r.kind}</span>
              <span className="status" data-route={r.route}>
                {r.route}
              </span>
            </button>
          ),
        )}
        <form className="ask-row" onSubmit={submit}>
          <label htmlFor="ask-input">직접 질문</label>
          <input
            id="ask-input"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="예: 기아 2026년 결산배당은?"
            maxLength={300}
            autoComplete="off"
          />
          <button className="button" type="submit">
            질문하기
          </button>
        </form>
        <div className="row edge" aria-hidden="true">
          <span className="q">KB금융 2026년 자사주 취득 결정 금액들</span>
          <span className="company">KB금융</span>
          <span className="kind">자기주식 취득</span>
          <span className="status" data-route="공시">공시</span>
        </div>
      </div>
    </section>
  );
}
