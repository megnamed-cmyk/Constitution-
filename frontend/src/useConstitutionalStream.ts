import { useCallback, useRef, useState } from 'react';

export type Grounding = 'grounded' | 'weak' | 'none';

export interface Source {
  chunk_id: string;
  source: 'constitution' | 'conan' | 'seed';
  provision: string;
  subtopic: string;
  title: string;
  url: string;
  clause_path: string;
  controlling_precedents: string[];
  rrf_score: number | null;
  reranker_score: number | null;
}

export interface AnalysisRequest {
  query: string;
  candidate_pool_size?: number;
  top_k_final?: number;
}

interface SseEvent {
  event: string;
  data: string;
}

/** Split a buffer into complete SSE events; returns the events and the unconsumed remainder. */
export function parseSseBuffer(buffer: string): { events: SseEvent[]; rest: string } {
  const normalized = buffer.replace(/\r\n/g, '\n');
  const blocks = normalized.split('\n\n');
  const rest = blocks.pop() ?? '';
  const events: SseEvent[] = [];
  for (const block of blocks) {
    let event = 'message';
    const data: string[] = [];
    for (const line of block.split('\n')) {
      if (line.startsWith('event:')) event = line.slice(6).trim();
      else if (line.startsWith('data:')) data.push(line.slice(5).replace(/^ /, ''));
    }
    if (data.length) events.push({ event, data: data.join('\n') });
  }
  return { events, rest };
}

export function useConstitutionalStream(endpointUrl = '/api/analyze/stream') {
  const [text, setText] = useState('');
  const [sources, setSources] = useState<Source[]>([]);
  const [grounding, setGrounding] = useState<Grounding | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const controllerRef = useRef<AbortController | null>(null);

  const abort = useCallback(() => {
    controllerRef.current?.abort();
    controllerRef.current = null;
    setIsLoading(false);
    setStatus(null);
  }, []);

  const submit = useCallback(
    async (req: AnalysisRequest) => {
      controllerRef.current?.abort();
      const controller = new AbortController();
      controllerRef.current = controller;

      setText('');
      setSources([]);
      setGrounding(null);
      setError(null);
      setStatus('Connecting…');
      setIsLoading(true);

      try {
        const res = await fetch(endpointUrl, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
          body: JSON.stringify({
            query: req.query,
            candidate_pool_size: req.candidate_pool_size ?? 15,
            top_k_final: req.top_k_final ?? 4,
          }),
          signal: controller.signal,
        });
        if (!res.ok) {
          const detail = res.status === 422 ? 'Question must be 3–1000 characters.' : res.statusText;
          throw new Error(`Server returned ${res.status}: ${detail}`);
        }
        if (!res.body) throw new Error('Streaming not supported by this browser.');

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        for (;;) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const { events, rest } = parseSseBuffer(buffer);
          buffer = rest;
          for (const { event, data } of events) {
            const payload = JSON.parse(data);
            switch (event) {
              case 'status':
                setStatus(payload.message);
                break;
              case 'sources':
                setSources(payload.sources);
                setGrounding(payload.grounding);
                break;
              case 'delta':
                setStatus(null);
                setText((prev) => prev + payload.text);
                break;
              case 'refusal':
              case 'error':
                setError(payload.message);
                return;
              case 'done':
                return;
            }
          }
        }
      } catch (err) {
        if (err instanceof DOMException && err.name === 'AbortError') return;
        setError(err instanceof Error ? err.message : 'Something went wrong.');
      } finally {
        if (controllerRef.current === controller) {
          controllerRef.current = null;
          setIsLoading(false);
          setStatus(null);
        }
      }
    },
    [endpointUrl],
  );

  return { text, sources, grounding, status, error, isLoading, submit, abort };
}
