import { type RouteConfig, layout, index, route } from "@react-router/dev/routes";

export default [
  layout("components/layout/AppLayout.tsx", [
    index("routes/dashboard.tsx"),
    route("motions", "routes/motions.tsx"),
    route("devices", "routes/devices.tsx"),
    route("devices/:deviceId", "routes/device-detail.tsx"),
    route("bindings", "routes/bindings.tsx"),
    route("logs", "routes/logs.tsx"),
  ]),
] satisfies RouteConfig;
