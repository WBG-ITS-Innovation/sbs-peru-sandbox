// Audit row + paginated response shape.

export interface AuditRow {
  id: number;
  created_at: string;
  actor_type: 'user' | 'agent';
  actor_id: string;
  action: string;
  object_type: string;
  object_id: string;
  diff: Record<string, unknown> | null;
  meta: Record<string, unknown> | null;
}

export interface AuditResponse {
  items: AuditRow[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}
