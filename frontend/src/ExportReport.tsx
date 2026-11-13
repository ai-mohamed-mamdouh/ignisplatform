
import {useEffect, useRef, useState} from 'react';
import {
  Download,
  FileText,
  CheckCircle2,
  AlertCircle,
  BarChart3,
  BrainCircuit,
  ShieldCheck
} from 'lucide-react';

import type {Filters} from './api';

type Props = {
  filters: Filters;
};

export default function ExportReport({filters}: Props) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);

  const activeRequest = useRef<AbortController | null>(null);

  useEffect(() => {
    return () => {
      activeRequest.current?.abort();
    };
  }, []);

  const countryNames: Record<string, string> = {
    AU: 'Australia',
    BR: 'Brazil',
    ID: 'Indonesia',
    ZA: 'South Africa'
  };

  async function downloadReport() {
    if (activeRequest.current) return;

    const controller = new AbortController();
    activeRequest.current = controller;

    setLoading(true);
    setError('');
    setSuccess(false);

    try {
      const response = await fetch('/api/reports/html', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(filters),
        signal: controller.signal
      });

      if (!response.ok) {
        let message = `Report generation failed (${response.status})`;

        try {
          const result = await response.json();

          if (typeof result.detail === 'string') {
            message = result.detail;
          }
        } catch {
          // Keep the HTTP status message.
        }

        throw new Error(message);
      }

      const htmlBlob = await response.blob();

      if (!htmlBlob.size) {
        throw new Error('The generated HTML report is empty.');
      }

      const url = URL.createObjectURL(htmlBlob);

      const filename =
        `IGNIS_${filters.country}_${filters.year}_Scientific_Report.html`;

      const link = document.createElement('a');

      link.href = url;
      link.download = filename;

      document.body.appendChild(link);
      link.click();
      link.remove();

      // Allow the browser to complete the download first.
      window.setTimeout(() => {
        URL.revokeObjectURL(url);
      }, 10000);

      setSuccess(true);

    } catch (err) {
      if (controller.signal.aborted) return;

      setError(
        err instanceof Error
          ? err.message
          : 'Unable to generate the HTML report.'
      );

    } finally {
      if (activeRequest.current === controller) {
        activeRequest.current = null;
      }

      if (!controller.signal.aborted) {
        setLoading(false);
      }
    }
  }

  return (
    <div className="export-report">

      <section className="card">
        <h3>
          <FileText size={19} style={{
            display: 'inline-block',
            verticalAlign: 'middle',
            marginRight: 9
          }}/>

          Complete Scientific Intelligence Report
        </h3>

        <p>
          Generate a comprehensive standalone HTML report
          containing the analytical results, scientific
          visualizations, AI interpretations, conclusions,
          and evidence-based recommended actions.
        </p>

        <div className="metrics">
          <div>
            <span>Country</span>
            <strong>{countryNames[filters.country]}</strong>
          </div>

          <div>
            <span>Selected Year</span>
            <strong>{filters.year}</strong>
          </div>

          <div>
            <span>Sensor</span>
            <strong>{filters.sensor || 'All sensors'}</strong>
          </div>

          <div>
            <span>Geographic Scope</span>
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
            Selected dates: {filters.start || 'Start of year'}
            {' — '}
            {filters.end || 'End of year'}
          </p>
        )}
      </section>

      <section className="card">
        <h3>What's Included in Your Report?</h3>

        <div style={{
          display: 'grid',
          gap: 18,
          marginTop: 18
        }}>

          <div>
            <BarChart3 size={20} color="#FF914D"/>
            <strong> Complete Analytics</strong>
            <p className="context">
              Overview metrics, daily and monthly trends,
              calendar heatmap, six-year comparison,
              spatial distributions, sensor and FRP analysis,
              and candidate-track statistics.
            </p>
          </div>

          <div>
            <BrainCircuit size={20} color="#2DD4BF"/>
            <strong> AI Scientific Interpretation</strong>
            <p className="context">
              Executive summary, detailed explanations,
              key scientific findings, final conclusions,
              and evidence-based recommended actions.
            </p>
          </div>

          <div>
            <ShieldCheck size={20} color="#79A9F6"/>
            <strong> Scientific Evidence</strong>
            <p className="context">
              Release provenance, data-quality information,
              supporting evidence references, and
              scientific limitations.
            </p>
          </div>

        </div>
      </section>

      <section className="card">
        <h3>Export Settings</h3>

        <p>
          <strong>Format:</strong> Standalone HTML
        </p>

        <p>
          <strong>Charts:</strong> Embedded SVG visualizations
        </p>

        <p>
          <strong>Offline Access:</strong> Supported
        </p>

        <p>
          <strong>Print:</strong> Browser print / Save as PDF
        </p>

        <p className="context">
          Historical comparison charts include the available
          years from 2020 to 2025. Current analytical sections
          respect the selected filters.
        </p>

        <button
          type="button"
          disabled={loading}
          onClick={downloadReport}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 10,
            marginTop: 15,
            padding: '13px 20px',
            fontWeight: 700,
            cursor: loading ? 'wait' : 'pointer'
          }}
        >
          <Download size={18}/>

          {loading
            ? 'Preparing Complete Report...'
            : 'Generate & Download HTML Report'}
        </button>

        <p className="context" style={{marginTop: 14}}>
          The report is generated only when requested.
          A cached AI report may be reused. Otherwise,
          Groq generation may be required.
        </p>
      </section>

      {loading && (
        <section className="card" role="status">
          <h3>Building Your Scientific Report</h3>

          <p>
            Collecting analytics, preparing visualizations,
            and including the AI-generated scientific report.
          </p>

          <div className="skeleton"/>
        </section>
      )}

      {error && (
        <section className="card error" role="alert">
          <AlertCircle size={20}/>

          <h3>Report Export Failed</h3>

          <p>{error}</p>

          <p className="context">
            Please check the error before trying again.
            AI generation may be subject to Groq usage limits.
          </p>
        </section>
      )}

      {success && (
        <section className="card" role="status">
          <CheckCircle2 size={20} color="#2DD4BF"/>

          <h3>Report Ready</h3>

          <p>
            Your HTML report has been sent to the browser
            for download.
          </p>

          <p className="context">
            Open the downloaded file in your browser
            to explore the report or print it.
          </p>
        </section>
      )}

      <section className="card">
        <h3>Scientific Disclaimer</h3>

        <p className="context">
          IGNIS uses historical NASA FIRMS satellite
          thermal observations. Thermal detections and
          algorithmically linked candidate tracks are
          not independently confirmed wildfire events.
        </p>

        <p className="context">
          AI-generated insights and recommendations require
          human scientific review and independent evidence
          before operational decisions are made.
        </p>
      </section>

    </div>
  );
}
