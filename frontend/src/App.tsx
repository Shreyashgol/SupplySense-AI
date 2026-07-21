import { RoleProvider } from "./context/RoleContext";
import { Dashboard } from "./pages/Dashboard";

function App() {
  return (
    <RoleProvider>
      <Dashboard />
    </RoleProvider>
  );
}

export default App;
