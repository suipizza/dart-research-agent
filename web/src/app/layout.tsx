import type { Metadata } from "next";
import { IBM_Plex_Mono, IBM_Plex_Sans_KR } from "next/font/google";
import "./globals.css";

// 본문: IBM Plex Sans KR. 숫자·로그·코드: IBM Plex Mono (자릿수가 고르게 정렬된다).
const sans = IBM_Plex_Sans_KR({
  variable: "--font-sans",
  weight: ["400", "500", "600"],
  preload: false,
  display: "swap",
});

const mono = IBM_Plex_Mono({
  variable: "--font-mono",
  subsets: ["latin"],
  weight: ["400", "500"],
  display: "swap",
});

export const metadata: Metadata = {
  title: "DART 공시 리서치",
  description:
    "코스피 상위 44개 기업의 DART 공시를 근거로 답하고, 답변의 숫자를 공시 원문과 대조하는 LangGraph RAG 에이전트.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="ko" className={`${sans.variable} ${mono.variable}`}>
      <body>{children}</body>
    </html>
  );
}
