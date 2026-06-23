import { useMemo, useState } from "react";
import {
  AlertTriangle,
  CheckCircle2,
  ClipboardList,
  Copy,
  Download,
  FileSearch,
  FileText,
  Printer,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ChatAnswer, Kpi, Opportunity, RetrievedContext, SourceCard } from "../api";

type InvestorReportModel = {
  title: string;
  fileStem: string;
  markdown: string;
  html: string;
  summaryShort: string;
  question: string;
  generatedAt: string;
  projectLabel: string;
  scoreLabel: string;
  riskLabel: string;
  engineLabel: string;
  kpis: Kpi[];
  alternatives: Opportunity[];
  sources: SourceCard[];
  evidence: RetrievedContext[];
  dueDiligence: string[];
};

function stripMarkdown(value: string) {
  return value
    .replace(/```[\s\S]*?```/g, "")
    .replace(/[#*_>`|]/g, "")
    .replace(/\[(.*?)\]\(.*?\)/g, "$1")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function escapeHtml(value: string) {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function slugify(value: string) {
  return (
    value
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "")
      .slice(0, 80) || "rapport"
  );
}

function downloadHref(content: string, type: string) {
  return `data:${type};charset=utf-8,${encodeURIComponent(content)}`;
}

function pdfText(value: string | number | undefined) {
  return String(value ?? "")
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[’‘]/g, "'")
    .replace(/[“”]/g, '"')
    .replace(/[–—]/g, "-")
    .replace(/…/g, "...")
    .replace(/•/g, "-")
    .replace(/[^\x20-\x7E]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function pdfEscape(value: string) {
  return pdfText(value).replace(/\\/g, "\\\\").replace(/\(/g, "\\(").replace(/\)/g, "\\)");
}

function wrapPdfLine(text: string, maxChars: number) {
  const clean = pdfText(text);
  if (!clean) return [""];
  const words = clean.split(" ");
  const lines: string[] = [];
  let current = "";
  for (const word of words) {
    const candidate = current ? `${current} ${word}` : word;
    if (candidate.length > maxChars && current) {
      lines.push(current);
      current = word;
    } else {
      current = candidate;
    }
  }
  if (current) lines.push(current);
  return lines;
}

function buildPdfContent(report: InvestorReportModel) {
  type PdfRow = { text: string; size?: number; bold?: boolean; gap?: number };
  const rows: PdfRow[] = [
    { text: "Invest Search", size: 11, bold: true },
    { text: report.title, size: 19, bold: true, gap: 8 },
    { text: `Date: ${report.generatedAt}` },
    { text: `Question: ${report.question}` },
    { text: `Zone: ${report.projectLabel} - ${report.scoreLabel} - risque ${report.riskLabel}` },
    { text: `Moteur: ${report.engineLabel}` },
    { text: "Synthese executive", size: 14, bold: true, gap: 18 },
    ...wrapPdfLine(report.summaryShort, 88).map((text) => ({ text })),
    { text: "KPIs decisionnels", size: 14, bold: true, gap: 18 },
    ...report.kpis.map((item) => ({ text: `${item.label}: ${item.value}` })),
    { text: "Alternatives a comparer", size: 14, bold: true, gap: 18 },
    ...(report.alternatives.length
      ? report.alternatives.flatMap((item) =>
          wrapPdfLine(`${item.zone} - ${scoreLabel(item.score)} - ${item.category}`, 88).map((text) => ({
            text: `- ${text}`,
          })),
        )
      : [{ text: "- Aucune alternative structuree dans la derniere reponse." }]),
    { text: "Checklist due diligence", size: 14, bold: true, gap: 18 },
    ...report.dueDiligence.flatMap((item) => wrapPdfLine(item, 86).map((text) => ({ text: `- ${text}` }))),
    { text: "Sources", size: 14, bold: true, gap: 18 },
    ...(report.sources.length
      ? report.sources.flatMap((source) =>
          wrapPdfLine(`${source.title} - ${source.metric || source.subtitle || source.description || "source"}`, 86)
            .map((text) => ({ text: `- ${text}` })),
        )
      : [{ text: "- Sources non disponibles." }]),
    { text: "Limites", size: 14, bold: true, gap: 18 },
    ...wrapPdfLine(
      "Ce rapport est une aide a la preselection. Il ne remplace pas une visite terrain, une due diligence financiere, juridique et reglementaire, ni une validation commerciale.",
      88,
    ).map((text) => ({ text })),
  ];

  const pageWidth = 595.28;
  const pageHeight = 841.89;
  const marginX = 48;
  const marginTop = 56;
  const marginBottom = 52;
  const pages: string[][] = [[]];
  let y = pageHeight - marginTop;

  function addPage() {
    pages.push([]);
    y = pageHeight - marginTop;
  }

  function addText(row: PdfRow) {
    const size = row.size ?? 10.5;
    const lineHeight = size + 5;
    y -= row.gap ?? 0;
    const maxChars = Math.max(42, Math.floor((pageWidth - marginX * 2) / (size * 0.47)));
    const lines = row.size && row.size >= 14 ? wrapPdfLine(row.text, Math.min(maxChars, 72)) : wrapPdfLine(row.text, maxChars);
    for (const line of lines) {
      if (y < marginBottom) addPage();
      const font = row.bold ? "F2" : "F1";
      pages[pages.length - 1].push(`BT /${font} ${size} Tf ${marginX} ${y.toFixed(2)} Td (${pdfEscape(line)}) Tj ET`);
      y -= lineHeight;
    }
  }

  rows.forEach(addText);

  const objects: string[] = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "",
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
  ];
  const pageRefs: number[] = [];
  const pageContentStart = 5;
  pages.forEach((commands, index) => {
    const contentObj = pageContentStart + index * 2;
    const pageObj = contentObj + 1;
    pageRefs.push(pageObj);
    const content = commands.join("\n");
    objects.push(`<< /Length ${content.length} >>\nstream\n${content}\nendstream`);
    objects.push(
      `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 ${pageWidth} ${pageHeight}] /Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents ${contentObj} 0 R >>`,
    );
  });
  objects[1] = `<< /Type /Pages /Kids [${pageRefs.map((ref) => `${ref} 0 R`).join(" ")}] /Count ${pageRefs.length} >>`;

  let pdf = "%PDF-1.4\n";
  const offsets = [0];
  objects.forEach((object, index) => {
    offsets.push(pdf.length);
    pdf += `${index + 1} 0 obj\n${object}\nendobj\n`;
  });
  const xrefOffset = pdf.length;
  pdf += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n`;
  for (let i = 1; i <= objects.length; i += 1) {
    pdf += `${String(offsets[i]).padStart(10, "0")} 00000 n \n`;
  }
  pdf += `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xrefOffset}\n%%EOF`;
  return pdf;
}

function scoreLabel(value?: number) {
  return typeof value === "number" && Number.isFinite(value) && value > 0
    ? `${Number(value).toFixed(1).replace(".0", "")}/100`
    : "Non calcule";
}

function engineLabel(answer: ChatAnswer) {
  const status = answer.rag_status || "";
  if (status.includes("ollama") || status === "llm_rag" || answer.retrieved_contexts?.length) {
    return "RAG local + scoring";
  }
  if (status.includes("api_")) return "RAG API + scoring";
  if (status.startsWith("easy_")) return "Moteur rapide";
  return "Scoring + recherche semantique";
}

function buildInvestorReport(answer: ChatAnswer): InvestorReportModel {
  const topOpportunity =
    answer.related_opportunities.find((item) => item.zone === answer.top_zone) ||
    answer.related_opportunities[0];
  const projectLabel =
    answer.subcategory_label ||
    topOpportunity?.category ||
    answer.category ||
    answer.sector ||
    "Projet d'implantation";
  const question = answer.question || answer.query || "Analyse Invest Search";
  const generatedAt = new Date().toLocaleString("fr");
  const title = `Rapport investisseur - ${projectLabel} - ${answer.top_zone || "Casablanca"}`;
  const score = topOpportunity?.score ?? answer.score;
  const risk = topOpportunity?.risk ?? answer.risk;
  const kpis = answer.kpis?.length
    ? answer.kpis
    : [
        { label: "Zone", value: answer.top_zone || "Casablanca" },
        { label: "Score", value: scoreLabel(score) },
        { label: "Risque", value: scoreLabel(risk) },
        { label: "Moteur", value: engineLabel(answer) },
      ];
  const alternatives = (answer.related_opportunities || [])
    .filter((item) => item.zone !== answer.top_zone)
    .slice(0, 5);
  const sources = (answer.sources || []).slice(0, 6);
  const evidence = (answer.retrieved_contexts || []).slice(0, 4);
  const summary = stripMarkdown(answer.answer_markdown || "Aucune analyse n'a encore ete generee.");
  const summaryShort = summary.length > 1200 ? `${summary.slice(0, 1200)}...` : summary;
  const dueDiligence = [
    "Verifier les loyers, le bail, la visibilite et les flux pietons sur site.",
    "Confirmer la concurrence non cartographiee et les acteurs informels autour de la zone.",
    "Controler les autorisations, normes, licences et contraintes operationnelles du secteur.",
    "Comparer au moins deux zones alternatives avant decision finale.",
    "Mettre a jour les donnees OSM/HCP/MSPS avant une presentation investisseur definitive.",
  ];
  const reportEngine = engineLabel(answer);
  const reportScore = scoreLabel(score);
  const reportRisk = scoreLabel(risk);
  const markdown = [
    `# ${title}`,
    "",
    `**Date de generation :** ${generatedAt}`,
    `**Question initiale :** ${question}`,
    `**Zone prioritaire :** ${answer.top_zone || "Casablanca"}`,
    `**Type / secteur :** ${projectLabel}`,
    `**Score :** ${reportScore}`,
    `**Risque :** ${reportRisk}`,
    `**Moteur :** ${reportEngine}`,
    "",
    "## Synthese executive",
    "",
    summaryShort,
    "",
    "## KPIs decisionnels",
    "",
    "| Indicateur | Valeur |",
    "|---|---:|",
    ...kpis.map((item) => `| ${item.label} | ${item.value} |`),
    "",
    "## Alternatives a comparer",
    "",
    alternatives.length
      ? alternatives.map((item) => `- **${item.zone}** - ${scoreLabel(item.score)} (${item.category})`).join("\n")
      : "- Aucune alternative structuree dans la derniere reponse.",
    "",
    "## Checklist due diligence",
    "",
    ...dueDiligence.map((item) => `- [ ] ${item}`),
    "",
    "## Sources et traces RAG",
    "",
    sources.length
      ? sources.map((source) => `- **${source.title}** - ${source.metric || source.subtitle || source.description || "source"}`).join("\n")
      : "- Sources non disponibles.",
    evidence.length ? "\n### Passages recuperes\n" : "",
    ...evidence.map((context) => `- **${context.title}** (${Math.round((context.score || 0) * 100)}%) - ${context.source_path}`),
    "",
    "## Limites",
    "",
    "Ce rapport est une aide a la preselection. Il ne remplace pas une visite terrain, une due diligence financiere, juridique et reglementaire, ni une validation commerciale.",
  ].join("\n");

  const htmlRows = kpis
    .map((item) => `<tr><th>${escapeHtml(item.label)}</th><td>${escapeHtml(item.value)}</td></tr>`)
    .join("");
  const alternativesHtml = alternatives.length
    ? alternatives
        .map((item) => `<li><strong>${escapeHtml(item.zone)}</strong> - ${escapeHtml(scoreLabel(item.score))} (${escapeHtml(item.category)})</li>`)
        .join("")
    : "<li>Aucune alternative structuree dans la derniere reponse.</li>";
  const sourceHtml = sources.length
    ? sources
        .map((source) => `<li><strong>${escapeHtml(source.title)}</strong> - ${escapeHtml(source.metric || source.subtitle || source.description || "source")}</li>`)
        .join("")
    : "<li>Sources non disponibles.</li>";
  const evidenceHtml = evidence.length
    ? `<h2>Traces RAG</h2><ul>${evidence
        .map((context) => `<li><strong>${escapeHtml(context.title)}</strong> - ${Math.round((context.score || 0) * 100)}% - ${escapeHtml(context.source_path)}</li>`)
        .join("")}</ul>`
    : "";
  const html = `<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8" />
  <title>${escapeHtml(title)}</title>
  <style>
    body { margin: 0; padding: 36px; font-family: Inter, Arial, sans-serif; color: #0f172a; background: #f8fafc; }
    main { max-width: 920px; margin: 0 auto; background: #fff; padding: 42px; border: 1px solid #dbe3ef; border-radius: 18px; }
    h1 { margin: 0 0 8px; font-size: 30px; }
    h2 { margin-top: 30px; color: #047857; font-size: 18px; }
    .meta { color: #64748b; font-size: 13px; line-height: 1.7; }
    .decision { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; margin: 24px 0; }
    .decision div { border: 1px solid #dbe3ef; border-radius: 12px; padding: 14px; background: #f8fafc; }
    .decision span { display: block; color: #64748b; font-size: 11px; font-weight: 700; text-transform: uppercase; }
    .decision strong { display: block; margin-top: 6px; font-size: 16px; }
    table { width: 100%; border-collapse: collapse; margin-top: 12px; }
    th, td { border-bottom: 1px solid #e2e8f0; padding: 10px; text-align: left; }
    th { width: 36%; color: #475569; }
    li { margin: 8px 0; }
    .summary { white-space: pre-wrap; line-height: 1.65; }
    @media print { body { background: #fff; padding: 0; } main { border: 0; border-radius: 0; } }
  </style>
</head>
<body>
  <main>
    <h1>${escapeHtml(title)}</h1>
    <div class="meta">Genere le ${escapeHtml(generatedAt)}<br/>Question : ${escapeHtml(question)}</div>
    <section class="decision">
      <div><span>Zone</span><strong>${escapeHtml(answer.top_zone || "Casablanca")}</strong></div>
      <div><span>Type</span><strong>${escapeHtml(projectLabel)}</strong></div>
      <div><span>Score</span><strong>${escapeHtml(reportScore)}</strong></div>
      <div><span>Moteur</span><strong>${escapeHtml(reportEngine)}</strong></div>
    </section>
    <h2>Synthese executive</h2>
    <p class="summary">${escapeHtml(summaryShort)}</p>
    <h2>KPIs decisionnels</h2>
    <table>${htmlRows}</table>
    <h2>Alternatives a comparer</h2>
    <ul>${alternativesHtml}</ul>
    <h2>Checklist due diligence</h2>
    <ul>${dueDiligence.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>
    <h2>Sources</h2>
    <ul>${sourceHtml}</ul>
    ${evidenceHtml}
    <h2>Limites</h2>
    <p>Ce rapport est une aide a la preselection. Il ne remplace pas une visite terrain, une due diligence financiere, juridique et reglementaire, ni une validation commerciale.</p>
  </main>
</body>
</html>`;

  return {
    title,
    fileStem: slugify(title),
    markdown,
    html,
    summaryShort,
    question,
    generatedAt,
    projectLabel,
    scoreLabel: reportScore,
    riskLabel: reportRisk,
    engineLabel: reportEngine,
    kpis,
    alternatives,
    sources,
    evidence,
    dueDiligence,
  };
}

export default function InvestorReport({ answer }: { answer: ChatAnswer }) {
  const report = useMemo(() => buildInvestorReport(answer), [answer]);
  const markdownHref = useMemo(() => downloadHref(report.markdown, "text/markdown"), [report.markdown]);
  const htmlHref = useMemo(() => downloadHref(report.html, "text/html"), [report.html]);
  const pdfHref = useMemo(() => `data:application/pdf;base64,${btoa(buildPdfContent(report))}`, [report]);
  const [copied, setCopied] = useState(false);

  function copyMarkdown() {
    navigator.clipboard.writeText(report.markdown).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  return (
    <main className="workspace">
      <div className="content-shell">
        <section className="query-block compact">
          <p className="eyebrow">Rapports</p>
          <h2>Pack decisionnel pour {answer.top_zone}</h2>
        </section>

        <section className="report-grid">
          <article className="report-card primary-report">
            <div className="report-icon">
              <FileSearch size={21} />
            </div>
            <span>Investor memo</span>
            <h3>Rapport structure pret a partager</h3>
            <p>
              Synthese executive, KPIs, risques, sources RAG et checklist terrain a partir de la derniere analyse.
            </p>
            <div className="report-actions">
              <button onClick={copyMarkdown} title="Copier le rapport en Markdown">
                {copied ? <CheckCircle2 size={16} /> : <Copy size={16} />}
                {copied ? "Copie" : "Copier"}
              </button>
              <a href={markdownHref} download={`${report.fileStem}.md`} title="Telecharger .md">
                <Download size={16} />
                .md
              </a>
              <a href={htmlHref} download={`${report.fileStem}.html`} title="Telecharger .html">
                <FileText size={16} />
                .html
              </a>
              <a href={pdfHref} download={`${report.fileStem}.pdf`} title="Telecharger le rapport PDF">
                <Printer size={16} />
                PDF
              </a>
            </div>
          </article>

          <article className="report-card">
            <div className="report-icon soft">
              <ClipboardList size={21} />
            </div>
            <span>Due diligence</span>
            <h3>Checklist terrain</h3>
            <p>
              Loyers, flux, autorisations, concurrence informelle et validation des donnees avant decision.
            </p>
          </article>

          <article className="report-card">
            <div className="report-icon warning">
              <AlertTriangle size={21} />
            </div>
            <span>Risk brief</span>
            <h3>Risques et hypotheses</h3>
            <p>
              Angles morts de donnees, fiabilite OSM, hypotheses de scoring et controles a documenter.
            </p>
          </article>
        </section>

        <section className="report-metric-grid">
          <div>
            <span>Zone prioritaire</span>
            <strong>{answer.top_zone}</strong>
          </div>
          <div>
            <span>Score</span>
            <strong>{report.scoreLabel}</strong>
          </div>
          <div>
            <span>Type recommande</span>
            <strong>{report.projectLabel}</strong>
          </div>
          <div>
            <span>Moteur</span>
            <strong>{report.engineLabel}</strong>
          </div>
        </section>

        <section className="report-document">
          <div className="report-document-header">
            <div>
              <span>Preview rapport</span>
              <h3>{report.title}</h3>
              <p>{report.generatedAt} · Question : {report.question}</p>
            </div>
            <span className="report-ready-pill">Pret</span>
          </div>

          <div className="report-summary">
            <h4>Synthese executive</h4>
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{answer.answer_markdown || "Aucune analyse disponible."}</ReactMarkdown>
          </div>

          <div className="report-section-grid">
            <article>
              <h4>KPIs decisionnels</h4>
              <dl>
                {report.kpis.slice(0, 8).map((item) => (
                  <div key={`${item.label}-${item.value}`}>
                    <dt>{item.label}</dt>
                    <dd>{item.value}</dd>
                  </div>
                ))}
              </dl>
            </article>
            <article>
              <h4>Checklist terrain</h4>
              <ul>
                {report.dueDiligence.map((item) => <li key={item}>{item}</li>)}
              </ul>
            </article>
          </div>

          <div className="report-section-grid">
            <article>
              <h4>Alternatives</h4>
              {report.alternatives.length ? (
                <ul>
                  {report.alternatives.map((item) => (
                    <li key={`${item.zone}-${item.category}`}>
                      <strong>{item.zone}</strong> · {scoreLabel(item.score)} · {item.category}
                    </li>
                  ))}
                </ul>
              ) : <p>Aucune alternative structuree dans la derniere reponse.</p>}
            </article>
            <article>
              <h4>Sources</h4>
              <ul>
                {report.sources.map((source) => (
                  <li key={source.title}>
                    <strong>{source.title}</strong> · {source.metric || source.subtitle || source.description || source.kind}
                  </li>
                ))}
              </ul>
            </article>
          </div>

          {report.evidence.length ? (
            <article className="report-evidence-list">
              <h4>Traces RAG</h4>
              {report.evidence.map((context) => (
                <div key={`${context.title}-${context.source_path}`}>
                  <span>{context.kind} · {Math.round((context.score || 0) * 100)}%</span>
                  <strong>{context.title}</strong>
                  <p>{context.source_path}</p>
                </div>
              ))}
            </article>
          ) : null}
        </section>
      </div>
    </main>
  );
}
