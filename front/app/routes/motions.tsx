import type { Route } from "./+types/motions";

export function meta(_: Route.MetaArgs) {
  return [{ title: "Motions - Remo-Trace" }];
}

export { MotionsPage as default } from "~/pages/MotionsPage";
