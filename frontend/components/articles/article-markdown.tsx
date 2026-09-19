import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";
import { ArticleChart } from "@/components/articles/article-chart";
import { cn } from "@/lib/utils";

/*
 * No rehype-raw, on purpose. Without it any HTML an author types is shown as
 * text rather than parsed, and react-markdown's default URL transform already
 * drops javascript: links — so article bodies need no sanitiser, and there is
 * no sanitiser configuration to get wrong. KaTeX runs with `trust` off, which
 * keeps \href and \htmlClass from reaching the page either.
 */

type HastNode = {
  type: string;
  tagName?: string;
  value?: string;
  properties?: { className?: unknown };
  children?: HastNode[];
};

function textOf(node: HastNode): string {
  if (node.type === "text") return node.value ?? "";
  return (node.children ?? []).map(textOf).join("");
}

/** The source of a ```chart fence, or null for any other <pre>. */
function chartSource(pre: HastNode | undefined): string | null {
  const code = pre?.children?.[0];
  if (!code || code.type !== "element" || code.tagName !== "code") return null;
  const classes = code.properties?.className;
  if (!Array.isArray(classes) || !classes.includes("language-chart")) return null;
  return textOf(code);
}

const COMPONENTS: Components = {
  pre({ node, children, ...props }) {
    const source = chartSource(node as HastNode | undefined);
    if (source !== null) return <ArticleChart source={source} />;
    return <pre {...props}>{children}</pre>;
  },
  a({ node, href, children, ...props }) {
    void node;
    // A link the URL transform refused (javascript: and the like) arrives
    // with no href; keep its words and drop the dead link.
    if (!href) return <span>{children}</span>;
    const external = /^https?:\/\//i.test(href);
    return (
      <a
        href={href}
        {...props}
        {...(external
          ? { target: "_blank", rel: "noopener noreferrer nofollow ugc" }
          : {})}
      >
        {children}
      </a>
    );
  },
  img({ node, src, alt, ...props }) {
    void node;
    return (
      // Article figures come from authors at arbitrary sizes and hosts, which
      // next/image would need declared ahead of time.
      // eslint-disable-next-line @next/next/no-img-element
      <img src={src} alt={alt ?? ""} loading="lazy" decoding="async" {...props} />
    );
  },
  table({ node, children, ...props }) {
    void node;
    // Wide tables scroll inside themselves instead of widening the page.
    return (
      <div className="article-table">
        <table {...props}>{children}</table>
      </div>
    );
  },
};

export function ArticleMarkdown({
  source,
  className,
}: {
  source: string;
  className?: string;
}) {
  return (
    <div className={cn("article-prose", className)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[[rehypeKatex, { throwOnError: false, strict: "ignore" }]]}
        components={COMPONENTS}
      >
        {source}
      </ReactMarkdown>
    </div>
  );
}
