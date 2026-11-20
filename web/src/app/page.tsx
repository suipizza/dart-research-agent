import Board, { type Example } from "@/components/Board";
import Reveal from "@/components/Reveal";
import examples from "@/data/examples.json";
import sample from "@/data/sample.json";

const REPO = "https://github.com/suipizza/dart-research-agent";

// 코스피 시가총액 상위 40개 전체 + 기존 4개 (2026-11-18 종가 기준)
const COMPANIES: { kind: string; names: string[] }[] = [
  {
    kind: "반도체·전자",
    names: ["삼성전자", "SK하이닉스", "삼성전기", "삼성SDI", "LG전자", "한미반도체", "삼성에스디에스", "LS ELECTRIC"],
  },
  {
    kind: "금융",
    names: ["KB금융", "신한지주", "하나금융지주", "우리금융지주", "메리츠금융지주", "기업은행", "삼성생명", "삼성화재"],
  },
  {
    kind: "자동차·조선·방산",
    names: ["현대자동차", "기아", "현대모비스", "현대글로비스", "HD현대중공업", "HD한국조선해양", "한화오션", "한화에어로스페이스", "HMM"],
  },
  {
    kind: "바이오·소재·에너지",
    names: ["삼성바이오로직스", "셀트리온", "LG에너지솔루션", "LG화학", "SK이노베이션", "POSCO홀딩스", "고려아연", "두산에너빌리티", "효성중공업", "한국전력공사"],
  },
  {
    kind: "지주·플랫폼·통신",
    names: ["SK", "LG", "SK스퀘어", "삼성물산", "한진칼", "NAVER", "카카오", "SK텔레콤", "KT&G"],
  },
];

const STEPS: [string, string, string][] = [
  ["질문 분석", "회사, 공시일, 공시 유형, 회계 기간을 정한다", "Claude Haiku"],
  ["근거 수집", "조각이 아니라 공시 전체, 이후 정정 공시까지", "pgvector"],
  ["재무 조회", "분기 3개월치와 연초부터의 누적을 구분한다", "재무제표"],
  ["숫자 검증", "답의 숫자를 원문의 숫자와 하나씩 대조한다", "코드"],
  ["재시도", "못 찾으면 조건을 풀고, 틀리면 다시 쓴다", "LangGraph"],
  ["정정 공시", "수집 대상 공시의 20%", "424건"],
  ["자회사 공시", "결정 주체가 제출 회사가 아닌 공시, 26%", "543건"],
  ["나뉜 공시", "원문 2,075건 중 여러 조각으로 잘린 것", "1,608건"],
];

const CREDITS = [
  "여의도 사진: “Yeouido September 2021” lazy fri13th, CC BY 2.0 · “November 2019 Yeouido 02” Willem van Valkenburg, CC BY 2.0 (Wikimedia Commons)",
  "장부 사진: “Account Book Ledger” John Carlin, CC0 · “Pittsboro Merchant Business Ledger”, public domain (Wikimedia Commons) · Kodak Archive Ledger, CC BY 4.0 (Museums Victoria)",
];

export default function Home() {
  return (
    <>
      <main>
        <header className="hero">
          <div className="grid topbar">
            <a className="wordmark" href="#top" id="top">
              DART 리서치
            </a>
            <nav aria-label="페이지 안 이동">
              <a className="link" href="#method">
                검증 방식
              </a>
              <a className="link" href="#result">
                측정 결과
              </a>
            </nav>
            <a className="button" href="#ask">
              질문해 보기
            </a>
          </div>
          <div />
          <div className="grid hero-foot">
            <p className="hero-lede reveal-late">
              코스피 상위 44개 기업의 DART 공시를 근거로 답하고, 답변 속 숫자를 원문 표와 하나씩 대조합니다.
            </p>
            <h1 className="hero-title on-axis">
              <span className="line">
                <span>공시에 묻고,</span>
              </span>
              <span className="line">
                <span>원문으로 답합니다</span>
              </span>
            </h1>
          </div>
        </header>

        <Board examples={examples as Example[]} initialOpen={3} sample={sample} />

        <Reveal as="section" className="grid names" aria-labelledby="names-title">
          <div className="names-head">
            <h2 id="names-title">수집한 회사</h2>
            <p className="meta">코스피 시가총액 상위 40개 전체와 4개 더, 44곳. 2024년 1월 2일부터 2026년 11월 19일까지 공시 21,644건, 원문 2,075건.</p>
          </div>
          <div className="name-cols">
            {COMPANIES.map((g) => (
              <ul key={g.kind}>
                <li className="kind-name">{g.kind}</li>
                {g.names.map((n) => (
                  <li key={n}>{n}</li>
                ))}
              </ul>
            ))}
          </div>
        </Reveal>

        <Reveal as="section" className="figure-page grid" id="result" aria-labelledby="result-title">
          <h2 id="result-title" className="on-axis">
            처음 보는 질문에서
          </h2>
          <div className="left-zone figure-block" style={{ gridColumn: "1 / 9", alignSelf: "end" }}>
            <p className="figure" aria-label="80퍼센트">
              80<sup>%</sup>
            </p>
            <p className="figure-caption">
              개발하는 동안 한 번도 보지 않은 시험용 20문항의 정답률입니다. 같은 문항에서 기본 RAG는 55%였고,
              숫자를 지어낸 답은 15%에서 0%가 됐습니다. 2026년 11월 20일 측정.
            </p>
          </div>
          <p className="figure-source">채점은 Claude Sonnet. 사람이 정한 기준과 15문항을 교차 채점해 모두 일치함을 확인했습니다.</p>
        </Reveal>

        <Reveal className="mosaic" aria-label="여의도와 옛 회계 장부">
          <div>
            <img src="/img/yeouido-september-2021.jpg" alt="한강 건너편으로 보이는 여의도 빌딩숲" width={1600} height={1200} loading="lazy" className="drift" />
          </div>
          <img src="/img/pittsboro-merchant-business-ledger.jpg" alt="1830년대 상점 거래 장부의 숫자 칸" width={1066} height={1600} loading="lazy" />
          <div className="tile-text">
            <p className="big">77%</p>
            <p>원문 대부분은 여러 조각으로 잘립니다. 그래서 조각이 아니라 공시 전체를 읽습니다.</p>
          </div>
          <img src="/img/ledger-kodak-archive-series-4-ledgers-accounts.jpg" alt="1920년대 코닥 지급 장부의 표지" width={1066} height={1600} loading="lazy" />
        </Reveal>

        <Reveal as="section" className="grid method" id="method" aria-labelledby="method-title">
          <h2 id="method-title">숫자는 원문에서만 가져옵니다</h2>
          <div className="method-body">
            <figure className="method-photo">
              <img src="/img/november-2019-yeouido-02.jpg" alt="여의도의 고층 빌딩들" width={1600} height={869} loading="lazy" />
            </figure>
            <p className="table-name">단계</p>
            <table className="steps-table">
              <tbody>
                {STEPS.map(([a, b, c], i) => (
                  <tr key={a} className={i === 5 ? "group" : undefined}>
                    <td>{a}</td>
                    <td>{b}</td>
                    <td>{c}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Reveal>

        <Reveal as="section" className="grid colophon" aria-label="이 프로젝트에 대해">
          <ul className="colophon-facts">
            <li>
              <strong>데이터</strong>DART Open API
            </li>
            <li>
              <strong>모델</strong>Claude Haiku 5.5
            </li>
            <li>
              <strong>코드</strong>
              <a className="link" href={REPO}>
                GitHub
              </a>
            </li>
          </ul>
          <div className="colophon-text">
            <p>
              <img className="dropcap" src="/img/account-book-ledger.jpg" alt="마블 무늬 표지의 옛 회계 장부" width={1200} height={1600} loading="lazy" />
              <strong>DART 리서치는 공시를 손으로 넘기던 일을 대신합니다.</strong>
            </p>
            <p>
              회사와 기간을 먼저 정하고, 해당 공시를 끝까지 읽은 뒤에 답합니다. 원문 2,075건은 표의 행이 끊기지 않게 잘라 bge-m3로 임베딩했고, 답변은 LangGraph 에이전트가 Claude Haiku로
              씁니다. 자회사가 낸 결정인지, 정정된 숫자인지도 함께 따집니다. 같은 질문은 저장된 답으로 0.1초 안에
              돌아오고, 질문은 하루 20번까지 받습니다. 주가 전망과 투자 판단은 하지 않습니다.
            </p>
          </div>
        </Reveal>
      </main>

      <footer className="footer">
        <div className="grid footer-cols">
          <div>
            <p>프로젝트</p>
            <ul>
              <li>
                <a className="link" href={REPO}>
                  GitHub 저장소
                </a>
              </li>
              <li>개인 포트폴리오, 2026</li>
            </ul>
          </div>
          <div>
            <p>데이터</p>
            <ul>
              <li>금융감독원 DART Open API</li>
              <li>2024-01-02 ~ 2026-11-19</li>
            </ul>
          </div>
          <div>
            <p>만든 방식</p>
            <ul>
              <li>LangGraph · Claude API</li>
              <li>FastAPI · PostgreSQL(pgvector) · Redis</li>
              <li>Next.js · Docker · GitHub Actions</li>
            </ul>
          </div>
          <div>
            <p>사진</p>
            <ul>
              {CREDITS.map((c) => (
                <li key={c}>{c}</li>
              ))}
            </ul>
          </div>
        </div>
        <div className="footer-word">
          <svg viewBox="0 0 1000 150" role="img" aria-label="DART 리서치">
            <text x="0" y="128" fontSize="160" textLength="1000" lengthAdjust="spacingAndGlyphs">
              DART 리서치
            </text>
          </svg>
          <p className="legal">공시 원문은 금융감독원 DART와 각 회사의 것입니다. 이 서비스는 투자 권유가 아닙니다.</p>
        </div>
      </footer>
    </>
  );
}
