import Link from "next/link";

export const REPO = "https://github.com/suipizza/dart-research-agent";

export default function TopBar({ active }: { active: "chat" | "about" }) {
  return (
    <header className="topbar">
      <Link href="/" className="wordmark">
        <span className="wordmark-mark" aria-hidden="true">
          ▍
        </span>
        dart-research
      </Link>
      <nav aria-label="주요 메뉴">
        <Link href="/" aria-current={active === "chat" ? "page" : undefined}>
          질문
        </Link>
        <Link href="/about" aria-current={active === "about" ? "page" : undefined}>
          프로젝트 소개
        </Link>
        <a href={REPO} target="_blank" rel="noreferrer">
          GitHub ↗
        </a>
      </nav>
    </header>
  );
}
