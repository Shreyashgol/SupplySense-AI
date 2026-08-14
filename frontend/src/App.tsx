import { useState } from "react";
import { RoleProvider } from "./context/RoleContext";
import { Dashboard } from "./pages/Dashboard";
import { LandingPage } from "./pages/LandingPage";

function App() {
  const [showApp, setShowApp] = useState(false);

  if (!showApp) {
    return <LandingPage onLaunch={() => setShowApp(true)} />;
  }

  return (
    <RoleProvider>
      <Dashboard />
    </RoleProvider>
  );
}

export default App;
