import type { Route } from "./+types/devices";

export function meta(_: Route.MetaArgs) {
  return [{ title: "Devices - Remo-Trace" }];
}

export { DevicesPage as default } from "~/pages/DevicesPage";
