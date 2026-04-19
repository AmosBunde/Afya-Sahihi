import { Header } from "./components/Layout/Header";
import { OfflineBanner } from "./components/Layout/OfflineBanner";
import { ChatPage } from "./components/Chat/ChatPage";

export default function App() {
  return (
    <div className="flex h-screen flex-col">
      <OfflineBanner />
      <Header />
      <main className="flex-1 overflow-hidden">
        <ChatPage />
      </main>
    </div>
  );
}
