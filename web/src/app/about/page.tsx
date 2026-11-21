import type { Metadata } from "next";
import Link from "next/link";
import { AgentFlow, Erd, SystemDiagram } from "@/components/Diagrams";
import TopBar, { REPO } from "@/components/TopBar";

export const metadata: Metadata = {
  title: "프로젝트 소개 · DART 공시 리서치",
  description: "DART 공시 RAG 에이전트의 동작 방식, 해결한 문제, 실험 결과.",
};

const FLOW: [string, string][] = [
  ["질문 분석", "회사, 공시 날짜, 공시 종류, 회계 기간을 뽑습니다."],
  ["공시 검색", "그 조건으로 좁혀 벡터 검색하고, 재순위 모델로 다시 정렬합니다."],
  ["답변 작성", "고른 공시 전체를 읽고 출처와 함께 답합니다."],
  ["숫자 검증", "답변의 숫자가 원문에 있는지 코드로 대조합니다."],
];

const PROBLEMS: [string, string][] = [
  [
    "제출한 회사와 결정한 회사가 다르다",
    "공시의 26%는 자회사의 결정을 모회사가 대신 낸 것입니다. 이런 공시를 따로 구분해 뒤로 미루고, 답변에 실제 결정한 회사를 밝히게 했습니다.",
  ],
  [
    "숫자가 나중에 바뀐다",
    "공시의 20%는 정정 공시가 따라옵니다. 원래 공시 뒤 150일 안의 정정 공시를 함께 가져와 바뀐 숫자로 답합니다.",
  ],
  [
    "분기 실적과 누적 실적이 섞인다",
    "재무 데이터의 같은 칸이 보고서에 따라 3개월치이기도 하고 연초부터의 누적이기도 합니다. 질문한 기간에 맞는 값을 고르고, 4분기는 연간에서 3분기 누적을 빼서 구합니다.",
  ],
  [
    "공시 하나가 여러 조각으로 잘린다",
    "원문의 77%가 여러 조각으로 나뉘어 있어, 조각 하나만 보고 답하면 필요한 숫자를 놓쳤습니다. 검색은 조각 단위로 하고, 답변을 쓸 때는 찾은 공시를 처음부터 끝까지 넣었습니다.",
  ],
];

const RETRIEVAL: { name: string; h1: string; h5: string; time: string; mark?: "base" | "bad" }[] = [
  { name: "머리말 없음", h1: "0.47", h5: "0.62", time: "0.1초", mark: "bad" },
  { name: "머리말 있음", h1: "0.62", h5: "0.89", time: "0.1초" },
  { name: "+ 잘린 표에 열 이름 반복", h1: "0.64", h5: "0.91", time: "0.1초" },
  { name: "+ 재순위 모델 (사용 중)", h1: "0.70", h5: "0.87", time: "27초", mark: "base" },
];

const STACK = [
  "LangGraph",
  "Claude Haiku 5.5",
  "bge-m3",
  "bge-reranker-v2-m3",
  "PostgreSQL · pgvector",
  "FastAPI",
  "Redis",
  "Langfuse",
  "Next.js",
  "Docker",
  "GitHub Actions",
];

const COMPANIES = [
  "삼성전자", "SK하이닉스", "삼성전기", "삼성SDI", "LG전자", "한미반도체", "삼성에스디에스", "LS ELECTRIC",
  "KB금융", "신한지주", "하나금융지주", "우리금융지주", "메리츠금융지주", "기업은행", "삼성생명", "삼성화재",
  "현대자동차", "기아", "현대모비스", "현대글로비스", "HD현대중공업", "HD한국조선해양", "한화오션", "한화에어로스페이스", "HMM",
  "삼성바이오로직스", "셀트리온", "LG에너지솔루션", "LG화학", "SK이노베이션", "POSCO홀딩스", "고려아연", "두산에너빌리티", "효성중공업", "한국전력공사",
  "SK", "LG", "SK스퀘어", "삼성물산", "한진칼", "NAVER", "카카오", "SK텔레콤", "KT&G",
];

export default function About() {
  return (
    <>
      <TopBar active="about" />
      <main className="doc">
        <header className="doc-head">
          <h1>DART 공시 리서치 에이전트</h1>
          <p>
            상장사 공시를 근거로 질문에 답하는 RAG 에이전트입니다. 답변에 나온 숫자는 공시 원문과 맞는지 코드로 한 번 더
            확인합니다.
          </p>
          <div className="doc-links">
            <Link className="btn primary" href="/">
              질문해 보기
            </Link>
            <a className="btn" href={REPO} target="_blank" rel="noreferrer">
              GitHub
            </a>
          </div>
        </header>

        <section>
          <h2>결과</h2>
          <div className="result">
            <div>
              <div className="result-label">정답률</div>
              <div className="result-value">
                55% <span>→</span> <b>80%</b>
              </div>
            </div>
            <div>
              <div className="result-label">원문에 없는 숫자를 쓴 답변</div>
              <div className="result-value">
                15% <span>→</span> <b>0%</b>
              </div>
            </div>
          </div>
          <p>
            검색된 문서를 그대로 넣어 답하는 기본 RAG와 비교한 결과입니다. 평가에는 개발할 때 쓰지 않은 질문 20개를 썼고,
            정답은 DART 원문을 보고 직접 확인했습니다.
          </p>
        </section>

        <section>
          <h2>시스템 구성</h2>
          <p>
            질문은 FastAPI를 거쳐 LangGraph 에이전트가 처리하고, 공시 데이터는 DART에서 따로 수집해 Postgres에 쌓습니다.
            임베딩과 재순위 모델은 서버에서 직접 돌리고, 외부로 나가는 호출은 Claude API뿐입니다.
          </p>
          <SystemDiagram />
        </section>

        <section>
          <h2>동작 방식</h2>
          <ol className="flow">
            {FLOW.map(([name, desc]) => (
              <li key={name}>
                <strong>{name}</strong>
                <span>{desc}</span>
              </li>
            ))}
          </ol>
          <p>
            실제 LangGraph 그래프는 아래와 같습니다. 검증에서 근거에 없는 숫자가 나오면 답변을 다시 쓰고, 공시를 못 찾으면
            조건을 풀어 다시 검색합니다. 투자 판단을 묻는 질문은 바로 거절합니다.
          </p>
          <AgentFlow />
        </section>

        <section>
          <h2>해결한 문제</h2>
          <p>공시 데이터에는 단순 검색으로는 틀리기 쉬운 구조가 있었습니다.</p>
          <dl className="problems">
            {PROBLEMS.map(([title, desc]) => (
              <div key={title}>
                <dt>{title}</dt>
                <dd>{desc}</dd>
              </div>
            ))}
          </dl>
        </section>

        <section>
          <h2>검색 실험</h2>
          <p>청크 구성과 재순위가 검색에 얼마나 영향을 주는지 질문 53개로 비교했습니다.</p>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>설정</th>
                  <th>1위 정답</th>
                  <th>5위 안 정답</th>
                  <th>질문당 시간</th>
                </tr>
              </thead>
              <tbody>
                {RETRIEVAL.map((r) => (
                  <tr key={r.name} className={r.mark}>
                    <td>{r.name}</td>
                    <td className="n">{r.h1}</td>
                    <td className="n">{r.h5}</td>
                    <td className="n">{r.time}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p>
            청크 앞에 회사·날짜·공시명을 붙이는 머리말이 가장 효과가 컸습니다. 여기에 잘린 표에 열 이름을 다시 붙이고,
            재순위 모델로 후보를 다시 정렬해 1위 정답을 0.70까지 올렸습니다. 실험에서는 재순위로 질문당 27초가 늘었지만,
            실제 에이전트는 회사와 날짜로 후보를 먼저 좁혀 응답 시간이 거의 늘지 않았습니다. 목록 질문은 빠짐없이 모으는 게
            중요해서 재순위 없이 후보를 더 넓게 봅니다.
          </p>
        </section>

        <section>
          <h2>데이터와 기술</h2>
          <dl className="facts">
            <div>
              <dt>범위</dt>
              <dd>코스피 시가총액 상위 44개 기업, 2024년 1월부터의 공시 21,644건 (원문 2,075건)</dd>
            </div>
            <div>
              <dt>평가</dt>
              <dd>직접 만든 질문 73개 (개발용 53 + 최종 확인용 20). 코드 채점과 Claude Sonnet 채점</dd>
            </div>
            <div>
              <dt>기술</dt>
              <dd>{STACK.join(", ")}</dd>
            </div>
          </dl>
          <Erd />
          <details className="companies">
            <summary>수집 기업 44개 보기</summary>
            <p>{COMPANIES.join(", ")}</p>
          </details>
        </section>

        <footer className="doc-foot">데이터 출처: 금융감독원 DART Open API. 투자 권유가 아닙니다.</footer>
      </main>
    </>
  );
}
