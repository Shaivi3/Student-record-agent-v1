import React, { useEffect, useMemo, useState } from "react";

function renderInline(text) {
  const parts = text.split(/(`[^`]+`|\*\*[^*]+\*\*)/g);

  return parts.map((part, index) => {
    if (part.startsWith("`") && part.endsWith("`")) {
      return <code key={index}>{part.slice(1, -1)}</code>;
    }

    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={index}>{part.slice(2, -2)}</strong>;
    }

    return <React.Fragment key={index}>{part}</React.Fragment>;
  });
}

function MarkdownBlock({ content }) {
  const blocks = useMemo(() => {
    const lines = content.replace(/\r\n/g, "\n").split("\n");
    const parsed = [];
    let paragraph = [];
    let list = [];
    let code = [];
    let inCode = false;

    const flushParagraph = () => {
      if (paragraph.length) {
        parsed.push({ type: "p", text: paragraph.join(" ") });
        paragraph = [];
      }
    };

    const flushList = () => {
      if (list.length) {
        parsed.push({ type: "ul", items: list });
        list = [];
      }
    };

    lines.forEach((line) => {
      if (line.trim().startsWith("```")) {
        if (inCode) {
          parsed.push({ type: "code", text: code.join("\n") });
          code = [];
          inCode = false;
        } else {
          flushParagraph();
          flushList();
          inCode = true;
        }
        return;
      }

      if (inCode) {
        code.push(line);
        return;
      }

      if (!line.trim()) {
        flushParagraph();
        flushList();
        return;
      }

      const listMatch = line.match(/^\s*[-*]\s+(.+)/);
      if (listMatch) {
        flushParagraph();
        list.push(listMatch[1]);
        return;
      }

      flushList();
      paragraph.push(line.trim());
    });

    flushParagraph();
    flushList();
    if (code.length) parsed.push({ type: "code", text: code.join("\n") });

    return parsed;
  }, [content]);

  return (
    <div className="markdown">
      {blocks.map((block, index) => {
        if (block.type === "code") {
          return <pre key={index}><code>{block.text}</code></pre>;
        }

        if (block.type === "ul") {
          return (
            <ul key={index}>
              {block.items.map((item, itemIndex) => (
                <li key={itemIndex}>{renderInline(item)}</li>
              ))}
            </ul>
          );
        }

        return <p key={index}>{renderInline(block.text)}</p>;
      })}
    </div>
  );
}

export default function MessageBubble({ role, content, animate = false }) {
  const [visibleContent, setVisibleContent] = useState(animate ? "" : content);
  const isUser = role === "user";

  useEffect(() => {
    if (!animate) {
      setVisibleContent(content);
      return undefined;
    }

    setVisibleContent("");
    let index = 0;
    const interval = window.setInterval(() => {
      index += 3;
      setVisibleContent(content.slice(0, index));
      if (index >= content.length) window.clearInterval(interval);
    }, 16);

    return () => window.clearInterval(interval);
  }, [animate, content]);

  return (
    <article className={`message-row ${isUser ? "message-row-user" : ""}`}>
      <div className={`message-bubble ${isUser ? "message-user" : "message-assistant"}`}>
        <div className="message-label">{isUser ? "You" : "SRA"}</div>
        <MarkdownBlock content={visibleContent} />
      </div>
    </article>
  );
}
