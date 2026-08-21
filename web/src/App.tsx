import { Layout } from "@/components/layout";
import { CamerasPage } from "@/pages/cameras";
import { DashboardPage } from "@/pages/dashboard";
import { PeoplePage } from "@/pages/people";
import {
  AttendancePage,
  AuditPage,
  BackupsPage,
  DiagnosticsPage,
  HistoryPage,
  ReportsPage,
  SettingsPage,
} from "@/pages/records";

const routes: Record<string, () => React.JSX.Element> = {
  "/": DashboardPage,
  "/camera": CamerasPage,
  "/people": PeoplePage,
  "/attendance": AttendancePage,
  "/history": HistoryPage,
  "/reports": ReportsPage,
  "/backups": BackupsPage,
  "/audit": AuditPage,
  "/system": DiagnosticsPage,
  "/diagnostics": DiagnosticsPage,
  "/settings": SettingsPage,
};

export default function App() {
  const Page = routes[window.location.pathname] ?? DashboardPage;
  return (
    <Layout>
      <Page />
    </Layout>
  );
}
