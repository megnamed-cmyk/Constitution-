import { useState, type FormEvent } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { useConstitutionalStream, type Grounding, type Source } from './useConstitutionalStream';

const EXAMPLES = [
  'Can the President suspend habeas corpus during peacetime?',
  'Can Congress require state sheriffs to run federal background checks?',
  'What level of scrutiny applies to a law classifying by national origin?',
];

const GROUNDING_LABEL: Record<Grounding, string> = {
  grounded: 'Grounded in retrieved sources',
  weak: 'Weak retrieval match',
  none: 'Not covered by corpus',
};

const SOURCE_LABEL: Record<Source['source'], string> = {
  constitution: 'Text',
  conan: 'CONAN',
  seed: 'Demo',
};

/** Turn inline citations like [2] into links to the matching source card. */
function linkCitations(md: string, count: number): string {
  return md.replace(/\[(\d{1,2})\](?!\()/g, (m, n) => {
    const i = Number(n);
    return i >= 1 && i <= count ? `[\\[${i}\\]](#src-${i})` : m;
  });
}

function SourceCard({ s, index }: { s: Source; index: number }) {
  const score = s.reranker_score ?? s.rrf_score;
  return (
    <li id={`src-${index}`} className="source">
      <div className="source-head">
        <span className="source-index">[{index}]</span>
        <span className={`tag tag-${s.source}`}>{SOURCE_LABEL[s.source]}</span>
        {score != null && (
          <span className="score" title={s.reranker_score != null ? 'Reranker score' : 'RRF score'}>
            {score.toFixed(3)}
          </span>
        )}
      </div>
      <div className="source-provision">{s.provision}</div>
      <div className="source-subtopic">
        {s.url ? (
          <a href={s.url} target="_blank" rel="noreferrer">
            {s.subtopic}
          </a>
        ) : (
          s.subtopic
        )}
      </div>
      {s.controlling_precedents.length > 0 && (
        <div className="precedents">{s.controlling_precedents.join(' · ')}</div>
      )}
    </li>
  );
}

export function ConstitutionalAnalyzer() {
  const [query, setQuery] = useState('');
  const { text, sources, grounding, status, error, isLoading, submit, abort } = useConstitutionalStream();

  const ask = (q: string) => {
    const trimmed = q.trim();
    if (trimmed.length < 3 || isLoading) return;
    submit({ query: trimmed });
  };
  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    ask(query);
  };

  return (
    <div className="page">
      <header>
        <h1>Constitutional Analysis Engine</h1>
        <p className="muted">
          Hybrid retrieval over the Constitution and the Constitution Annotated, analyzed by Claude.
        </p>
      </header>

      <form onSubmit={onSubmit} className="ask">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Ask a constitutional question…"
          disabled={isLoading}
          aria-label="Constitutional question"
        />
        {isLoading ? (
          <button type="button" onClick={abort} className="btn btn-stop">
            Stop
          </button>
        ) : (
          <button type="submit" className="btn" disabled={query.trim().length < 3}>
            Analyze
          </button>
        )}
      </form>

      {!text && !isLoading && (
        <div className="examples">
          {EXAMPLES.map((ex) => (
            <button key={ex} className="chip" onClick={() => { setQuery(ex); ask(ex); }}>
              {ex}
            </button>
          ))}
        </div>
      )}

      {error && <div className="error" role="alert">{error}</div>}

      <div className="layout">
        <main className="answer" aria-live="polite">
          {grounding && <span className={`grounding grounding-${grounding}`}>{GROUNDING_LABEL[grounding]}</span>}
          {text ? (
            <div className="markdown">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{linkCitations(text, sources.length)}</ReactMarkdown>
              {isLoading && <span className="cursor" />}
            </div>
          ) : (
            <p className="muted placeholder">{status ?? 'Submit a question to see a structured constitutional analysis.'}</p>
          )}
        </main>

        {sources.length > 0 && (
          <aside className="sources">
            <h2>Retrieved sources</h2>
            <ol>
              {sources.map((s, i) => (
                <SourceCard key={s.chunk_id} s={s} index={i + 1} />
              ))}
            </ol>
          </aside>
        )}
      </div>

      <footer className="muted small">
        Educational tool, not legal advice. Verify every citation against the primary source.
      </footer>
    </div>
  );
}
