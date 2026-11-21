/* 프로젝트 소개용 다이어그램 3개 (인라인 SVG). 실제 코드 구조를 그대로 옮겼다.
   - SystemDiagram: app/api, app/agent, app/rag, app/ingest
   - AgentFlow:     app/agent/graph.py build_graph()
   - Erd:           app/models.py */

type BoxProps = {
  x: number;
  y: number;
  w: number;
  h?: number;
  title: string;
  sub?: string;
  kind?: "llm" | "code" | "store" | "ext";
};

function Box({ x, y, w, h = 52, title, sub, kind = "code" }: BoxProps) {
  return (
    <g className={`dg-box dg-${kind}`}>
      <rect x={x} y={y} width={w} height={h} rx={6} />
      <text x={x + w / 2} y={sub ? y + h / 2 - 4 : y + h / 2 + 5} textAnchor="middle" className="dg-title">
        {title}
      </text>
      {sub && (
        <text x={x + w / 2} y={y + h / 2 + 14} textAnchor="middle" className="dg-sub">
          {sub}
        </text>
      )}
    </g>
  );
}

function Edge({ d, label, lx, ly, dashed }: { d: string; label?: string; lx?: number; ly?: number; dashed?: boolean }) {
  return (
    <g className="dg-edge">
      <path d={d} markerEnd="url(#dg-arrow)" strokeDasharray={dashed ? "4 4" : undefined} />
      {label && lx != null && ly != null && (
        <text x={lx} y={ly} className="dg-label" textAnchor="middle">
          {label}
        </text>
      )}
    </g>
  );
}

function Defs() {
  return (
    <defs>
      <marker id="dg-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
        <path d="M0,0 L10,5 L0,10 z" className="dg-arrowhead" />
      </marker>
    </defs>
  );
}

export function SystemDiagram() {
  return (
    <figure className="diagram">
      <div className="dg-scroll">
      <svg viewBox="0 0 900 360" role="img" aria-label="시스템 구성도">
        <Defs />
        <text x={10} y={22} className="dg-group">질문 처리</text>
        <Box x={10} y={40} w={150} title="브라우저" sub="Next.js 채팅" />
        <Box x={230} y={40} w={170} title="FastAPI" sub="/ask · SSE 진행 단계" />
        <Box x={470} y={40} w={180} title="LangGraph 에이전트" sub="분석 → 검색 → 작성 → 검증" kind="llm" />
        <Box x={720} y={40} w={170} title="Claude API" sub="Haiku 5.5 · JSON 출력" kind="ext" />

        <Box x={10} y={150} w={150} title="Langfuse" sub="단계·토큰·비용 추적" kind="ext" />
        <Box x={230} y={150} w={170} title="Redis" sub="답변 캐시 · 호출 제한" kind="store" />
        <Box x={470} y={150} w={180} title="PostgreSQL + pgvector" sub="공시 · 청크 · 재무" kind="store" />
        <Box x={720} y={150} w={170} title="로컬 모델" sub="bge-m3 · bge-reranker" />

        <Edge d="M160,66 L228,66" />
        <Edge d="M400,66 L468,66" />
        <Edge d="M650,66 L718,66" />
        <Edge d="M315,92 L315,148" label="같은 질문이면 캐시" lx={378} ly={125} />
        <Edge d="M560,92 L560,148" label="필터 + 벡터 검색" lx={618} ly={125} />
        <Edge d="M650,82 L760,148" />
        <Edge d="M250,92 L150,148" dashed label="추적" lx={182} ly={116} />

        <line x1={10} y1={238} x2={890} y2={238} className="dg-sep" />
        <text x={10} y={262} className="dg-group">오프라인 수집</text>
        <Box x={10} y={280} w={150} title="DART Open API" sub="공시 목록 · 원문 · 재무" kind="ext" />
        <Box x={230} y={280} w={170} title="수집 · 파싱" sub="XML/HTML → 텍스트·표" />
        <Box x={470} y={280} w={180} title="청킹 · 임베딩" sub="머리말 + 표 행 단위" />
        <Edge d="M160,306 L228,306" />
        <Edge d="M400,306 L468,306" />
        <Edge d="M560,280 L560,204" />
        <Edge d="M315,280 C315,240 470,240 520,204" />
      </svg>
      </div>
      <figcaption>
        <span className="dg-key dg-llm" /> LLM 호출 <span className="dg-key dg-store" /> 저장소 <span className="dg-key dg-ext" /> 외부
        서비스
      </figcaption>
    </figure>
  );
}

export function AgentFlow() {
  return (
    <figure className="diagram">
      <div className="dg-scroll">
      <svg viewBox="0 0 900 290" role="img" aria-label="에이전트 내부 흐름 (LangGraph)">
        <Defs />
        <g className="dg-terminal">
          <rect x={6} y={118} width={56} height={30} rx={15} />
          <text x={34} y={138} textAnchor="middle">질문</text>
        </g>
        <Box x={84} y={108} w={110} title="analyze" sub="질문 분석" kind="llm" />
        <Box x={236} y={18} w={110} title="refuse" sub="범위 밖 · 투자 판단" />
        <Box x={236} y={108} w={110} title="financial" sub="재무 데이터" kind="store" />
        <Box x={388} y={108} w={110} title="retrieve" sub="검색 · 재순위" kind="store" />
        <Box x={540} y={108} w={110} title="generate" sub="답변 작성" kind="llm" />
        <Box x={692} y={108} w={110} title="verify" sub="숫자 대조 (코드)" />
        <Box x={540} y={18} w={110} title="retry_search" sub="검색 조건 완화" />
        <Box x={540} y={210} w={110} title="retry_generate" sub="숫자 피드백" />
        <g className="dg-terminal">
          <rect x={826} y={118} width={68} height={30} rx={15} />
          <text x={860} y={138} textAnchor="middle">답변</text>
        </g>
        <g className="dg-terminal">
          <rect x={388} y={29} width={56} height={30} rx={15} />
          <text x={416} y={49} textAnchor="middle">답변</text>
        </g>

        <Edge d="M62,133 L82,133" />
        <Edge d="M194,120 C214,120 214,44 234,44" label="refuse" lx={200} ly={74} />
        <Edge d="M346,44 L386,44" />
        <Edge d="M194,134 L234,134" label="financial" lx={215} ly={152} />
        <Edge d="M346,134 L386,134" />
        <Edge d="M139,160 L139,186 L443,186 L443,162" label="search" lx={290} ly={180} />
        <Edge d="M498,134 L538,134" />
        <Edge d="M650,134 L690,134" />
        <Edge d="M802,134 L824,134" label="통과" lx={813} ly={154} />
        <Edge d="M747,108 L747,44 L652,44" label="답 못 함 + 풀 조건 남음" lx={822} ly={84} />
        <Edge d="M560,70 C560,94 470,86 470,106" />
        <Edge d="M747,160 L747,236 L652,236" label="근거에 없는 숫자" lx={704} ly={256} />
        <Edge d="M595,210 L595,162" />
      </svg>
      </div>
      <figcaption>
        재시도는 최대 2회. 그래도 확인되지 않은 숫자가 남으면 답변 끝에 경고를 붙입니다.{" "}
        <span className="dg-key dg-llm" /> Claude 호출 <span className="dg-key dg-store" /> DB 조회
      </figcaption>
    </figure>
  );
}

type Col = { name: string; type?: string; key?: "PK" | "FK" | "PK·FK" };

function Table({ x, y, w, name, desc, cols }: { x: number; y: number; w: number; name: string; desc: string; cols: Col[] }) {
  const h = 46 + cols.length * 20 + 6;
  return (
    <g className="dg-table">
      <rect x={x} y={y} width={w} height={h} rx={6} />
      <text x={x + 12} y={y + 20} className="dg-tname">
        {name}
      </text>
      <text x={x + w - 12} y={y + 20} className="dg-tdesc" textAnchor="end">
        {desc}
      </text>
      <line x1={x} y1={y + 32} x2={x + w} y2={y + 32} />
      {cols.map((c, i) => (
        <g key={c.name}>
          <text x={x + 12} y={y + 52 + i * 20} className={c.key ? "dg-col dg-colkey" : "dg-col"}>
            {c.name}
          </text>
          <text x={x + w - 12} y={y + 52 + i * 20} className="dg-ctype" textAnchor="end">
            {c.key ? `${c.key} ` : ""}
            {c.type}
          </text>
        </g>
      ))}
    </g>
  );
}

export function Erd() {
  return (
    <figure className="diagram">
      <div className="dg-scroll">
      <svg viewBox="0 0 900 360" role="img" aria-label="데이터베이스 ERD">
        <Table
          x={10}
          y={120}
          w={190}
          name="companies"
          desc="기업 44"
          cols={[
            { name: "corp_code", type: "text", key: "PK" },
            { name: "stock_code", type: "text" },
            { name: "corp_name", type: "text" },
          ]}
        />
        <Table
          x={250}
          y={10}
          w={200}
          name="filings"
          desc="공시 21,644"
          cols={[
            { name: "rcept_no", type: "접수번호", key: "PK" },
            { name: "corp_code", type: "", key: "FK" },
            { name: "report_nm", type: "공시명" },
            { name: "rcept_dt", type: "date" },
            { name: "category", type: "유형 13종" },
            { name: "is_correction", type: "bool" },
          ]}
        />
        <Table
          x={490}
          y={10}
          w={180}
          name="documents"
          desc="원문 2,075"
          cols={[
            { name: "rcept_no", type: "", key: "PK·FK" },
            { name: "title", type: "text" },
            { name: "text", type: "본문·표" },
          ]}
        />
        <Table
          x={710}
          y={10}
          w={180}
          name="chunks"
          desc="청크 6,128"
          cols={[
            { name: "id", type: "", key: "PK" },
            { name: "rcept_no", type: "", key: "FK" },
            { name: "corp_code · rcept_dt" },
            { name: "category", type: "검색 필터" },
            { name: "text", type: "머리말 포함" },
            { name: "embedding", type: "vector(1024)" },
          ]}
        />
        <Table
          x={250}
          y={210}
          w={220}
          name="structured_events"
          desc="주요사항"
          cols={[
            { name: "rcept_no · api", type: "", key: "PK" },
            { name: "corp_code", type: "", key: "FK" },
            { name: "payload", type: "jsonb" },
          ]}
        />
        <Table
          x={510}
          y={210}
          w={260}
          name="financials"
          desc="재무 14,225"
          cols={[
            { name: "corp_code · 연도 · 보고서", type: "", key: "PK" },
            { name: "연결/별도 · 계정명", type: "", key: "PK" },
            { name: "thstrm_amount", type: "당기 (3개월)" },
            { name: "thstrm_add_amount", type: "누적 (payload)" },
          ]}
        />

        <g className="dg-rel">
          <path d="M200,150 L225,150 L225,60 L248,60" />
          <path d="M200,170 L225,170 L225,262 L248,262" />
          <path d="M225,170 L225,330 L490,330 L490,262 L508,262" />
          <path d="M450,60 L488,60" />
          <path d="M670,60 L708,60" />
        </g>
        <g className="dg-card">
          <text x={206} y={145}>1</text>
          <text x={238} y={55}>N</text>
          <text x={238} y={257}>N</text>
          <text x={497} y={257}>N</text>
          <text x={455} y={55}>1</text>
          <text x={478} y={55}>1</text>
          <text x={675} y={55}>1</text>
          <text x={698} y={55}>N</text>
        </g>
      </svg>
      </div>
      <figcaption>
        chunks는 검색 필터를 위해 회사·날짜·유형을 중복으로 들고 있습니다. 실험용 청크는 chunks_exp에 버전별로 따로
        저장합니다.
      </figcaption>
    </figure>
  );
}
