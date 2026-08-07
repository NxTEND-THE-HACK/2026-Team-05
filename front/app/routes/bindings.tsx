import type { Route } from "./+types/bindings";

export function meta(_: Route.MetaArgs) {
  return [{ title: "Bindings - Remo-Trace" }];
}

export { BindingsPage as default } from "~/pages/BindingsPage";
