const ALLOWED_TAGS = new Set(["strong", "em", "code", "a", "ul", "ol", "li", "p", "br"]);

function sanitizeHtml(html: string): string {
  let safe = html
    .replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, "")
    .replace(/\s+on\w+\s*=\s*"[^"]*"/gi, "")
    .replace(/\s+on\w+\s*=\s*'[^']*'/gi, "")
    .replace(/\s+on\w+\s*=\s*[^\s>]+/gi, "");

  safe = safe.replace(/<\/?(\w+)[^>]*>/g, (match, tag) => {
    const t = tag.toLowerCase();
    if (!ALLOWED_TAGS.has(t)) return "";
    if (t === "a") {
      const hrefMatch = match.match(/href\s*=\s*"([^"]*)"/i);
      if (hrefMatch) {
        const url = hrefMatch[1];
        if (/^(https?:\/\/|mailto:|\/)/i.test(url) && !/javascript:/i.test(url)) {
          return `<a href="${url}" rel="noopener noreferrer" target="_blank">`;
        }
      }
      return "<a>";
    }
    if (match.startsWith("</")) return `</${tag}>`;
    return `<${tag}>`;
  });

  return safe;
}

export function renderMarkdown(text: string): string {
  if (!text) return "";

  let html = text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");

  html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/\*(.+?)\*/g, "<em>$1</em>");
  html = html.replace(/`([^`]+)`/g, "<code>$1</code>");

  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_, text, url) => {
    const safeUrl = url.replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">");
    if (/^(https?:\/\/|mailto:|\/)/i.test(safeUrl) && !/javascript:/i.test(safeUrl)) {
      return `<a href="${safeUrl}">${text}</a>`;
    }
    return text;
  });

  const blocks: string[] = [];
  let inList = false;

  for (const line of html.split("\n")) {
    const trimmed = line.trim();
    const listMatch = trimmed.match(/^[-*]\s+(.+)/);

    if (listMatch) {
      if (!inList) {
        blocks.push("<ul>");
        inList = true;
      }
      blocks.push(`<li>${listMatch[1]}</li>`);
    } else {
      if (inList) {
        blocks.push("</ul>");
        inList = false;
      }
      if (trimmed === "") {
        blocks.push("");
      } else {
        const headingMatch = trimmed.match(/^#{1,3}\s+(.+)/);
        if (headingMatch) {
          blocks.push(`<p>${headingMatch[1]}</p>`);
        } else {
          blocks.push(`<p>${trimmed}</p>`);
        }
      }
    }
  }
  if (inList) blocks.push("</ul>");

  return sanitizeHtml(blocks.join("\n"));
}
