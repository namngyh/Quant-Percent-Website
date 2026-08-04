import { getLocale, getTranslations } from "next-intl/server";
import type { ModelConfig } from "@/config/models";
import { Reveal } from "@/components/reveal";

/**
 * Layer-by-layer view of a flagship system. Names techniques only.
 * parameters, weights and entry logic stay unpublished (spec §9.2).
 */
export async function Architecture({ model }: { model: ModelConfig }) {
  if (!model.architecture?.length) return null;
  const locale = (await getLocale()) as "vi" | "en";
  const t = await getTranslations("models.detail");

  return (
    <section>
      <h2 className="title-md">{t("architecture")}</h2>
      <p className="mt-3 max-w-2xl text-sm leading-relaxed text-dim">
        {t("architectureNote")}
      </p>

      <ol className="mt-8 grid gap-px overflow-hidden rounded-lg border border-border bg-border shadow-sm sm:grid-cols-2 desk:grid-cols-3">
        {model.architecture.map((layer, i) => (
          <li key={layer.title.en} className="bg-background p-6">
            <Reveal index={i}>
              <p className="figure text-xs text-dim">
                {String(i + 1).padStart(2, "0")}
              </p>
              <h3 className="mt-3 text-[15px] font-semibold leading-snug">
                {layer.title[locale]}
              </h3>
              <p className="mt-2 text-[13px] leading-relaxed text-dim">
                {layer.text[locale]}
              </p>
            </Reveal>
          </li>
        ))}
      </ol>
    </section>
  );
}
