import type { Metadata } from "next";
import { Literata, Noto_Serif_KR } from "next/font/google";
import "./globals.css";

// Literata: 라틴 문자와 숫자(표의 금액). 한글 글자가 없어 같은 명조 계열 Noto Serif KR로 받친다.
const literata = Literata({
  variable: "--font-latin",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  display: "swap",
});

const notoSerifKr = Noto_Serif_KR({
  variable: "--font-hangul",
  weight: ["400", "500", "600"],
  preload: false,
  display: "swap",
});

export const metadata: Metadata = {
  title: "DART 리서치 — 공시에 묻고, 원문으로 답합니다",
  description:
    "코스피 시가총액 상위 44개 기업의 DART 공시를 근거로 답하고, 답변의 숫자를 원문 표와 대조하는 LangGraph 에이전트.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="ko" className={`${literata.variable} ${notoSerifKr.variable}`}>
      <body>{children}</body>
    </html>
  );
}
