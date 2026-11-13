
import {useState} from 'react';
import {useMutation} from '@tanstack/react-query';
import {request,type Filters} from './api';

type Finding = {
  title: string;
  explanation: string;
  evidence_ids: string[];
};

type RecommendedAction = {
  action: string;
  rationale: string;
  priority: 'high' | 'medium' | 'low';
  evidence_ids: string[];
  caution: string;
};

type InsightReport = {
  executive_summary: string;
  temporal_analysis: string;
  spatial_analysis: string;
  sensor_analysis: string;
  candidate_tracks_analysis: string;
  year_comparison: string;
  data_quality: string;
  key_findings: Finding[];
  recommended_actions: RecommendedAction[];
  scientific_limitations: string[];
  conclusion: string;
};

type AiResult = {
  model: string;
  scope: Record<string, unknown>;
  report: InsightReport;
  evidence: Record<string, unknown>;
  note: string;
  cached: boolean;
};

type Props = {
  filters: Filters;
};

function Section({
  title,
  children
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="card">
      <h3>{title}</h3>
      {children}
    </section>
  );
}

function Explanation({
  title,
  content
}: {
  title: string;
  content: string;
}) {
  return (
    <Section title={title}>
      <p style={{whiteSpace: 'pre-wrap', lineHeight: 1.8}}>
        {content}
      </p>
    </Section>
  );
}

function Evidence({
  ids,
  facts
}: {
  ids: string[];
  facts: Record<string, unknown>;
}) {
  return (
    <details style={{marginTop: 12}}>
      <summary style={{cursor: 'pointer'}}>
        View supporting evidence ({ids.length})
      </summary>

      {ids.map(id => (
        <div key={id} style={{marginTop: 12}}>
          <strong>{id}</strong>

          <pre style={{
            whiteSpace: 'pre-wrap',
            overflowWrap: 'anywhere',
            fontSize: 12,
            marginTop: 6
          }}>
            {JSON.stringify(facts[id], null, 2)}
          </pre>
        </div>
      ))}
    </details>
  );
}

export default function AiInsights({filters}: Props) {
  const [requestedScope, setRequestedScope] =
    useState<string | null>(null);

  // Used to prevent showing a report for old filters.
  const currentScope = JSON.stringify(filters);

  const mutation = useMutation({
    mutationFn: (selectedFilters: Filters) => {
      const controller = new AbortController();

      return request<AiResult>(
        '/ai/insights',
        controller.signal,
        selectedFilters
      );
    },

    retry: false
  });

  const isCurrentReport = requestedScope === currentScope;

  const result = isCurrentReport
    ? mutation.data
    : undefined;

  const error = isCurrentReport
    ? mutation.error
    : null;

  const generate = () => {
    if (mutation.isPending) return;

    setRequestedScope(currentScope);

    mutation.mutate({...filters});
  };

  const report = result?.report;

  const countryNames: Record<string, string> = {
    AU: 'Australia',
    BR: 'Brazil',
    ID: 'Indonesia',
    ZA: 'South Africa'
  };

  return (
    <div className="ai-insights">

      <Section title="AI-Powered Scientific Insights">
        <p>
          Generate a comprehensive, evidence-based explanation
          of historical NASA FIRMS thermal activity.
        </p>

        <p className="context">
          The AI explains your analytics, identifies patterns,
          and suggests cautious research and monitoring actions.
          It does not independently confirm wildfires.
        </p>

        <div className="metrics">
          <div>
            <span>Country</span>
            <strong>
              {countryNames[filters.country]}
            </strong>
          </div>

          <div>
            <span>Year</span>
            <strong>{filters.year}</strong>
          </div>

          <div>
            <span>Sensor</span>
            <strong>{filters.sensor || 'All sensors'}</strong>
          </div>

          <div>
            <span>Geographic scope</span>
            <strong>
              {filters.region
                ? 'Selected region'
                : filters.polygon
                ? 'Custom polygon'
                : 'Entire country'}
            </strong>
          </div>
        </div>

        {(filters.start || filters.end) && (
          <p className="context">
            Date range: {filters.start || 'Start of year'}
            {' — '}
            {filters.end || 'End of year'}
          </p>
        )}

        <button
          type="button"
          onClick={generate}
          disabled={mutation.isPending}
          style={{marginTop: 16}}
        >
          {mutation.isPending
            ? 'Generating scientific report...'
            : 'Generate AI Insights'}
        </button>

        <p className="context">
          Reports are generated only when requested.
          Year comparisons use full calendar years.
        </p>
      </Section>

      {mutation.isPending && isCurrentReport && (
        <div className="card" role="status">
          <h3>Analyzing historical observations</h3>
          <p>
            Collecting scientific evidence, interpreting
            analytical results, and checking references.
          </p>
          <div className="skeleton" />
        </div>
      )}

      {error && (
        <div className="card error" role="alert">
          <h3>Unable to generate AI Insights</h3>
          <p>{error.message}</p>
        </div>
      )}

      {report && result && (
        <>
          <Section title="Historical Thermal Activity Report">
            <p className="context">
              {countryNames[filters.country]} · {filters.year}
              {' · '}
              {filters.sensor || 'All sensors'}
            </p>

            <p className="context">
              AI model: {result.model}
              {result.cached ? ' · Cached report' : ''}
            </p>

            <p>{result.note}</p>
          </Section>

          <Explanation
            title="1. Executive Summary"
            content={report.executive_summary}
          />

          <Explanation
            title="2. Temporal Analysis"
            content={report.temporal_analysis}
          />

          <Explanation
            title="3. Spatial Analysis"
            content={report.spatial_analysis}
          />

          <Explanation
            title="4. Sensor Comparison"
            content={report.sensor_analysis}
          />

          <Explanation
            title="5. Candidate Tracks Analysis"
            content={report.candidate_tracks_analysis}
          />

          <Explanation
            title="6. Year-over-Year Comparison"
            content={report.year_comparison}
          />

          <Explanation
            title="7. Data Quality and Reliability"
            content={report.data_quality}
          />

          <Section title="8. Key Scientific Findings">
            {report.key_findings.map((finding, index) => (
              <div
                key={index}
                style={{marginBottom: 22}}
              >
                <h4>
                  {index + 1}. {finding.title}
                </h4>

                <p style={{lineHeight: 1.8}}>
                  {finding.explanation}
                </p>

                <Evidence
                  ids={finding.evidence_ids}
                  facts={result.evidence}
                />
              </div>
            ))}
          </Section>

          <Section title="9. Recommended Actions">
            <p className="context">
              These are suggested analytical and research
              actions, not emergency instructions.
            </p>

            {report.recommended_actions.map(
              (action, index) => (
                <div
                  key={index}
                  style={{marginBottom: 24}}
                >
                  <h4>
                    {index + 1}. {action.action}
                  </h4>

                  <p>
                    <strong>Priority:</strong>
                    {' '}
                    {action.priority.toUpperCase()}
                  </p>

                  <p style={{lineHeight: 1.8}}>
                    <strong>Why:</strong>
                    {' '}
                    {action.rationale}
                  </p>

                  <p className="context">
                    <strong>Scientific caution:</strong>
                    {' '}
                    {action.caution}
                  </p>

                  <Evidence
                    ids={action.evidence_ids}
                    facts={result.evidence}
                  />
                </div>
              )
            )}
          </Section>

          <Section title="10. Scientific Limitations">
            <ul>
              {report.scientific_limitations.map(
                (item, index) => (
                  <li
                    key={index}
                    style={{marginBottom: 12}}
                  >
                    {item}
                  </li>
                )
              )}
            </ul>
          </Section>

          <Explanation
            title="11. Final Conclusion"
            content={report.conclusion}
          />

          <Section title="Scientific Disclaimer">
            <p className="context">
              This report is an AI-generated interpretation
              of historical satellite thermal observations.
              It may contain errors or omissions.
            </p>

            <p className="context">
              Candidate tracks are not confirmed wildfires.
              The recommendations require expert review,
              local context, and independent evidence
              before operational use.
            </p>
          </Section>
        </>
      )}
    </div>
  );
}
