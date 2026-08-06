import type { Route } from "./+types/dashboard";
import { DashboardPage } from "../pages/DashboardPage";

export function meta({}: Route.MetaArgs) {
  return [
    { title: "Smart Home Dashboard" },
    { name: "description", content: "Gesture Smart Home Management Dashboard" },
  ];
}

export default function Dashboard() {
  return <DashboardPage />;
}
