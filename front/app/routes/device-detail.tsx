import type { Route } from "./+types/device-detail";

export function meta(_: Route.MetaArgs) {
  return [{ title: "Device Detail - Remo-Trace" }];
}

export { DeviceDetailPage as default } from "~/pages/DeviceDetailPage";
