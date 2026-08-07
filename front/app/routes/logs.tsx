import type { Route } from "./+types/logs";

export function meta(_: Route.MetaArgs) {
  return [{ title: "Logs - Remo-Trace" }];
}

export { LogsPage as default } from "~/pages/LogsPage";
