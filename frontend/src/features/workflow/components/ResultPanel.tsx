import { useMemo, useState } from "react";

import type { AttemptResult } from "../../../types/workflow";

interface ResultPanelProps {
  result: AttemptResult | null;
  isLoading: boolean;
}

function getNumberMetric(source: Record<string, unknown>, key: string) {
  const value = source[key];
  return typeof value === "number" ? value : 0;
}

function getArrayLengthMetric(source: Record<string, unknown>, key: string) {
  const value = source[key];
  return Array.isArray(value) ? value.length : 0;
}

function stringifyPretty(value: unknown) {
  return JSON.stringify(value ?? {}, null, 2);
}

export function ResultPanel({ result, isLoading }: ResultPanelProps) {
  const [copied, setCopied] = useState(false);
  const jsonText = result?.result.json_text ?? "";
  const compileReport = result?.result.compile_report ?? {};
  const verificationReport = result?.result.verification_report ?? {};
  const formattedJson = useMemo(() => {
    if (!jsonText) {
      return "";
    }
    try {
      return JSON.stringify(JSON.parse(jsonText), null, 2);
    } catch {
      return jsonText;
    }
  }, [jsonText]);

  async function copyJson() {
    await navigator.clipboard.writeText(formattedJson || jsonText);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  }

  if (isLoading) {
    return <section className="panel">正在加载结果...</section>;
  }

  if (!result) {
    return <section className="panel empty-panel">暂无结果数据。</section>;
  }

  if (result.status !== "completed") {
    return (
      <section className="panel empty-panel">
        <p className="eyebrow">Result</p>
        <h2>当前状态暂不适合查看最终产物</h2>
        <p>attempt.status={result.status}。结果页会容错展示，但 `json_text` 与验收报告通常在 completed 后才可靠。</p>
      </section>
    );
  }

  return (
    <section className="panel result-panel">
      <div className="panel-heading split">
        <div>
          <p className="eyebrow">Final Artifact</p>
          <h2>JSON 产物与验收报告</h2>
        </div>
        <button className="ghost-button" type="button" onClick={copyJson} disabled={!formattedJson && !jsonText}>
          {copied ? "已复制" : "复制 JSON"}
        </button>
      </div>

      <div className="metric-grid">
        <article>
          <span>页面数</span>
          <strong>{getNumberMetric(compileReport, "page_count")}</strong>
        </article>
        <article>
          <span>子流程数</span>
          <strong>{getNumberMetric(compileReport, "subflow_count")}</strong>
        </article>
        <article>
          <span>节点数</span>
          <strong>{getNumberMetric(compileReport, "node_count")}</strong>
        </article>
        <article>
          <span>body 节点</span>
          <strong>{getNumberMetric(compileReport, "body_node_count")}</strong>
        </article>
        <article>
          <span>跳过节点</span>
          <strong>{getNumberMetric(compileReport, "dropped_node_count")}</strong>
        </article>
        <article>
          <span>缺模板</span>
          <strong>{getNumberMetric(compileReport, "missing_template_count")}</strong>
        </article>
        <article>
          <span>占位符</span>
          <strong>{getNumberMetric(compileReport, "unresolved_placeholder_count")}</strong>
        </article>
        <article>
          <span>body 错误</span>
          <strong>{getArrayLengthMetric(compileReport, "body_expansion_errors")}</strong>
        </article>
        <article>
          <span>验收状态</span>
          <strong>{String(verificationReport.status ?? "unknown")}</strong>
        </article>
      </div>

      <details className="code-panel" open>
        <summary>json_text</summary>
        <pre>{formattedJson || "json_text 为空。"}</pre>
      </details>

      <details className="code-panel">
        <summary>compile_report</summary>
        <pre>{stringifyPretty(compileReport)}</pre>
      </details>

      <details className="code-panel">
        <summary>verification_report</summary>
        <pre>{stringifyPretty(verificationReport)}</pre>
      </details>
    </section>
  );
}
