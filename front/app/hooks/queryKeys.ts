export const queryKeys = {
  health: ["health"] as const,
  cameras: ["cameras"] as const,
  motions: ["motions"] as const,
  appliances: ["appliances"] as const,
  applianceState: (applianceId: string) => ["appliances", applianceId, "state"] as const,
  irHealth: (applianceId: string) => ["appliances", applianceId, "ir", "health"] as const,
  actions: (applianceId?: string) => ["actions", applianceId ?? "*"] as const,
  bindings: ["bindings"] as const,
  logs: (limit?: number) => ["logs", limit ?? 100] as const,
};
