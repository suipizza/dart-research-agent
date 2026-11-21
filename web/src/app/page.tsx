import Chat, { type Example } from "@/components/Chat";
import TopBar from "@/components/TopBar";
import examples from "@/data/examples.json";

export default function Home() {
  return (
    <main className="chat">
      <TopBar active="chat" />
      <Chat examples={examples as Example[]} companyCount={44} />
      <footer className="statusbar">
        <span>
          <span className="dot" />
          claude-haiku-5-5
        </span>
        <span>bge-m3 · pgvector</span>
        <span className="hide-sm">IP당 하루 20회</span>
        <span className="hide-sm">투자 판단·주가 전망은 답하지 않음</span>
      </footer>
    </main>
  );
}
