export type Action = 'idle' | 'nod' | 'wave' | 'smile' | 'confused';
export type Item = { id: string; nickname: string; text: string; status: string; category: string; candidate: string; action: Action; latency: number | null };
export type StudioState = { stopped: boolean; mode: string; epoch: number; player_connected: boolean; items: Item[]; events: { category: string; duration: number; time: number }[]; debug: boolean; metrics: { latency?: number; fps?: number; time: number }[] };
export type Play = { id: string; playback_id: string; text: string; action: Action; audio: string; duration: number; epoch: number };
