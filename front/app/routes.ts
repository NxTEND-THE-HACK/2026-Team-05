import { type RouteConfig, layout, index, route } from "@react-router/dev/routes";

export default [
  layout("components/layout/AppLayout.tsx", [
    index("routes/dashboard.tsx"),
  ]),
  // TEMP_BACKEND_DEMO: 仮画面。削除手順は docs/temporary-backend-demo-ui.md を参照。
  route("backend-demo", "routes/backend-demo.tsx"),
] satisfies RouteConfig;
