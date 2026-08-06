import { type RouteConfig, layout, index } from "@react-router/dev/routes";

export default [
  layout("components/layout/AppLayout.tsx", [
    index("routes/dashboard.tsx"),
  ]),
] satisfies RouteConfig;
