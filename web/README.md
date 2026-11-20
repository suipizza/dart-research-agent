# web — DART 리서치 데모 화면

Next.js(App Router) + TypeScript. 백엔드 `/ask`(SSE)에 질문을 보내고 진행 단계, 답변, 출처, 숫자별 원문 줄을 보여준다.

```bash
npm install
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000 npm run dev   # http://localhost:3000
```

- `src/components/Board.tsx`: 질문 보드(예시 질문 행 + 직접 질문). 행을 누르면 열리며 답변을 스트리밍으로 받는다.
- `src/data/examples.json`: 예시 질문. 서버 캐시에 미리 넣어 두면 누를 때 바로 뜨고 API 비용이 들지 않는다.
- `src/data/sample.json`: 기본으로 열린 행의 실제 답변. 스크립트나 API 없이도 보이는 대체 자료.
- 사진 출처: `public/img/credits.json`, 페이지 푸터에 표기.
